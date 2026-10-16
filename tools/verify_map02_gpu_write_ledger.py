#!/usr/bin/env python3
"""Offline source-pinned MAP02 VRAM transfer ledger (not a gameplay capture).

Replay explicit PC-port LoadImage/MoveImage/ClearImage transfer events in the
exact order they were recorded between successive user-supplied private VRAM
snapshots. Reject all unexplained changes, including rasterized GPU writes
not represented by these three APIs. Requires the already checked private
per-submission MAP02 GTE/VRAM timeline. No raw pixels or geometry in report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tools.prepare_map02_pcport import git_blob_sha1
from tools.verify_map02_frame_bundle import (
    DIGEST_RE, VRAM_BYTES, fields, number, parse_json, safe_file, safe_file_max,
    sha_check,
)
from tools.verify_map02_vram_timeline import verify_timeline

SCHEMA = "vh.map02.gpu.transfer-ledger.v1"
MAX_EVENTS = 512
MAX_EVENT_BYTES = 512 * 1024
MAX_TRANSFER_WORDS = 16384
LIBGPU_BLOB = "9d0fab71c45ed09dda072cfeacd557ab9c5d81e5"
RASTER_BLOB = "ba8a05d161ad778c0b75e452ff0a11ed163c65cd"

# These anchors are extracted from the fixed public PC-port source. Crucial
# distinction: MoveImage reads and writes IN PLACE in positive i,j order;
# Python's slice-copy and memmove would not have the same overlap behavior.
ANCHORS_GPU = (
    "int LoadImage(RECT *rect, unsigned int *p) {",
    "PC_LangPatchFwdUpload(rect->x, rect->y, rect->w, rect->h, src);",
    "for (y = y0; y < y1; y++)",
    "for (x = x0; x < x1; x++)",
    "vram[rect->y + y][rect->x + x] = src[y * rect->w + x];",
    "int MoveImage(RECT *rect, int x, int y) {",
    "for (j = 0; j < rect->h; j++)",
    "for (i = 0; i < rect->w; i++)",
    "vram[dy][dx] = vram[sy][sx];",
    "int ClearImage(RECT *rect, u_char r, u_char g, u_char b) {",
    "FillRectRaw(rect->x, rect->y, rect->w, rect->h, r, g, b);",
)
ANCHORS_RASTER = (
    "static unsigned short PackColor(int r, int g, int b) {",
    "return (unsigned short)(((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3));",
    "void FillRectRaw(int x0, int y0, int w, int h, int r, int g, int b) {",
    "s_vram[y][x] = c;",
)


def audit_original_source(libgpu_bytes, raster_bytes):
    if (git_blob_sha1(libgpu_bytes) != LIBGPU_BLOB or
            git_blob_sha1(raster_bytes) != RASTER_BLOB):
        raise ValueError("upstream GPU source Git blobs are not the pinned revision")
    gpu = libgpu_bytes.decode("utf-8")
    raster = raster_bytes.decode("utf-8")
    for anchor in ANCHORS_GPU:
        if gpu.count(anchor) != 1:
            raise ValueError("pinned PC GPU Load/Move/Clear semantics changed: " + anchor)
    for anchor in ANCHORS_RASTER:
        if raster.count(anchor) != 1:
            raise ValueError("pinned PC GPU clear/raster packing changed: " + anchor)
    return True


def rect(value):
    if type(value) is not list or len(value) != 4:
        raise ValueError("rect must be [x,y,w,h]")
    x, y = [number(v, "rectangle origin", -2048, 2048) for v in value[:2]]
    w, h = [number(v, "rectangle dimension", 1, 2048) for v in value[2:]]
    if w * h > MAX_TRANSFER_WORDS:
        raise ValueError("transfer rectangle exceeds safe word limit")
    return x, y, w, h


def coord(value, label):
    if type(value) is not list or len(value) != 2:
        raise ValueError(f"{label} must be two integers")
    return (number(value[0], label, -2048, 2048),
            number(value[1], label, -2048, 2048))


def u16(view, index):
    addr = index * 2
    return view[addr] | (view[addr+1] << 8)


def put16(view, index, word):
    addr = index * 2
    view[addr] = word & 255
    view[addr+1] = word >> 8


def apply_transfer(vram, event, payload):
    """Mutate only one bounded VRAM buffer, mirroring original PC loops."""
    op = event["op"]
    x, y, w, h = rect(event["rect"])
    writes = 0
    if op == "load":
        if payload is None or len(payload) != w * h * 2:
            raise ValueError("LoadImage payload does not match source RECT size")
        for j in range(h):
            for i in range(w):
                px, py = x + i, y + j
                if 0 <= px < 1024 and 0 <= py < 512:
                    vram_index = py*1024 + px
                    put16(vram, vram_index, u16(payload, j*w+i))
                    writes += 1
    elif op == "move":
        dx, dy = coord(event["dest"], "MoveImage destination")
        for j in range(h):
            for i in range(w):
                sx, sy = x+i, y+j
                tx, ty = dx+i, dy+j
                if (0 <= sx < 1024 and 0 <= sy < 512 and
                        0 <= tx < 1024 and 0 <= ty < 512):
                    # Sequential in-place assignment, not memmove.
                    put16(vram, ty*1024+tx, u16(vram, sy*1024+sx))
                    writes += 1
    elif op == "clear":
        rgb = event["rgb"]
        if type(rgb) is not list or len(rgb) != 3:
            raise ValueError("ClearImage rgb must be [r,g,b]")
        r, g, b = [number(v, "ClearImage color", 0, 255) for v in rgb]
        color = ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)
        for j in range(h):
            for i in range(w):
                tx, ty = x+i, y+j
                if 0 <= tx < 1024 and 0 <= ty < 512:
                    put16(vram, ty*1024+tx, color)
                    writes += 1
    else:
        raise ValueError("unrecognized VRAM transfer op")
    return writes


def load_transfer_events(folder, data, transition_count):
    lines = data.splitlines()
    if not 1 <= len(lines) <= MAX_EVENTS or any(not line.strip() for line in lines):
        raise ValueError("expected 1–512 nonblank transfer events")
    events = []
    for step, line in enumerate(lines):
        event = parse_json(line, f"VRAM transfer {step}")
        if type(event) is not dict:
            raise ValueError("transfer event must be an object")
        op = event.get("op")
        common = ("step", "before_submission", "op", "rect")
        if op == "load":
            fields(event, common + ("payload_sha256",), "LoadImage event")
        elif op == "move":
            fields(event, common + ("dest",), "MoveImage event")
        elif op == "clear":
            fields(event, common + ("rgb",), "ClearImage event")
        else:
            raise ValueError(f"event {step}: unsupported transfer API")
        if number(event["step"], "transfer step", 0, MAX_EVENTS-1) != step:
            raise ValueError("VRAM transfer event order is not contiguous")
        number(event["before_submission"], "submission boundary",
               1, transition_count)
        rect(event["rect"])
        if op == "load":
            # Only immutable fixed filenames derived from the event's index:
            # never read an attacker-supplied or relative path from JSON.
            payload = safe_file(folder, f"load-{step:04d}.bin",
                                event["rect"][2]*event["rect"][3]*2)
            sha_check(payload, event["payload_sha256"], "LoadImage payload")
        else:
            payload = None
            if op == "move":
                coord(event["dest"], "MoveImage destination")
            if op == "clear":
                rgb = event["rgb"]
                if type(rgb) is not list or len(rgb) != 3:
                    raise ValueError("ClearImage rgb must have three components")
                for channel in rgb:
                    number(channel, "ClearImage component", 0, 255)
        if events and event["before_submission"] < events[-1][0]["before_submission"]:
            raise ValueError("transfer submission boundaries not ordered")
        events.append((event, payload))
    return events


def verify_write_ledger(folder, *, compiler="gcc", header=None,
                        libgpu=None, raster=None):
    folder = Path(folder).absolute()
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("ledger must be a local directory")
    # Verifies all existing source/GTE/texture/CLUT/snapshot hashes FIRST.
    timeline = verify_timeline(folder, compiler=compiler,
                               **({"header":header} if header is not None else {}))
    if timeline["submitted_faces_checked"] < 2:
        raise ValueError("transfer replay requires at least two submissions")
    raw_manifest = safe_file_max(folder, "write-ledger.json", 64*1024)
    meta = parse_json(raw_manifest, "write-ledger.json")
    fields(meta, ("schema","frame","pc_source_commit","timeline_sha256",
                  "transfers_sha256"), "transfer manifest")
    if meta["schema"] != SCHEMA or meta["pc_source_commit"] != timeline["pc_source_commit"]:
        raise ValueError("unrecognized transfer schema or PC source baseline")
    if number(meta["frame"], "transfer frame", 1, 2**32-1) != timeline["frame"]:
        raise ValueError("VRAM transfers come from a different frame")
    timeline_manifest = safe_file_max(folder, "timeline.json", 64*1024)
    sha_check(timeline_manifest, meta["timeline_sha256"], "timeline manifest")
    stream = safe_file_max(folder, "gpu-writes.jsonl", MAX_EVENT_BYTES)
    sha_check(stream, meta["transfers_sha256"], "GPU write journal")
    events = load_transfer_events(folder, stream,
                                  timeline["submitted_faces_checked"]-1)
    if libgpu is not None or raster is not None:
        if libgpu is None or raster is None:
            raise ValueError("both pinned GPU source files must be supplied")
        audit_original_source(Path(libgpu).read_bytes(), Path(raster).read_bytes())
    # All event files hashed and validated before mutation. The initial
    # snapshot is a PRIVATE trusted baseline; replay from there forward.
    state = bytearray(safe_file(folder,"gpu-vram-000.bin",VRAM_BYTES))
    operations = {"load":0,"move":0,"clear":0}
    written = explained_changed = 0
    next_event = 0
    for boundary in range(1,timeline["submitted_faces_checked"]):
        before = bytes(state)
        while (next_event < len(events) and
               events[next_event][0]["before_submission"] == boundary):
            event, payload = events[next_event]
            written += apply_transfer(state,event,payload)
            operations[event["op"]] += 1
            next_event += 1
        actual = safe_file(folder,f"gpu-vram-{boundary:03d}.bin",VRAM_BYTES)
        if state != actual:
            # We DO NOT fill the gap with invented raster writes. Other
            # writes, interrupted copies, snapshots at the wrong time,
            # or missing trace events must fail this bounded proof.
            raise ValueError(
                f"submission {boundary}: VRAM differs from transfer replay; "
                "missing/rasterized GPU write or wrong event order")
        explained_changed += sum(
            before[k:k+2] != actual[k:k+2]
            for k in range(0,VRAM_BYTES,2))
    if next_event != len(events):
        raise ValueError("unreplayed GPU write events")
    if explained_changed != timeline["changed_vram_words_across_snapshots"]:
        raise ValueError("transfer mutation counts differ from timeline")
    return {
        "write_ledger_manifest_sha256":hashlib.sha256(raw_manifest).hexdigest(),
        "gpu_writes_sha256":meta["transfers_sha256"],
        "timeline_sha256":meta["timeline_sha256"],
        "frame":timeline["frame"],
        "submitted_faces_checked":timeline["submitted_faces_checked"],
        "snapshot_transitions_replayed":timeline["snapshot_transitions_checked"],
        "gpu_transfer_events_replayed":len(events),
        "load_image_events":operations["load"],
        "move_image_events":operations["move"],
        "clear_image_events":operations["clear"],
        "vram_word_assignments":written,
        "changed_vram_words_explained":explained_changed,
        "changed_current_face_texture_words":timeline["changed_current_face_texture_words"],
        "changed_current_face_clut_words":timeline["changed_current_face_clut_words"],
        "compiled_pc_gte_matches":timeline["compiled_pc_gte_matches"],
        "every_supplied_snapshot_matches_transfer_replay":True,
        "all_vram_writes_captured":False,
        "rasterized_gpu_writes_modeled":False,
        "pc_gameplay_authenticated":False,
        "ps1_hardware_pixels_verified":False,
        "raw_game_bytes_emitted":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--compiler",default="gcc")
    parser.add_argument("--pc-libgpu",type=Path)
    parser.add_argument("--pc-raster",type=Path)
    args=parser.parse_args()
    try:
        result=verify_write_ledger(
            args.directory,compiler=args.compiler,
            libgpu=args.pc_libgpu,raster=args.pc_raster)
    except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
