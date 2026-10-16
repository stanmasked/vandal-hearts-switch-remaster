#!/usr/bin/env python3
"""Fail-closed, bounded read-only preflight for a user-supplied M_MAP02.PRS.

This is NOT the game's unsafe decoder. It independently implements the exact
token semantics of pinned src/maps/unpack.c with explicit bounds. It never
executes or mutates user content or emits decoded proprietary map data.
Only aggregate face counts, GFX coverage and hashes are reported.

Retail file identity cannot be proven from a filename or a successful decode.
The 28x12/304-byte model contract is derived from the pinned PC-port.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

WIDTH, HEIGHT = 28, 12
STRIDE = 304  # 22 SVECTOR*8 + 18 s16 + (18*4) faces + 18 shades + faceCt + height
EXPECTED = WIDTH * HEIGHT * STRIDE
MAX_COMPRESSED = 2 * 1024 * 1024
MAX_PADDING = 4096
FACE_COUNT = 18
VERTEX_COUNT = 22
GFX_COUNT = 870
V24_COUNT = 120
V24_MASTERS = 96
ROW = re.compile(r"^\s*\{\s*(\d+(?:\s*,\s*\d+){11})\s*\},\s*$")


class InvalidPrs(ValueError):
    pass


def read_prs(path: Path, allow_zero_padding: bool = False) -> tuple[bytes, str, dict]:
    size = path.stat().st_size
    if size < 5 or size > MAX_COMPRESSED + 4 + MAX_PADDING:
        raise InvalidPrs(f"unsafe PRS input size {size} bytes")
    with path.open("rb") as fp:
        data = fp.read(MAX_COMPRESSED + 4 + MAX_PADDING + 1)
    if len(data) != size:
        raise InvalidPrs("file size changed during read")
    length, = struct.unpack_from("<I", data)
    if length < 1 or length > MAX_COMPRESSED:
        raise InvalidPrs(f"invalid compressed length: {length}")
    end = 4 + length
    if end > size:
        raise InvalidPrs("truncated PRS compressed payload")
    tail = data[end:]
    if tail and not allow_zero_padding:
        raise InvalidPrs(f"unexpected trailing {len(tail)} bytes; use --allow-zero-padding only for all-zero sector padding")
    if len(tail) > MAX_PADDING or any(tail):
        raise InvalidPrs("nonzero or excessive trailing bytes")
    return data[4:end], hashlib.sha256(data).hexdigest(), {
        "file_bytes": size,
        "declared_compressed_bytes": length,
        "zero_padding_bytes": len(tail),
    }


def unpack_bounded(payload: bytes, output_limit: int = EXPECTED) -> bytes:
    if not 1 <= output_limit <= EXPECTED:
        raise InvalidPrs("invalid decompression output capacity")
    if not 1 <= len(payload) <= MAX_COMPRESSED:
        raise InvalidPrs("invalid compressed buffer length")
    out = bytearray()
    dictionary = bytearray(1024)
    cache_ofs = 990
    pos = 0

    def emit(byte: int):
        nonlocal cache_ofs
        if len(out) >= output_limit:
            raise InvalidPrs("decompression exceeds expected 28x12 MapTileModel size")
        out.append(byte)
        dictionary[cache_ofs] = byte
        cache_ofs = (cache_ofs + 1) & 1023

    while pos < len(payload):
        flag = payload[pos]
        pos += 1
        mode_bits = flag | 0xff00
        while mode_bits & 0x100:
            # The original decoder exits when its compressed byte count is
            # exhausted in the middle of the final eight-symbol flag group.
            # Require the FULL expected output before accepting that boundary.
            if pos == len(payload):
                if len(out) == output_limit:
                    return bytes(out)
                raise InvalidPrs("truncated compressed token group")
            if not (mode_bits & 1):
                emit(payload[pos])
                pos += 1
            else:
                b1 = payload[pos]
                pos += 1
                if b1 < 0x80:
                    if pos >= len(payload):
                        raise InvalidPrs("truncated absolute dictionary token")
                    offset = ((b1 & 3) << 8) | payload[pos]
                    pos += 1
                    count = (b1 >> 2) + 3
                    for i in range(count):
                        emit(dictionary[(offset + i) & 1023])
                elif b1 < 0xc0:
                    offset = b1 & 15
                    count = ((b1 & 0x30) >> 4) + 2
                    for _ in range(count):
                        emit(dictionary[(cache_ofs - offset) & 1023])
                else:
                    count = (b1 & 63) + 8
                    if pos + count > len(payload):
                        raise InvalidPrs("truncated literal-run token")
                    for byte in payload[pos:pos + count]:
                        emit(byte)
                    pos += count
            mode_bits >>= 1
    if len(out) != output_limit:
        raise InvalidPrs(f"decoded {len(out)} bytes, expected {output_limit}")
    return bytes(out)


def load_v24(path: Path) -> dict[int, tuple[int, ...]]:
    src = path.read_text(encoding="utf-8")
    if "#define VH_MAP02_HD_SLOT_COUNT 120" not in src:
        raise InvalidPrs("v24 lookup header missing strict 120-row declaration")
    result = {}
    for line in src.splitlines():
        m = ROW.fullmatch(line)
        if m is None:
            continue
        values = tuple(int(v.strip()) for v in m.group(1).split(","))
        slot, canonical, u, v, w, h, cw, ch, tpage, clut, turns, mirror = values
        if slot in result:
            raise InvalidPrs(f"duplicate v24 slot {slot}")
        if not (1 <= slot <= 469 and 1 <= canonical <= 469 and
                0 <= u <= 255 and 0 <= v <= 255 and 1 <= w <= 256-u and
                1 <= h <= 256-v and 1 <= cw <= 256 and 1 <= ch <= 256 and
                0 <= tpage <= 65535 and 0 <= clut <= 65535 and
                turns in (0, 1, 2, 3) and mirror in (0, 1)):
            raise InvalidPrs(f"invalid v24 slot geometry or palette: {slot}")
        if (w, h) != ((cw, ch) if turns % 2 == 0 else (ch, cw)):
            raise InvalidPrs(f"v24 rotation changes dimensions for slot {slot}")
        result[slot] = values
    if len(result) != V24_COUNT:
        raise InvalidPrs(f"v24 lookup has {len(result)} entries, expected 120")
    masters = {row[1] for row in result.values()}
    if len(masters) != V24_MASTERS:
        raise InvalidPrs(f"v24 lookup has {len(masters)} masters, expected 96")
    if not masters.issubset(result):
        raise InvalidPrs("v24 canonical slot references absent entries")
    for slot in (241, 243):
        if result[slot][1] != slot:
            raise InvalidPrs(f"protected v24 slot {slot} lost its identity")
    if result[241][8:10] != (5, 31978) or result[243][8:10] != (5, 31850):
        raise InvalidPrs("protected slot tpage/CLUT mismatch")
    return result


def inspect_models(decoded: bytes, slots: dict[int, tuple[int, ...]]) -> dict:
    if len(decoded) != EXPECTED:
        raise InvalidPrs(f"invalid unpacked model array size {len(decoded)}")
    face_gfx = Counter()
    matched = Counter()
    unmatched = Counter()
    other = Counter()
    empty = 0
    nonempty = 0
    count_faces = 0
    used_vertices = 0
    for idx in range(WIDTH * HEIGHT):
        base = idx * STRIDE
        nfaces = decoded[base + 302]
        if nfaces > FACE_COUNT:
            raise InvalidPrs(f"tile z={idx//WIDTH} x={idx%WIDTH}: faceCt {nfaces} > 18")
        if nfaces:
            nonempty += 1
        else:
            empty += 1
        for face in range(nfaces):
            gfx, = struct.unpack_from("<h", decoded, base + 176 + 2 * face)
            verts = decoded[base+212+4*face:base+216+4*face]
            shade = decoded[base + 284 + face]
            if gfx < 0 or gfx >= GFX_COUNT:
                raise InvalidPrs(f"tile z={idx//WIDTH} x={idx%WIDTH}, face {face}: invalid GFX {gfx}")
            if gfx == 0:
                continue
            if any(v >= VERTEX_COUNT for v in verts):
                raise InvalidPrs(f"tile z={idx//WIDTH} x={idx%WIDTH}, face {face}: vertex index >=22")
            if shade >= 26:
                raise InvalidPrs(f"tile z={idx//WIDTH} x={idx%WIDTH}, face {face}: shade index >=26")
            used_vertices += len(set(verts))
            count_faces += 1
            face_gfx[gfx] += 1
            if gfx >= 400:
                local = gfx - 400
                if local in slots:
                    matched[local] += 1
                else:
                    unmatched[local] += 1
            else:
                other[gfx] += 1

    def counter_dict(src: Counter):
        return {str(k): src[k] for k in sorted(src)}
    candidates = sum(matched.values()) + sum(unmatched.values())
    return {
        "map_grid": {"width": WIDTH, "height": HEIGHT, "total_tiles": WIDTH*HEIGHT},
        "empty_tiles": empty,
        "tiles_with_faces": nonempty,
        "non_null_faces": count_faces,
        "vertex_references": used_vertices,
        "global_gfx_histogram": counter_dict(face_gfx),
        "v24_candidate_faces": candidates,
        "v24_matched_faces": sum(matched.values()),
        "v24_unmatched_faces": sum(unmatched.values()),
        "v24_matched_local_slot_counts": counter_dict(matched),
        "v24_unmatched_local_slot_counts": counter_dict(unmatched),
        "non_candidate_gfx_counts": counter_dict(other),
        "v24_distinct_slots_observed": len(matched),
        "v24_distinct_masters_observed": len({slots[k][1] for k in matched}),
        "v24_coverage_note": (
            "Slot coverage is based on GFX-400 only; PRS face data does not "
            "carry actual runtime tpage/CLUT/UV. No HD replacement is approved."
        ),
    }


def inspect_file(prs: Path, lookup_header: Path, zero_padding=False, synthetic=False):
    slots = load_v24(lookup_header)
    compressed, sha, meta = read_prs(prs, allow_zero_padding=zero_padding)
    decoded = unpack_bounded(compressed)
    return {
        "schema": "vh-map02-bounded-prs-preflight-v45",
        "status": "structurally_valid_unverified_source",
        "input_provenance": "caller_declared_synthetic" if synthetic else "unverified_file",
        "retail_map_authenticity_proven": False,
        "runtime_tpage_clut_uv_proven": False,
        "HD_replacement_approved": False,
        "sha256_input": sha,
        "sha256_decoded": hashlib.sha256(decoded).hexdigest(),
        "decoded_bytes": len(decoded),
        "lookup_v24_rows": len(slots),
        "lookup_v24_canonical_masters": len({a[1] for a in slots.values()}),
        **meta,
        **inspect_models(decoded, slots),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prs", type=Path, help="user-authorized M_MAP02.PRS, kept local")
    parser.add_argument("--v24", type=Path, default=Path(__file__).resolve().parents[1]/
                        "tests/fixtures/vh_map02_hd_lookup_v24.h")
    parser.add_argument("--output", type=Path, help="JSON report only; refuses overwrite")
    parser.add_argument("--allow-zero-padding", action="store_true",
                        help="accept at most 4096 all-zero sector-pad bytes")
    parser.add_argument("--synthetic-fixture", action="store_true",
                        help="label test-owned synthetic bytes; never implies retail authenticity")
    args = parser.parse_args()
    try:
        result = inspect_file(args.prs, args.v24, args.allow_zero_padding,
                              args.synthetic_fixture)
        data = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as out:
                out.write(data)
        else:
            print(data, end="")
        return 0
    except (InvalidPrs, OSError, UnicodeError, KeyError) as exc:
        print(f"[v45-preflight] REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
