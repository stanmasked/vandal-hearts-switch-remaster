#!/usr/bin/env python3
"""Offline MAP02 *per-submission* VRAM timeline: independent snapshots and GTE.

This is a consistency / mutation-detector for privately acquired, user-owned
data, NOT a gameplay recorder and NOT evidence of PS1 GPU pixel equivalence.
Only file hashes and aggregate counts are returned. In particular, differing
snapshots show VRAM changed between captured instants, but do NOT identify
when, how, or whether it changed and then reverted between snapshots.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tools.verify_map02_frame_bundle import (
    MAP_BYTES, VRAM_BYTES, MAX_FACES, PINNED_PC_SOURCE, DIGEST_RE, HEADER,
    fields, gte_projector, inspect_event, number, parse_json,
    safe_file, safe_file_max, sha_check, u16,
)

SCHEMA = "vh.map02.vram.timeline.v1"
MAX_MANIFEST = 65536
EVENT_LIMIT = 256 * 1024


def read_events(raw):
    lines = raw.splitlines()
    if not 1 <= len(lines) <= MAX_FACES or any(not line.strip() for line in lines):
        raise ValueError("timeline requires 1–32 nonblank GPU events")
    events = []
    for index, line in enumerate(lines):
        event = parse_json(line, f"GPU event {index}")
        fields(event, ("stage", "frame", "register_frame", "source",
                       "gte", "texture", "submission_index",
                       "vram_snapshot_index"), f"event {index}")
        if number(event["submission_index"], "submission index", 0, MAX_FACES-1) != index:
            raise ValueError(f"event {index}: nonmonotonic submission index")
        if number(event["vram_snapshot_index"], "snapshot index", 0, MAX_FACES-1) != index:
            raise ValueError(f"event {index}: snapshot must be paired to submission")
        events.append(event)
    return events


def referenced_words(event, vram):
    """Return exact 16-bit VRAM indices sampled by this submitted 4-bpp crop.

    This duplicates the proven original index-address formula solely to
    identify modified source locations. Projection, data validity and all
    recorded BGR555 probes are checked independently by inspect_event().
    """
    t = event["texture"]
    tx = (t["tpage"] & 15) * 64
    ty = ((t["tpage"] >> 4) & 1) * 256
    cx = (t["clut"] & 63) * 16
    cy = (t["clut"] >> 6) & 511
    mx, my = t["mask_x"] * 8, t["mask_y"] * 8
    ox = (t["offset_x"] & t["mask_x"]) * 8
    oy = (t["offset_y"] & t["mask_y"]) * 8
    texture_words = set()
    palette_words = set()
    for y in range(t["v"], t["v"] + t["h"] + 1):
        yy = (y & ~my) | oy
        for x in range(t["u"], t["u"] + t["w"] + 1):
            xx = (x & ~mx) | ox
            word_index = (ty + yy) * 1024 + tx + xx//4
            texel_index = (u16(vram, word_index) >> ((xx & 3) * 4)) & 15
            texture_words.add(word_index)
            palette_words.add(cy * 1024 + cx + texel_index)
    return texture_words, palette_words


def words_changed(left, right, addresses):
    return sum(left[index*2:index*2+2] != right[index*2:index*2+2]
               for index in addresses)


def verify_timeline(directory, *, compiler="gcc", header=HEADER):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("bundle must be a real private directory")
    manifest_raw = safe_file_max(directory, "timeline.json", MAX_MANIFEST)
    manifest = parse_json(manifest_raw, "timeline.json")
    fields(manifest,
           ("schema", "frame", "ot_size", "pc_source_commit",
            "decoded_map_sha256", "events_sha256", "snapshots"),
           "manifest", optional=("pc_game_binary_sha256",))
    if manifest["schema"] != SCHEMA or manifest["pc_source_commit"] != PINNED_PC_SOURCE:
        raise ValueError("unknown timeline schema or unpinned source revision")
    frame = number(manifest["frame"], "frame", 1, 2**32-1)
    ot_size = number(manifest["ot_size"], "OT size", 5, 4096)
    if "pc_game_binary_sha256" in manifest:
        digest = manifest["pc_game_binary_sha256"]
        if type(digest) is not str or DIGEST_RE.fullmatch(digest) is None:
            raise ValueError("invalid optional game binary SHA-256")
    map_raw = safe_file(directory, "map02.decoded.bin", MAP_BYTES)
    events_raw = safe_file_max(directory, "gpu-events.jsonl", EVENT_LIMIT)
    sha_check(map_raw, manifest["decoded_map_sha256"], "MAP02 decoded source")
    sha_check(events_raw, manifest["events_sha256"], "GPU event log")
    events = read_events(events_raw)
    descriptions = manifest["snapshots"]
    if type(descriptions) is not list or len(descriptions) != len(events):
        raise ValueError("each submission requires one dedicated VRAM snapshot")
    # Authenticate the supplied files BEFORE compiling or processing events.
    # Never infer paths from JSON contents: filenames are fixed and local.
    snapshots = []
    sha_list = []
    for i, descriptor in enumerate(descriptions):
        fields(descriptor, ("index", "frame", "sha256"), f"snapshot {i}")
        if number(descriptor["index"], "snapshot index", 0, MAX_FACES-1) != i:
            raise ValueError("out-of-order snapshot descriptors")
        if number(descriptor["frame"], "snapshot frame", 1, 2**32-1) != frame:
            raise ValueError("snapshot belongs to a different frame")
        digest = descriptor["sha256"]
        raw = safe_file(directory, f"gpu-vram-{i:03d}.bin", VRAM_BYTES)
        sha_check(raw, digest, f"VRAM snapshot {i}")
        snapshots.append(raw)
        sha_list.append(digest)
    compiled, projector = gte_projector(compiler, header)
    try:
        seen = set()
        total_texels = zero = stp = probes = 0
        changed_all = changed_tex = changed_clut = relevant_transitions = 0
        changed_transitions = 0
        prev = None
        for i, (event, snapshot) in enumerate(zip(events, snapshots)):
            # The index fields are timeline metadata and MUST NOT be
            # accepted as extra fields by the v1 source/GTE validator.
            clean = {k: v for k, v in event.items()
                     if k not in ("submission_index", "vram_snapshot_index")}
            try:
                n, z, s, p = inspect_event(
                    clean, map_raw, snapshot, frame, ot_size, seen, projector)
            except ValueError as exc:
                raise ValueError(f"submission {i}: {exc}") from exc
            total_texels += n
            zero += z
            stp += s
            probes += p
            if prev is not None:
                # Consecutive *captured* images, no claim of uninterrupted
                # monitoring of GPU writes/reverts between acquisition times.
                all_diff = sum(
                    snapshot[k:k+2] != prev[k:k+2]
                    for k in range(0, VRAM_BYTES, 2))
                changed_all += all_diff
                changed_transitions += bool(all_diff)
                tex_words, palette_words = referenced_words(event, snapshot)
                dtex = words_changed(prev, snapshot, tex_words)
                dclut = words_changed(prev, snapshot, palette_words)
                changed_tex += dtex
                changed_clut += dclut
                relevant_transitions += bool(dtex or dclut)
            prev = snapshot
    finally:
        compiled.cleanup()
    return {
        "timeline_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "decoded_map_sha256": manifest["decoded_map_sha256"],
        "events_sha256": manifest["events_sha256"],
        "vram_snapshot_hash_list_sha256": hashlib.sha256(
            "".join(sha_list).encode("ascii")).hexdigest(),
        "pc_source_commit": manifest["pc_source_commit"],
        "frame": frame,
        "submitted_faces_checked": len(events),
        "snapshots_sha256_verified": len(snapshots),
        "snapshot_transitions_checked": max(0, len(snapshots)-1),
        "snapshot_transitions_with_vram_changes": changed_transitions,
        "changed_vram_words_across_snapshots": changed_all,
        "changed_current_face_texture_words": changed_tex,
        "changed_current_face_clut_words": changed_clut,
        "transitions_affecting_current_face_texture_or_clut": relevant_transitions,
        "compiled_pc_gte_matches": len(events),
        "vram_4bpp_crop_texels_checked": total_texels,
        "zero_index_texels": zero,
        "stp_palette_texels": stp,
        "observed_color_probes_checked": probes,
        "all_submission_snapshot_indices_matched": True,
        "frame_capture_authenticated": False,
        "continuous_vram_write_monitoring": False,
        "unobserved_intervening_vram_writes_excluded": False,
        "retail_ps1_pixels_verified": False,
        "raw_game_data_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path,
                        help="private directory with timeline.json and bounded snapshots")
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        report = verify_timeline(args.directory, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
