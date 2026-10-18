#!/usr/bin/env python3
"""Local-only, read-only inventory of PS1 MIPS memory-mapped GPU/DMA writes.

Accept a PRIVATE user-owned PS-X EXE (for example an owned SLUS executable),
never a copyrighted input in CI. Only constant-propagated candidate SW
instruction counts may leave the process. This does not establish that those
instructions execute, use linked-list DMA, or belong to retail MAP02.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

MAX_EXE_BYTES = 4 * 1024 * 1024
HEADER_BYTES = 2048
RAM_BYTES = 2 * 1024 * 1024
MMIO = {
    0x1f8010a0: "dma2_madr",
    0x1f8010a4: "dma2_bcr",
    0x1f8010a8: "dma2_chcr",
    0x1f8010f0: "dma_dpcr",
    0x1f801810: "gpu_gp0",
    0x1f801814: "gpu_gp1",
}
NAME_ORDER = tuple(MMIO.values())
SCHEMA = "vh.map02.local-private-psx-mips-mmio-static-candidates.v1"


class Refused(ValueError):
    """Cannot safely characterize the supplied private executable."""


def _signed16(value):
    return value if value < 0x8000 else value - 0x10000


def _snapshot(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_mode, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _read_exact(fd, count):
    parts = []
    left = count
    while left:
        block = os.read(fd, min(1024 * 1024, left))
        if not block:
            raise Refused("private PS-X EXE truncated during protected read")
        parts.append(block)
        left -= len(block)
    return b"".join(parts)


def read_private_exe(path):
    """Same-inode, two-pass bounded private read; no path or hashes in output."""
    try:
        # Never wait for a writer on an attacker-supplied FIFO, or acquire a
        # controlling terminal from a character device. O_NONBLOCK is ignored
        # for normal regular-file reads; the existing fstat test still refuses
        # anything that is not a single-link private regular file.
        fd = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                     getattr(os, "O_CLOEXEC", 0) |
                     getattr(os, "O_NONBLOCK", 0) |
                     getattr(os, "O_NOCTTY", 0))
    except OSError:
        raise Refused("private PS-X EXE cannot be safely opened") from None
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or
                stat.S_IMODE(st.st_mode) & 0o077 or st.st_nlink != 1 or
                st.st_size < HEADER_BYTES + 4 or
                st.st_size > MAX_EXE_BYTES):
            raise Refused("private PS-X EXE owner, mode, link or size invalid")
        snapshot = _snapshot(st)
        first = _read_exact(fd, st.st_size)
        if _snapshot(os.fstat(fd)) != snapshot:
            raise Refused("private PS-X EXE changed during first read")
        os.lseek(fd, 0, os.SEEK_SET)
        second = _read_exact(fd, st.st_size)
        if (hashlib.sha256(first).digest() != hashlib.sha256(second).digest()
                or _snapshot(os.fstat(fd)) != snapshot):
            raise Refused("private PS-X EXE changed during two-pass read")
        return first
    except OSError:
        raise Refused("private PS-X EXE protected read failed") from None
    finally:
        os.close(fd)


def parse_psx_text(raw):
    """Validate native PS-X EXE structure; never return text in a report."""
    if (type(raw) is not bytes or len(raw) < HEADER_BYTES + 4 or
            len(raw) > MAX_EXE_BYTES or raw[:8] != b"PS-X EXE"):
        raise Refused("not a bounded PS-X EXE")
    entry, load, length = struct.unpack_from("<III", raw, 0x10)[0], (
        struct.unpack_from("<I", raw, 0x18)[0]), (
        struct.unpack_from("<I", raw, 0x1c)[0])
    if (length == 0 or length % 4 or load % 4 or entry % 4 or
            length > RAM_BYTES or HEADER_BYTES + length > len(raw) or
            (load & 0xe0000000) not in (0x80000000, 0xa0000000) or
            (entry & 0xe0000000) not in (0x80000000, 0xa0000000)):
        raise Refused("unsupported PS-X EXE load/entry/section bounds")
    physical_load = load & 0x1fffffff
    physical_entry = entry & 0x1fffffff
    if (physical_load + length > RAM_BYTES or
            not physical_load <= physical_entry < physical_load + length):
        raise Refused("PS-X EXE entry is outside bounded mapped code")
    if any(raw[HEADER_BYTES + length:]):
        raise Refused("unexpected nonzero data after declared PS-X EXE section")
    return raw[HEADER_BYTES:HEADER_BYTES + length]


def _destination_unknown(regs, reg):
    if reg:
        regs[reg] = None


def _known(regs, reg):
    return 0 if reg == 0 else regs[reg]


def _canonical_mmio(address):
    # Only ordinary PS1 kuseg/kseg0/kseg1 addresses; no inferred mirrors.
    if (address & 0xe0000000) not in (
            0x00000000, 0x80000000, 0xa0000000):
        return None
    return (address & 0x1fffffff) if (
        address & 0x1fffffff) in MMIO else None


def analyze_mips_text(text):
    """Conservative straight-line constants, reset at all control-flow edges.

    Data-embedded instruction coincidences are merely STATIC candidates;
    no claim about execution, branch reachability, MAP02 or native VRAM.
    """
    if type(text) is not bytes or len(text) == 0 or len(text) % 4:
        raise Refused("invalid four-byte MIPS instruction stream")
    counts = {name: 0 for name in NAME_ORDER}
    counts["dma2_linked_list_chcr_literal"] = 0
    regs = [None] * 32
    regs[0] = 0
    for (word,) in struct.iter_unpack("<I", text):
        if word == 0:  # MIPS NOP preserves all register constants.
            continue
        op = word >> 26
        rs = (word >> 21) & 31
        rt = (word >> 16) & 31
        imm = word & 0xffff
        value = _known(regs, rs)
        if op == 0x0f:  # LUI
            if rt: regs[rt] = imm << 16
        elif op == 0x0d:  # ORI
            if rt: regs[rt] = ((value | imm) & 0xffffffff) if (
                value is not None) else None
        elif op in (0x08, 0x09):  # ADDI, ADDIU
            if rt: regs[rt] = ((value + _signed16(imm)) & 0xffffffff) if (
                value is not None) else None
        elif op == 0x0c:  # ANDI
            if rt: regs[rt] = (value & imm) if value is not None else None
        elif op == 0x0e:  # XORI
            if rt: regs[rt] = (value ^ imm) if value is not None else None
        elif op == 0x2b:  # SW offset(base) = source, original MIPS opcode
            if value is not None:
                address = (value + _signed16(imm)) & 0xffffffff
                normalized = _canonical_mmio(address)
                if normalized in MMIO:
                    field = MMIO[normalized]
                    counts[field] += 1
                    if (field == "dma2_chcr" and
                            _known(regs, rt) == 0x01000401):
                        counts["dma2_linked_list_chcr_literal"] += 1
        elif op in (0x28, 0x29, 0x2a, 0x2e):  # Other stores: no GPR write.
            continue
        elif op in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
                    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37):
            _destination_unknown(regs, rt)  # Loads/atomic reads
        elif op == 0x00:
            rd = (word >> 11) & 31
            funct = word & 0x3f
            rhs = _known(regs, rt)
            if funct in (0x20, 0x21):  # ADD, ADDU
                if rd: regs[rd] = (value + rhs) & 0xffffffff if (
                    value is not None and rhs is not None) else None
            elif funct == 0x25:  # OR
                if rd: regs[rd] = (value | rhs) if (
                    value is not None and rhs is not None) else None
            elif funct in (0x08, 0x09):  # JR, JALR = control flow
                regs = [None] * 32
                regs[0] = 0
            else:
                # Other R instructions: conservative destination clobber.
                _destination_unknown(regs, rd)
        elif op in (0x02, 0x03, 0x01, 0x04, 0x05, 0x06, 0x07,
                    0x14, 0x15, 0x16, 0x17):  # Jump or conditional branch.
            regs = [None] * 32
            regs[0] = 0
        else:
            # Unknown instructions cannot preserve inferred register state.
            regs = [None] * 32
            regs[0] = 0
    return counts


def audit_private_exe(path):
    text = parse_psx_text(read_private_exe(path))
    counts = analyze_mips_text(text)
    return {
        "schema": SCHEMA,
        "input_kind": "local_private_user_owned_psx_exe",
        "candidate_sw_instruction_counts": counts,
        "analysis_kind": "linear_conservative_mips_static_candidate_inventory",
        "did_not_execute_mips": True,
        "did_not_extract_or_export_game_bytes": True,
        "candidate_mmio_not_proof_of_executed_dma": True,
        "retail_map02_scene_identity_verified": False,
        "retail_map02_gpu_rendering_verified": False,
        "physical_ps1_equivalence_verified": False,
        "nintendo_switch_hd_parity_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_psx_exe", type=Path)
    args = parser.parse_args()
    try:
        result = audit_private_exe(args.private_psx_exe)
    except (OSError, Refused, ValueError, struct.error):
        parser.exit(2, "VH131_PRIVATE_RETAIL_EXE_REFUSED\n")
    print(json.dumps(result,sort_keys=True,separators=(",",":")))


if __name__ == "__main__":
    main()
