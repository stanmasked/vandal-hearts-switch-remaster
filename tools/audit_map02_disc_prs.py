#!/usr/bin/env python3
"""Read-only map-11 M_MAP02.PRS evidence from an owned US disc image or PRS file.

Matches the pinned PC-port's 4-byte compressed-byte-count header and LZ
decoder. Reports metadata and hashes only, never writes proprietary bytes.
A matching SHA-256 proves local byte identity, not visible GPU pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.compare_map02_variants import (
    EXPECTED_LENGTH, FACE_GFX_OFFSET, PRIOR_PRS_DECOMPRESSED_SHA256,
    RECORD_SIZE, TARGET_RECORDS, compare_map02,
)

START_SECTOR = 0x1BCC
SECTOR_COUNT = 0x0C
USER_BYTES = 2048
RAW_BYTES = 2352
PRIOR_COMPRESSED_SHA256 = "c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387"
PRIOR_DAT_SHA256 = "07666bd80b87de763ef7312ecaeaa0bf747ebfe49db032fa68c9af675d151c31"
PRIOR_DAT_LENGTH = 238336
DAT_START_SECTOR = 6999
DAT_SECTOR_COUNT = (PRIOR_DAT_LENGTH + USER_BYTES - 1) // USER_BYTES
XA_EDC_POLYNOMIAL = 0xD8018001
XA_EDC_OFFSET = 0x818
SYNC = bytes((0,)) + bytes((255,)) * 10 + bytes((0,))
MAX_INPUT_SIZE = SECTOR_COUNT * USER_BYTES


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def xa_edc(data: bytes) -> int:
    """CD-ROM XA reflected CRC with zero initial value and no final XOR.

    Mode2 Form1 checks 2056 bytes at raw sector offsets [0x10, 0x818).
    The EDC detects corruption but does not validate P/Q ECC parity.
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc >> 1) ^ (XA_EDC_POLYNOMIAL if crc & 1 else 0))
    return crc


def read_sectors_from_stream(handle, layout: str, bias: int = 0, *,
                             start_sector: int = START_SECTOR,
                             sector_count: int = SECTOR_COUNT) -> bytes:
    """Read bounded sectors from an already opened, caller-owned file descriptor.

    The caller may hash and sector-check the SAME open inode: do not silently
    reopen an untrusted filesystem path between those two operations.
    """
    sector_size = {"mode2-2352": RAW_BYTES, "iso-2048": USER_BYTES}.get(layout)
    if sector_size is None:
        raise ValueError("layout must be mode2-2352 or iso-2048")
    if type(bias) is not int:
        raise ValueError("sector bias must be an integer")
    if (type(start_sector) is not int or start_sector < 0
            or type(sector_count) is not int or sector_count < 1):
        raise ValueError("invalid disc-sector range")
    first = start_sector + bias
    if first < 0:
        raise ValueError("selected sector before beginning of image")
    data = bytearray()
    if handle.seek(0, 2) < (first + sector_count) * sector_size:
        raise ValueError("disc image is too short for requested MAP02 sectors")
    for relative in range(sector_count):
        handle.seek((first + relative) * sector_size)
        sector = handle.read(sector_size)
        if len(sector) != sector_size:
            raise ValueError(f"short sector {relative}")
        if layout == "mode2-2352":
            if sector[:12] != SYNC or sector[15] != 2:
                raise ValueError(f"sector {relative}: not Mode2/2352")
            if sector[16:20] != sector[20:24]:
                raise ValueError(f"sector {relative}: inconsistent XA subheader")
            if sector[18] & 0x20:
                raise ValueError(f"sector {relative}: Mode2 Form2 not supported")
            expected_edc = int.from_bytes(sector[XA_EDC_OFFSET:XA_EDC_OFFSET + 4], "little")
            actual_edc = xa_edc(sector[0x10:XA_EDC_OFFSET])
            if actual_edc != expected_edc:
                raise ValueError(
                    f"sector {relative}: Mode2 Form1 EDC mismatch"
                    f" (stored 0x{expected_edc:08x}, computed 0x{actual_edc:08x})"
                )
            data.extend(sector[24:24 + USER_BYTES])
        else:
            data.extend(sector)
    return bytes(data)


