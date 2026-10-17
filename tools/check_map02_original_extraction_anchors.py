#!/usr/bin/env python3
"""Private asset-free extraction witness for exact original US PS-X data.

For the original pinned SLUS_004.47.yaml, fixed PS-X header load address
0x80010000, and source-known data points, verify that an independently
extracted MIPS ELF has the *same bytes* as the byte-exact US PS-X EXE.
This checks selected original sections, not a complete matching decomp
or the generated assets/*.inc text format. No private bytes are logged.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import struct

LOAD_VRAM = 0x80010000
PSX_HEADER = 0x800
# Anchors are from pinned original SLUS_004.47.yaml + original source:
# maps/map_32 .data, maps/map_35 .data, core/text glyph bitmap array
ANCHORS = (
    ("original_map32_data", 0x801009bc, 32),
    ("original_map35_data", 0x80100e9c, 32),
    ("original_ascii_font_bitmap", 0x801012e4, 128 * 9),
)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _stable_source(path, category):
    """Keep one descriptor throughout each anchor comparison and audit its path."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("linked original extraction input rejected: " + category)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        # Do not disclose caller-owned filesystem paths in audit errors.
        raise ValueError("original extraction input unavailable: " + category) from None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_size <= 0):
            raise ValueError("original extraction input metadata invalid: " + category)
        identity = _identity(info)
        yield stream, info.st_size
        try:
            after = os.stat(path, follow_symlinks=False)
        except OSError:
            raise ValueError("original extraction input changed: " + category) from None
        if (_identity(after) != identity
                or _identity(os.fstat(stream.fileno())) != identity
                or not stat.S_ISREG(after.st_mode)):
            raise ValueError("original extraction input changed: " + category)


def _read_at(stream, length, offset):
    # pread retains the descriptor and avoids path reopens or seek races.
    return os.pread(stream.fileno(), length, offset)


def compare_data_ranges(exe_path, elf_path):
    """Check source-pinned anchor bytes through stable file descriptors only."""
    with _stable_source(exe_path, "US PS-X EXE") as (exe, exe_size):
        with _stable_source(elf_path, "MIPS ELF") as (elf, elf_size):
            header = _read_at(exe, PSX_HEADER, 0)
            if len(header) != PSX_HEADER or header[:8] != b"PS-X EXE":
                raise ValueError("original US EXE does not have a full PS-X header")
            exe_load = int.from_bytes(header[0x18:0x1c], "little")
            if exe_load != LOAD_VRAM:
                raise ValueError("pinned US PS-X EXE has unexpected load VRAM")
            elf_header = _read_at(elf, 52, 0)
            if (len(elf_header) < 52 or elf_header[:4] != bytes.fromhex("7f454c46")
                    or elf_header[4] != 1 or elf_header[5] != 1):
                raise ValueError("extracted original MIPS ELF is not ELF32 little-endian")
            if struct.unpack_from("<H", elf_header, 18)[0] != 8:
                raise ValueError("extracted ELF machine is not original PS1 MIPS")
            shoff = struct.unpack_from("<I", elf_header, 32)[0]
            entsize, count = struct.unpack_from("<HH", elf_header, 46)
            if shoff < 52 or entsize < 40 or not (1 <= count <= 512):
                raise ValueError("original ELF has invalid section header table")
            if shoff + entsize * count > elf_size:
                raise ValueError("original ELF section headers are truncated")
            sections = []
            for i in range(count):
                info = _read_at(elf, entsize, shoff + i * entsize)
                if len(info) != entsize:
                    raise ValueError("original ELF section headers are incomplete")
                _, typ, _, address, offset, size = struct.unpack_from(
                    "<IIIIII", info)
                if typ == 1 and size > 0:
                    if offset + size > elf_size:
                        raise ValueError("original ELF PROGBITS outside file")
                    sections.append((address, address + size, offset))
            evidence = []
            for key, address, length in ANCHORS:
                matched = [(first, offset) for first, end, offset in sections
                           if first <= address and address + length <= end]
                if len(matched) != 1:
                    raise ValueError("original MIPS ELF missing unique data section: " + key)
                first, offset = matched[0]
                source_offset = PSX_HEADER + address - LOAD_VRAM
                if source_offset < PSX_HEADER or source_offset + length > exe_size:
                    raise ValueError("original US PS-X data extends past executable")
                from_exe = _read_at(exe, length, source_offset)
                from_elf = _read_at(elf, length, offset + address - first)
                if (len(from_exe) != length or len(from_elf) != length
                        or from_exe != from_elf):
                    raise ValueError("extracted MIPS ELF differs from original PS-X data: " + key)
                evidence.append(key)
    return {
        "original_exe_and_mips_elf_data_anchors_match": True,
        "original_private_data_anchors_checked": evidence,
        "original_private_data_bytes_compared": sum(x[2] for x in ANCHORS),
        "complete_matching_decomp_proven": False,
        "generated_inc_tables_proven": False,
        "actual_gameplay_executed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_psx_executable", type=Path)
    parser.add_argument("original_extracted_mips_elf", type=Path)
    args = parser.parse_args()
    try:
        result = compare_data_ranges(args.original_psx_executable,
                                     args.original_extracted_mips_elf)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
