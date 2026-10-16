#!/usr/bin/env python3
"""Offline integrity + PC-GTE/VRAM consistency check for an owned MAP02 frame.

Private input directory only: bundle.json, map02.decoded.bin,
gpu-vram-le.bin, gpu-events.jsonl. Reports digest/counts only. Neither
a user asset nor a frame screenshot is uploaded by this command.
Even a successful bundle is NOT authenticated retail gameplay:
timestamps, file hashes and camera numbers can be invented, and GPU
memory may change between polygon submissions.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile

from tools.verify_map02_camera_capture import WRAPPER as GTE_WRAPPER, MISMATCH

MAP_BYTES = 616 * 304
VRAM_BYTES = 1024 * 512 * 2
EVENT_LIMIT = 256 * 1024
MAX_FACES = 32
PINNED_PC_SOURCE = "14552fffa0e0b47e02b57592e274fc6e7a649923"
HEADER = Path(__file__).resolve().parent.parent / "source/map02_projection.h"
FILE_SIZES = {
    "map02.decoded.bin": MAP_BYTES,
    "gpu-vram-le.bin": VRAM_BYTES,
}
DIGEST_RE = re.compile(r"[0-9a-f]{64}\\Z")

def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON field: {key}")
        out[key] = value
    return out

def parse_json(raw, label):
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ValueError("invalid JSON numeric constant " + value)))
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid JSON: {exc}") from exc

def fields(obj, keys, label, optional=()):
    if type(obj) is not dict or not set(keys) <= set(obj) or not set(obj) <= (set(keys) | set(optional)):
        raise ValueError(f"{label}: invalid fields")
    return obj

def number(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label}: expected integer in [{low},{high}]")
    return value

def vector(value, label, length, low, high):
    if type(value) is not list or len(value) != length:
        raise ValueError(f"{label}: expected {length} integers")
    return [number(v, label, low, high) for v in value]

def matrix(value, label, rows, cols, low, high):
    if type(value) is not list or len(value) != rows:
        raise ValueError(f"{label}: expected {rows} rows")
    return [vector(row, label, cols, low, high) for row in value]

def safe_file(directory, name, expected_bytes):
    path = directory / name
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{name}: missing, linked or non-regular file")
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"{name}: wrong file length")
    return path.read_bytes()

def sha_check(raw, digest, name):
    if type(digest) is not str or DIGEST_RE.fullmatch(digest) is None:
        raise ValueError(f"{name}: malformed SHA-256")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"{name}: SHA-256 mismatch")

def u16(data, address):
    return struct.unpack_from("<H", data, address * 2)[0]

def s16(data, offset):
    return struct.unpack_from("<h", data, offset)[0]

def gte_projector(compiler, header):
    temp = tempfile.TemporaryDirectory(prefix="vh-map02-evidence-gte-")
    root = Path(temp.name)
    (root / "map02_projection.h").write_bytes(header.read_bytes())
    (root / "verify.c").write_text(GTE_WRAPPER, encoding="utf-8")
    result = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
         "-fPIC", "-shared", str(root / "verify.c"), "-o", str(root / "verify.so")],
        capture_output=True, text=True, timeout=30)
    if result.returncode:
        temp.cleanup()
        raise ValueError("compiled PC GTE reference failed: " + result.stderr[-1000:])
    library = ctypes.CDLL(str(root / "verify.so"))
    function = library.vh_map02_verify_snapshot
    pint = ctypes.POINTER(ctypes.c_int32)
    function.argtypes = [pint, pint, ctypes.c_int32, pint, ctypes.c_int32, ctypes.c_int32]
    function.restype = ctypes.c_int
    return temp, function

def inspect_event(event, decoded, vram, frame, ot_size, seen, projector):
    fields(event, ("stage", "frame", "register_frame", "source", "gte", "texture"), "event")
    if event["stage"] != "map02_ft4_submit":
        raise ValueError("event must be a submitted normal-terrain FT4")
    for label in ("frame", "register_frame"):
        if number(event[label], label, 1, 2**32-1) != frame:
            raise ValueError(f"{label} disagrees with frame snapshot")

    src = fields(event["source"],
        ("z","x","record_index","face_index","local_gfx","shade","indices","vertices"), "source")
    z = number(src["z"], "z", 0, 11)
    x = number(src["x"], "x", 0, 23)
    face = number(src["face_index"], "face_index", 0, 17)
    record = 28 * z + x
    if number(src["record_index"], "record_index", 0, 615) != record:
        raise ValueError("source record_index violates original 28-cell stride")
    key = (record, face)
    if key in seen:
        raise ValueError("duplicate submitted source face identity")
    seen.add(key)
    start = record * 304
    count = decoded[start + 302]
    if count > 18 or face >= count:
        raise ValueError("face outside decoded tile faceCt")
    gfx = s16(decoded, start + 176 + 2*face)
    if number(src["local_gfx"], "local_gfx", -32768, 32767) != gfx or gfx <= 0:
        raise ValueError("decoded source local GFX mismatch or null")
    shade = decoded[start + 284 + face]
    if number(src["shade"], "shade", 0, 25) != shade:
        raise ValueError("decoded source shade mismatch")
    indices = vector(src["indices"], "source indices", 4, 0, 21)
    positions = matrix(src["vertices"], "source vertices", 4, 3, -32768, 32767)
    for i, vi in enumerate(indices):
        if decoded[start+212+4*face+i] != vi:
            raise ValueError("decoded face vertex index mismatch")
        actual = [s16(decoded, start+vi*8+axis*2) for axis in range(3)]
        if positions[i] != actual:
            raise ValueError("decoded face vertex coordinates mismatch")

    gte = fields(event["gte"], ("camera","perimeter_xy","nclip_mac0","raw_otz"), "gte")
    camera = vector(gte["camera"], "camera", 16, -2**31, 2**31-1)
    for i in range(9):
        number(camera[i], "RT coefficient", -32768, 32767)
    for i in (14,15):
        number(camera[i], "H/ZSF4", 1, 32767)
    corners = matrix(gte["perimeter_xy"], "screen XY", 4, 2, -1024, 1023)
    nclip = number(gte["nclip_mac0"], "NCLIP MAC0", -2**31, 2**31-1)
    if nclip <= 0:
        raise ValueError("submitted terrain FT4 must have NCLIP > 0")
    otz = number(gte["raw_otz"], "raw AVSZ4 OTZ", 0, 65535)
    if max(5, otz) > ot_size:
        raise ValueError("raw OTZ outside supplied ordering table")
    # The source's FT4 output maps perimeter indices 0,1,3,2.
    gpu = [v for i in (0,1,3,2) for v in corners[i]]
    rc = projector(
        (ctypes.c_int32*16)(*camera),
        (ctypes.c_int32*12)(*(axis for p in positions for axis in p)),
        nclip, (ctypes.c_int32*8)(*gpu), otz, 1)
    if rc:
        raise ValueError("compiled PC GTE mismatch: " + MISMATCH.get(rc, f"code {rc}"))

    tex = fields(event["texture"], (
        "u","v","w","h","tpage","clut",
        "mask_x","mask_y","offset_x","offset_y"), "texture", optional=("probes",))
    u = number(tex["u"],"u",0,255)
    v = number(tex["v"],"v",0,255)
    w = number(tex["w"],"w",1,255-u)
    h = number(tex["h"],"h",1,255-v)
    tpage = number(tex["tpage"],"tpage",0,65535)
    clut = number(tex["clut"],"clut",0,65535)
    if ((tpage >> 7) & 3) != 0:
        raise ValueError("unsupported texture depth (only 4bpp)")
    maskx = number(tex["mask_x"],"mask_x",0,31)
    masky = number(tex["mask_y"],"mask_y",0,31)
    offx = number(tex["offset_x"],"offset_x",0,31)
    offy = number(tex["offset_y"],"offset_y",0,31)
    cx, cy = (clut & 63)*16, (clut >> 6) & 511
    tx, ty = (tpage & 15)*64, ((tpage >> 4)&1)*256

    def lookup(px, py):
        ux = (px & ~(maskx*8)) | ((offx & maskx)*8)
        vy = (py & ~(masky*8)) | ((offy & masky)*8)
        word = u16(vram, (ty+vy)*1024 + tx + ux//4)
        index = (word >> ((ux & 3)*4)) & 15
        return index, u16(vram, cy*1024+cx+index)

    # Independently verify every original page sample inside the crop;
    # never write raw palette/color pixels into the public summary.
    zeros = 0
    stp = 0
    for yy in range(v,v+h+1):
        for xx in range(u,u+w+1):
            index, color = lookup(xx,yy)
            zeros += (index == 0)
            stp += bool(color & 0x8000)
    probes = tex.get("probes", [])
    if type(probes) is not list or len(probes)>32:
        raise ValueError("texture probes must be a list (up to 32)")
    used = set()
    for probe in probes:
        fields(probe, ("u","v","bgr555"), "probe")
        pu = number(probe["u"],"probe u",u,u+w)
        pv = number(probe["v"],"probe v",v,v+h)
        if (pu,pv) in used:
            raise ValueError("duplicate texture probe coordinates")
        used.add((pu,pv))
        raw = number(probe["bgr555"], "observed BGR555", 0, 65535)
        if lookup(pu,pv)[1] != raw:
            raise ValueError("recorded GPU texture probe disagrees with source VRAM")
    return (w+1)*(h+1), zeros, stp, len(probes)

def verify_bundle(directory: Path, *, compiler="gcc", header=HEADER):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("bundle must be a real local directory")
    manifest_raw = safe_file_max(directory, "bundle.json", 64*1024)
    manifest = parse_json(manifest_raw, "bundle.json")
    fields(manifest, ("schema","frame","vram_snapshot_frame","ot_size",
                       "pc_source_commit","decoded_map_sha256",
                       "vram_sha256","events_sha256"), "manifest",
           optional=("pc_game_binary_sha256",))
    if manifest["schema"] != "vh.map02.frame.v1" or manifest["pc_source_commit"] != PINNED_PC_SOURCE:
        raise ValueError("unrecognized schema or unpinned PC source commit")
    frame = number(manifest["frame"],"frame",1,2**32-1)
    if number(manifest["vram_snapshot_frame"],"snapshot frame",1,2**32-1) != frame:
        raise ValueError("snapshot frame differs from capture frame")
    ot = number(manifest["ot_size"],"OT length",5,4096)
    if "pc_game_binary_sha256" in manifest:
        digest = manifest["pc_game_binary_sha256"]
        if type(digest) is not str or DIGEST_RE.fullmatch(digest) is None:
            raise ValueError("invalid game binary fingerprint")
    decoded = safe_file(directory,"map02.decoded.bin",MAP_BYTES)
    vram = safe_file(directory,"gpu-vram-le.bin",VRAM_BYTES)
    events_raw = safe_file_max(directory,"gpu-events.jsonl",EVENT_LIMIT)
    sha_check(decoded,manifest["decoded_map_sha256"],"decoded MAP02")
    sha_check(vram,manifest["vram_sha256"],"VRAM")
    sha_check(events_raw,manifest["events_sha256"],"GPU event stream")
    lines = events_raw.splitlines()
    if not 1 <= len(lines) <= MAX_FACES or any(not line.strip() for line in lines):
        raise ValueError("expected 1–32 nonblank submitted FT4 observations")
    events = [parse_json(line, f"event {i+1}") for i,line in enumerate(lines)]
    compiled, projector = gte_projector(compiler,header)
    try:
        seen = set()
        sampled = zero = stp = probes = 0
        for index,event in enumerate(events):
            try:
                n,z,s,p = inspect_event(event,decoded,vram,frame,ot,seen,projector)
            except ValueError as exc:
                raise ValueError(f"event {index+1}: {exc}") from exc
            sampled+=n;zero+=z;stp+=s;probes+=p
    finally:
        compiled.cleanup()
    return {
        "bundle_manifest_sha256":hashlib.sha256(manifest_raw).hexdigest(),
        "decoded_map_sha256":manifest["decoded_map_sha256"],
        "vram_sha256":manifest["vram_sha256"],
        "events_sha256":manifest["events_sha256"],
        "pc_source_commit":manifest["pc_source_commit"],
        "game_binary_fingerprint_supplied":"pc_game_binary_sha256" in manifest,
        "frame":frame,
        "submitted_faces_checked":len(events),
        "source_faces_matched":len(seen),
        "compiled_pc_gte_matches":len(events),
        "vram_4bpp_crop_texels_checked":sampled,
        "zero_index_texels":zero,
        "stp_palette_texels":stp,
        "recorded_vram_color_probes_checked":probes,
        "all_inputs_have_matching_frame_labels":True,
        "frame_capture_authenticated":False,
        "vram_unchanged_between_draws_proven":False,
        "retail_ps1_pixels_verified":False,
        "input_game_bytes_printed":False,
    }

def safe_file_max(directory, name, maximum):
    path = directory / name
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{name}: missing, linked or non-regular file")
    if not 0 < path.stat().st_size <= maximum:
        raise ValueError(f"{name}: empty or over size limit")
    return path.read_bytes()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path,help="local private MAP02 frame-bundle directory")
    parser.add_argument("--compiler",default="gcc")
    args = parser.parse_args()
    try:
        result = verify_bundle(args.directory,compiler=args.compiler)
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