def read_sectors(path: Path, layout: str, bias: int = 0, *,
                 start_sector: int = START_SECTOR,
                 sector_count: int = SECTOR_COUNT) -> bytes:
    """Existing public API: open the source read-only and delegate to the stream."""
    with path.open("rb") as handle:
        return read_sectors_from_stream(
            handle, layout, bias, start_sector=start_sector,
            sector_count=sector_count,
        )


def unpack_prs(source: bytes, *, max_output: int = EXPECTED_LENGTH) -> bytes:
    """Bounded decoder matching the 1KiB dictionary token types in unpack.c.

    The 4-byte header stores the compressed byte count, not output length.
    A damaged stream or an overlarge output raises ValueError.
    """
    if len(source) < 4:
        raise ValueError("PRS compressed-length header missing")
    count = int.from_bytes(source[:4], "little")
    if count <= 0 or count > MAX_INPUT_SIZE - 4:
        raise ValueError(f"invalid MAP02 compressed byte count {count}")
    if 4 + count > len(source):
        raise ValueError("PRS stream truncated before declared compressed length")
    encoded = memoryview(source)[4:4 + count]
    cache = bytearray(1024)
    cursor = 990
    output = bytearray()
    pos = 0

    def append(value: int):
        nonlocal cursor
        if len(output) >= max_output:
            raise ValueError("PRS decompressed beyond map buffer limit")
        output.append(value)
        cache[cursor] = value
        cursor = (cursor + 1) & 1023

    def take():
        nonlocal pos
        if pos >= count:
            raise ValueError("truncated MAP02 compression token")
        byte = encoded[pos]
        pos += 1
        return int(byte)

    while pos < count:
        flags = take()
        for bit in range(8):
            if pos >= count:
                break
            if not (flags >> bit) & 1:
                append(take())
                continue
            control = take()
            if control < 0x80:
                idx = take() | ((control & 3) << 8)
                length = (control >> 2) + 3
                for offset in range(length):
                    append(cache[(idx + offset) & 1023])
            elif control < 0xC0:
                distance = control & 15
                length = ((control & 0x30) >> 4) + 2
                for _ in range(length):
                    append(cache[(cursor - distance) & 1023])
            else:
                length = (control & 63) + 8
                for _ in range(length):
                    if pos >= count:
                        # Upstream's final literal run may end at byte-count boundary.
                        break
                    append(take())
    return bytes(output)


