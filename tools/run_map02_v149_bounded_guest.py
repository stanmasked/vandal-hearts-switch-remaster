#!/usr/bin/env python3
"""v149: bounded, RAM-only diagnostic subset of PS1 MIPS-I execution.

No BIOS, CD, interrupts, GPU, DMA or host syscalls are emulated. Public tests
use synthetic EXE/ELF only. The CLI requires the private original US edition
and a pre-existing v148 boot manifest; neither game bytes nor guest registers
are printed. A CPU subset probe is NOT a PCSX boot or MAP02 game execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import stat

from .analyze_map02_v131_private_mips_mmio import (
    RAM_BYTES, Refused, parse_psx_text, read_private_exe,
)
from .analyze_map02_v135_original_us_elf_pair import read_private_elf
from .analyze_map02_v136_original_code_sections import _elf_exec_sections
from .prepare_map02_v148_original_guest_boot import (
    derive_guest_boot_plan, read_private_boot_plan,
)
from .run_map02_v146_verified_fd_native import _open_private_dirfd
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,
)

SCHEMA = "vh.map02.private-bounded-mips-probe.v1"
LEAF = "vh149-bounded-mips-probe.json"
MAX_STEPS = 256
MAX_RECEIPT = 4096
MASK = 0xffffffff


class GuestTrap(Exception):
    """Expected, non-leaking bounded CPU probe stop."""


def signed(value):
    value &= MASK
    return value - 0x100000000 if value & 0x80000000 else value


def _phys(address, size, align=1):
    if (address & 0xe0000000) not in (0, 0x80000000, 0xa0000000):
        raise GuestTrap("unmapped_or_mmio_access")
    physical = address & 0x1fffffff
    if physical % align:
        raise GuestTrap("unaligned_memory_access")
    if physical + size > RAM_BYTES:
        raise GuestTrap("unmapped_or_mmio_access")
    return physical


def bounded_guest_probe(exe: bytes, elf: bytes, *, require_original=True,
                        max_steps=64):
    """Execute at most 256 supported MIPS-I instructions in disposable RAM.

    Any unsupported instruction, MMIO, executable write or invalid PC stops
    before its side effect. Branch delay slots and one-cycle load delays are
    modeled. No claim of complete PS1 instruction-set or timing accuracy.
    """
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
        raise Refused("invalid bounded MIPS step budget")
    plan = derive_guest_boot_plan(exe, elf, require_original=require_original)
    ram = bytearray(RAM_BYTES)
    image = parse_psx_text(exe)
    load = plan["load_virtual"] & 0x1fffffff
    ram[load:load + len(image)] = image
    ranges = [(start, end) for start, end, _ in _elf_exec_sections(elf)]
    pc = plan["entry_virtual"]
    gp, bss, bss_size, sp_base, sp_offset = struct.unpack_from(
        "<IIIII", exe, 0x14)[0], *struct.unpack_from("<IIII", exe, 0x28)
    regs = [0] * 32
    regs[28] = gp
    regs[29] = (sp_base + sp_offset) & MASK if sp_base else 0
    pending_branch = None
    pending_load = None
    steps = 0
    loads = 0
    stores = 0
    reason = "instruction_budget_reached"
    while steps < max_steps:
        if pc % 4 or not any(start <= pc and pc + 4 <= end
                              for start, end in ranges):
            reason = "fetch_outside_verified_text"
            break
        try:
            physical = _phys(pc, 4, 4)
            word = struct.unpack_from("<I", ram, physical)[0]
            op, rs, rt = (word >> 26), (word >> 21) & 31, (word >> 16) & 31
            rd, sh, fn, imm = (word >> 11) & 31, (word >> 6) & 31, word & 63, word & 65535
            src, rhs = regs[rs], regs[rt]
            offset = imm if imm < 0x8000 else imm - 0x10000
            write = None
            new_load = None
            store = None
            next_branch = None
            is_control = False
            if op == 0:
                if fn == 0 and rs == 0: write = (rd, (rhs << sh) & MASK)
                elif fn == 2 and rs == 0: write = (rd, rhs >> sh)
                elif fn == 3 and rs == 0: write = (rd, (signed(rhs) >> sh) & MASK)
                elif fn == 0x21: write = (rd, (src + rhs) & MASK)
                elif fn == 0x23: write = (rd, (src - rhs) & MASK)
                elif fn == 0x24: write = (rd, src & rhs)
                elif fn == 0x25: write = (rd, src | rhs)
                elif fn == 0x26: write = (rd, src ^ rhs)
                elif fn == 0x27: write = (rd, (~(src | rhs)) & MASK)
                elif fn == 0x2a: write = (rd, int(signed(src) < signed(rhs)))
                elif fn == 0x2b: write = (rd, int(src < rhs))
                elif fn in (8, 9) and rt == 0 and sh == 0:
                    is_control = True
                    next_branch = src
                    if fn == 9: write = (rd, (pc + 8) & MASK)
                else: raise GuestTrap("unsupported_or_privileged_opcode")
            elif op == 0x0f and rs == 0:
                write = (rt, imm << 16)
            elif op in (8, 9):
                value = signed(src) + offset
                if op == 8 and not -0x80000000 <= value <= 0x7fffffff:
                    raise GuestTrap("signed_arithmetic_overflow")
                write = (rt, value & MASK)
            elif op == 0x0c: write = (rt, src & imm)
            elif op == 0x0d: write = (rt, src | imm)
            elif op == 0x0e: write = (rt, src ^ imm)
            elif op == 0x0a: write = (rt, int(signed(src) < offset))
            elif op == 0x0b: write = (rt, int(src < (offset & MASK)))
            elif op in (2, 3):
                is_control = True
                next_branch = ((pc + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2)
                if op == 3: write = (31, (pc + 8) & MASK)
            elif op in (4, 5, 6, 7):
                is_control = True
                if op == 4: take = src == rhs
                elif op == 5: take = src != rhs
                elif op == 6 and rt == 0: take = signed(src) <= 0
                elif op == 7 and rt == 0: take = signed(src) > 0
                else: raise GuestTrap("unsupported_or_privileged_opcode")
                next_branch = ((pc + 4 + (offset << 2)) if take else pc + 8) & MASK
            elif op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2b):
                width = 1 if op in (0x20, 0x24, 0x28) else 2 if op in (0x21, 0x25, 0x29) else 4
                effective = (src + offset) & MASK
                pos = _phys(effective, width, width)
                if op in (0x28, 0x29, 0x2b):
                    if any(not (effective + width <= start or effective >= end)
                           for start, end in ranges):
                        raise GuestTrap("verified_code_write_refused")
                    store = (pos, rhs.to_bytes(4, "little")[:width])
                else:
                    value = int.from_bytes(ram[pos:pos + width], "little")
                    if op in (0x20, 0x21):
                        sign_bit = 1 << (width * 8 - 1)
                        if value & sign_bit: value -= 1 << (width * 8)
                    new_load = (rt, value & MASK)
            else:
                raise GuestTrap("unsupported_or_privileged_opcode")
            if is_control and pending_branch is not None:
                raise GuestTrap("control_inside_delay_slot")
            # Commit only after the complete instruction has passed checks.
            # Previous load commits after this instruction reads old registers;
            # its new GPR write takes priority over a delayed load to same GPR.
            if pending_load is not None and pending_load[0]:
                regs[pending_load[0]] = pending_load[1]
            if write is not None and write[0]:
                regs[write[0]] = write[1]
            if store is not None:
                pos, data = store
                ram[pos:pos + len(data)] = data
                stores += 1
            if new_load is not None: loads += 1
            pending_load = new_load
            steps += 1
            if pending_branch is not None:
                pc = pending_branch
                pending_branch = None
            else:
                pc = (pc + 4) & MASK
                if is_control: pending_branch = next_branch
            regs[0] = 0
        except GuestTrap as exc:
            reason = str(exc)
            break
    if steps == max_steps and pending_branch is not None:
        reason = "budget_ended_in_delay_slot"
    return {
        "schema": SCHEMA,
        "scope": "ram_only_mips_subset_not_pcsx_retail_boot",
        "edition": plan["edition"],
        "source_boot_plan_sha256": hashlib.sha256(
            json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "steps_completed": steps,
        "step_budget": max_steps,
        "loads_completed": loads,
        "stores_completed": stores,
        "stop_reason": reason,
        "pending_load_delay": pending_load is not None,
        "pending_branch_delay": pending_branch is not None,
        "registers_sha256": hashlib.sha256(struct.pack("<32I", *regs)).hexdigest(),
        "guest_ram_sha256": hashlib.sha256(ram).hexdigest(),
        "retail_runtime_authenticated": False,
        "original_map02_rendered": False,
        "bios_cd_gpu_services_executed": False,
        "nintendo_switch_hd_parity_verified": False,
    }


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def private_probe(exe_path, elf_path, boot_plan_path, output_directory,
                  *, max_steps=64):
    exe = read_private_exe(exe_path)
    elf = read_private_elf(elf_path)
    plan = derive_guest_boot_plan(exe, elf, require_original=True)
    if read_private_boot_plan(boot_plan_path) != plan:
        raise Refused("private v148 boot-plan witness changed")
    report = bounded_guest_probe(exe, elf, require_original=True,
                                 max_steps=max_steps)
    payload = _canonical(report)
    if len(payload) > MAX_RECEIPT:
        raise Refused("private bounded guest receipt oversize")
    directory = _open_private_dirfd(output_directory)
    fd = -1
    created = False
    committed = False
    try:
        fd = os.open(LEAF, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        created = True
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
            raise Refused("private probe receipt inode refused")
        at = 0
        while at < len(payload):
            size = os.write(fd, payload[at:])
            if size <= 0: raise Refused("private probe incomplete write")
            at += size
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.fsync(directory)
        if (read_private_exe(exe_path) != exe or
                read_private_elf(elf_path) != elf or
                read_private_boot_plan(boot_plan_path) != plan or
                read_private_exact_mmio_trace(
                    Path(output_directory) / LEAF) != payload):
            raise Refused("private probe inputs or result changed")
        committed = True
        return report
    except OSError:
        raise Refused("private probe receipt safely inaccessible") from None
    finally:
        if fd >= 0: os.close(fd)
        if created and not committed:
            try: os.unlink(LEAF, dir_fd=directory)
            except OSError: pass
        os.close(directory)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_original_us_exe", type=Path)
    p.add_argument("private_extracted_mips_elf", type=Path)
    p.add_argument("private_v148_boot_plan", type=Path)
    p.add_argument("private_output_directory", type=Path)
    p.add_argument("--max-steps", type=int, default=64)
    args = p.parse_args()
    try:
        private_probe(args.private_original_us_exe,
                      args.private_extracted_mips_elf,
                      args.private_v148_boot_plan, args.private_output_directory,
                      max_steps=args.max_steps)
    except (Refused, OSError, ValueError, TypeError, struct.error):
        p.exit(2, "VH149_PRIVATE_BOUNDED_GUEST_PROBE_REFUSED\n")
    print("VH149_PRIVATE_GUEST_PROBE_RECORDED "
          "retail_boot_authenticated=0 map02_rendered=0 "
          "private_guest_values_exported=0")


if __name__ == "__main__":
    main()
