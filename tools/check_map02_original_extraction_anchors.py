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


def _psx_loaded_extent(exe, exe_size):
    """Only declared PS-X load bytes count as original runtime image."""
    header = _read_at(exe, PSX_HEADER, 0)
    if len(header) != PSX_HEADER or header[:8] != b"PS-X EXE":
        raise ValueError("original US EXE does not have a full PS-X header")
    exe_load, payload_size = struct.unpack_from("<II", header, 0x18)
    if exe_load != LOAD_VRAM:
        raise ValueError("pinned US PS-X EXE has unexpected load VRAM")
    if (payload_size == 0 or payload_size > exe_size - PSX_HEADER or
            exe_load + payload_size > 0x100000000):
        raise ValueError("original PS-X executable has invalid load extent")
    return exe_load, payload_size


def compare_data_ranges(exe_path, elf_path):
    """Check source-pinned anchor bytes through stable file descriptors only."""
    with _stable_source(exe_path, "US PS-X EXE") as (exe, exe_size):
        with _stable_source(elf_path, "MIPS ELF") as (elf, elf_size):
            exe_load, payload_size = _psx_loaded_extent(exe, exe_size)
            end_of_image = exe_load + payload_size
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
                _, typ, flags, address, offset, size = struct.unpack_from(
                    "<IIIIII", info)
                # Only file-backed, loaded ELF sections can authenticate
                # original MIPS runtime data. Debug/metadata PROGBITS
                # sections are not valid source-image address evidence.
                if typ == 1 and (flags & 0x2) and size > 0:
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
                if (source_offset < PSX_HEADER or
                        address + length > end_of_image or
                        source_offset + length > exe_size):
                    raise ValueError("original US PS-X data extends past declared load image")
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



def compare_loaded_sections(exe_path, elf_path):
    """Compare ALL file-backed, allocated ELF sections inside the PS-X load image.

    This is deliberately separate from the three pinned data anchors. It
    checks the mapped sections it can find, not uncovered gaps, zero-fill
    sections, external allocations, or a matching source-level decompilation.
    Only aggregate counts leave this verifier; private bytes remain local.
    """
    with _stable_source(exe_path, "US PS-X EXE") as (exe, exe_size):
        with _stable_source(elf_path, "MIPS ELF") as (elf, elf_size):
            exe_load, payload_size = _psx_loaded_extent(exe, exe_size)
            end_of_image = exe_load + payload_size

            elf_header = _read_at(elf, 52, 0)
            if (len(elf_header) != 52 or elf_header[:6] != b"\x7fELF\x01\x01" or
                    struct.unpack_from("<H", elf_header, 18)[0] != 8):
                raise ValueError("extracted original MIPS ELF has invalid ELF32 header")
            shoff = struct.unpack_from("<I", elf_header, 32)[0]
            entsize, count = struct.unpack_from("<HH", elf_header, 46)
            if (shoff < 52 or entsize < 40 or not (1 <= count <= 512)
                    or shoff + entsize * count > elf_size):
                raise ValueError("original ELF section headers are invalid")
            # ELF32 e_phoff/e_phentsize/e_phnum describe another table of
            # metadata. Its bytes cannot masquerade as PS-X runtime data.
            phoff = struct.unpack_from("<I", elf_header, 28)[0]
            phentsize, phnum = struct.unpack_from("<HH", elf_header, 42)
            if phnum:
                if (phoff < 52 or phentsize < 32 or
                        phoff + phentsize * phnum > elf_size):
                    raise ValueError("original ELF program header table is invalid")
                phend = phoff + phentsize * phnum
            else:
                phoff = phend = 0

            mapped = []
            outside = 0
            for index in range(count):
                record = _read_at(elf, entsize, shoff + entsize * index)
                if len(record) != entsize:
                    raise ValueError("original ELF section header read incomplete")
                _, kind, flags, address, offset, size = struct.unpack_from(
                    "<IIIIII", record)
                if kind != 1 or not (flags & 0x2) or size == 0:
                    continue  # not initialized runtime bytes (e.g. .bss)
                if offset + size > elf_size or address + size > 0x100000000:
                    raise ValueError("original ELF loaded section has invalid bounds")
                # A mapped runtime section must contain actual file
                # payload, not byte aliases into its own ELF metadata.
                # That includes the optional program-header table.
                section_table_end = shoff + entsize * count
                if (offset < 52 or
                        (offset < section_table_end and
                         shoff < offset + size) or
                        (phnum and offset < phend and phoff < offset + size)):
                    raise ValueError(
                        "original ELF loaded section aliases ELF metadata")
                if address >= end_of_image or address + size <= exe_load:
                    outside += 1
                    continue
                if address < exe_load or address + size > end_of_image:
                    raise ValueError("original ELF loaded section crosses PS-X extent")
                mapped.append((address, address + size, offset))

            if not mapped:
                raise ValueError("original ELF has no mapped initialized PS-X sections")
            mapped.sort()
            total = 0
            previous_end = exe_load
            uncovered_spans = 0
            largest_uncovered_span = 0
            for begin, end, offset in mapped:
                if begin < previous_end:
                    raise ValueError("original ELF has overlapping allocated sections")
                if begin > previous_end:
                    uncovered_spans += 1
                    largest_uncovered_span = max(
                        largest_uncovered_span, begin - previous_end)
                previous_end = end
                length = end - begin
                for start in range(0, length, 65536):
                    chunk_size = min(65536, length - start)
                    original = _read_at(
                        exe, chunk_size, PSX_HEADER + begin - exe_load + start)
                    extracted = _read_at(elf, chunk_size, offset + start)
                    if (len(original) != chunk_size or
                            len(extracted) != chunk_size or
                            original != extracted):
                        raise ValueError(
                            "extracted ELF loaded section differs from original PS-X bytes")
                total += length
            if previous_end < end_of_image:
                uncovered_spans += 1
                largest_uncovered_span = max(
                    largest_uncovered_span, end_of_image - previous_end)
            # Gaps are measured in PS-X loaded-address order, not ELF
            # storage offsets: their positions remain private.
            if (uncovered_spans == 0) != (total == payload_size):
                raise ValueError("original ELF loaded coverage accounting inconsistent")
    return {
        "original_exe_and_mips_elf_loaded_sections_match": True,
        "original_allocated_sections_compared": len(mapped),
        "original_allocated_section_bytes_compared": total,
        # Lengths are aggregate counters only, never private addresses or
        # file contents. Sparse ELF coverage is allowed, but must not be
        # reported as full PS-X image authentication.
        "original_psx_loaded_payload_bytes": payload_size,
        "original_psx_loaded_bytes_not_covered_by_elf_sections":
            payload_size - total,
        "original_psx_loaded_payload_fully_covered": total == payload_size,
        "original_psx_uncovered_contiguous_spans": uncovered_spans,
        "original_psx_largest_uncovered_span_bytes": largest_uncovered_span,
        "unmapped_allocated_sections_not_authenticated": outside,
        "complete_matching_decomp_proven": False,
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
        result.update(compare_loaded_sections(
            args.original_psx_executable, args.original_extracted_mips_elf))
    except ValueError as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("private original extraction filesystem verification failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