def audit_prs(source: bytes, dat: bytes | None = None) -> dict:
    if len(source) < 4:
        raise ValueError("PRS header is missing")
    count = int.from_bytes(source[:4], "little")
    if count <= 0 or count > MAX_INPUT_SIZE - 4:
        raise ValueError(f"invalid MAP02 compressed byte count {count}")
    if len(source) < count + 4:
        raise ValueError("PRS file shorter than compression header declares")
    logical = source[:count + 4]
    unpacked = unpack_prs(logical)
    if len(unpacked) != EXPECTED_LENGTH:
        raise ValueError(f"decompressed map has {len(unpacked)} bytes, expected {EXPECTED_LENGTH}")
    faces = []
    for record in TARGET_RECORDS:
        local = unpacked[record * RECORD_SIZE + FACE_GFX_OFFSET]
        faces.append({
            "record_index": record,
            "z": record // 28, "x": record % 28, "face": 0,
            "local_gfx": local,
            "global_gfx_if_loaded": (local + 400 if local else 0),
        })
    compressed_hash = sha256(logical)
    uncompressed_hash = sha256(unpacked)
    report = {
        "compressed_byte_count": count,
        "logical_prs_byte_count": count + 4,
        "available_bytes": len(source),
        "compressed_logical_sha256": compressed_hash,
        "compressed_padded_sha256": sha256(source),
        "decompressed_sha256": uncompressed_hash,
        "matches_prior_logical_compressed_sha256": compressed_hash == PRIOR_COMPRESSED_SHA256,
        "matches_prior_padded_compressed_sha256": sha256(source) == PRIOR_COMPRESSED_SHA256,
        "matches_prior_decompressed_sha256": uncompressed_hash == PRIOR_PRS_DECOMPRESSED_SHA256,
        "target_faces": faces,
        "matches_prior_target_gfx": [face["local_gfx"] for face in faces] == [241, 243],
        "evidence_scope": "disc/source data only; not live runtime or visible screen pixels",
    }
    if dat is not None:
        comparison = compare_map02(unpacked, dat)
        report["dat_comparison"] = {
            "dat_sha256": comparison["dat_sha256"],
            "dat_byte_count": len(dat),
            "matches_prior_dat_sha256": (
                len(dat) == PRIOR_DAT_LENGTH
                and comparison["dat_sha256"] == PRIOR_DAT_SHA256
            ),
            "difference_count": comparison["difference_count"],
            "differences": comparison["differences"],
            "target_faces": comparison["target_faces"],
            "matches_prior_disc_audit": comparison["matches_prior_disc_audit"],
            "matches_prior_disc_audit_with_provenance":
                comparison["matches_prior_disc_audit_with_provenance"],
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--disc-image", type=Path,
                       help="owned BIN/ISO image, read only")
    group.add_argument("--prs-file", type=Path,
                       help="previously extracted M_MAP02.PRS, read only")
    parser.add_argument("--layout", choices=("mode2-2352", "iso-2048"),
                        help="mandatory for --disc-image")
    parser.add_argument("--sector-bias", type=int, default=0,
                        help="track-relative sector adjustment; default 0 (not automatic)")
    dat_source = parser.add_mutually_exclusive_group()
    dat_source.add_argument("--dat-file", type=Path,
                            help="optional local M_MAP02.DAT to compare with PRS")
    dat_source.add_argument("--dat-from-disc", action="store_true",
                            help="read M_MAP02.DAT from same owned image at LBA 6999")
    parser.add_argument("--require-prior-provenance", action="store_true",
                        help="require archived compressed/decompressed PRS hashes and optional DAT hash")
    args = parser.parse_args()
    if args.disc_image is not None and args.layout is None:
        parser.error("--disc-image requires --layout")
    if args.prs_file is not None and (args.layout is not None or args.sector_bias):
        parser.error("--layout/--sector-bias only apply to --disc-image")
    if args.dat_from_disc and args.disc_image is None:
        parser.error("--dat-from-disc requires --disc-image")
    try:
        content = (read_sectors(args.disc_image, args.layout, args.sector_bias)
                   if args.disc_image is not None else args.prs_file.read_bytes())
        dat = args.dat_file.read_bytes() if args.dat_file is not None else None
        if args.dat_from_disc:
            dat = read_sectors(
                args.disc_image, args.layout, args.sector_bias,
                start_sector=DAT_START_SECTOR,
                sector_count=DAT_SECTOR_COUNT,
            )[:PRIOR_DAT_LENGTH]
        result = audit_prs(content, dat=dat)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    result["input_type"] = "disc_image" if args.disc_image is not None else "prs_file"
    if args.dat_from_disc:
        result["dat_source"] = "disc_image"
        result["dat_start_sector"] = DAT_START_SECTOR
        result["dat_sector_count"] = DAT_SECTOR_COUNT
        result["dat_mode2_form1_edc_verified_sectors"] = (
            DAT_SECTOR_COUNT if args.layout == "mode2-2352" else None
        )
    elif args.dat_file is not None:
        result["dat_source"] = "dat_file"
    if args.disc_image is not None:
        result["cd_table_start_sector"] = START_SECTOR
        result["sector_count"] = SECTOR_COUNT
        result["sector_bias"] = args.sector_bias
        result["layout"] = args.layout
        result["mode2_form1_edc_verified_sectors"] = (
            SECTOR_COUNT if args.layout == "mode2-2352" else None
        )
    print(json.dumps(result, indent=2))
    provenance_matches = (
        result["matches_prior_logical_compressed_sha256"]
        and result["matches_prior_decompressed_sha256"]
        and result["matches_prior_target_gfx"]
    )
    if dat is not None:
        provenance_matches = (
            provenance_matches and
            result["dat_comparison"]["matches_prior_disc_audit_with_provenance"]
            and result["dat_comparison"]["matches_prior_dat_sha256"]
        )
    return int(args.require_prior_provenance and not provenance_matches)


if __name__ == "__main__":
    raise SystemExit(main())
