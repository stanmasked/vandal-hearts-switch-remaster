#!/usr/bin/env python3
"""v149 synthetic-only MIPS-I subset, bounded stops, and original-only CLI."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_map02_v136_original_code_sections import (
    CODE_OFFSET, synthetic_with_exec_section,
)
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.run_map02_v149_bounded_guest import (
    LEAF, MAX_STEPS, SCHEMA, bounded_guest_probe,
)

PROGRAM = (
    0x3c088001, # LUI t0, 0x8001
    0x35083000, # ORI t0, t0, 0x3000 (safe RAM outside ELF text)
    0x2409002a, # ADDIU t1, zero, 42
    0xad090000, # SW t1, 0(t0)
    0x8d0a0000, # LW t2, 0(t0), one-cycle load delay
    0x254b0001, # ADDIU t3, t2, 1 (old t2)
    0x254c0001, # ADDIU t4, t2, 1 (new t2)
    0x118c0001, # BEQ t4, t4, +1
    0x240d0009, # ADDIU t5, zero, 9 (branch delay slot)
    0x0000000c, # SYSCALL refused before any host-side effect
)


def fixture(program=PROGRAM):
    exe, elf = synthetic_with_exec_section()
    encoded = struct.pack("<%dI" % len(program), *program)
    src = bytearray(exe)
    extracted = bytearray(elf)
    src[2048:2048 + len(encoded)] = encoded
    extracted[CODE_OFFSET:CODE_OFFSET + len(encoded)] = encoded
    return bytes(src), bytes(extracted)


class BoundedSyntheticGuest(unittest.TestCase):
    def setUp(self):
        self.exe, self.elf = fixture()

    def run_probe(self, *, exe=None, elf=None, limit=64):
        return bounded_guest_probe(
            self.exe if exe is None else exe,
            self.elf if elf is None else elf,
            require_original=False, max_steps=limit,
        )

    def test_synthetic_source_verified_instructions_really_step_and_trap(self):
        report = self.run_probe()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["edition"], "synthetic_fixture_only")
        self.assertEqual(report["steps_completed"], 9)
        self.assertEqual(report["loads_completed"], 1)
        self.assertEqual(report["stores_completed"], 1)
        self.assertEqual(report["stop_reason"], "unsupported_or_privileged_opcode")
        self.assertFalse(report["pending_branch_delay"])
        self.assertFalse(report["retail_runtime_authenticated"])
        self.assertFalse(report["original_map02_rendered"])
        self.assertFalse(report["bios_cd_gpu_services_executed"])
        self.assertFalse(report["nintendo_switch_hd_parity_verified"])

    def test_budget_is_bounded_and_reports_incomplete_delay_slot(self):
        for limit in (1, 3, 7, 8, 9, MAX_STEPS):
            with self.subTest(limit=limit):
                result = self.run_probe(limit=limit)
                self.assertLessEqual(result["steps_completed"], limit)
        at_branch = self.run_probe(limit=8)
        self.assertEqual(at_branch["steps_completed"], 8)
        self.assertEqual(at_branch["stop_reason"], "budget_ended_in_delay_slot")
        self.assertTrue(at_branch["pending_branch_delay"])
        at_slot = self.run_probe(limit=9)
        self.assertEqual(at_slot["steps_completed"], 9)
        self.assertEqual(at_slot["stop_reason"], "instruction_budget_reached")
        self.assertFalse(at_slot["pending_branch_delay"])

    def test_load_delay_and_branch_slot_change_final_register_digest(self):
        base = self.run_probe()
        without_load = (
            *PROGRAM[:4], 0x00000000, *PROGRAM[5:],
        )
        altered = self.run_probe(*(), exe=fixture(without_load)[0],
                                 elf=fixture(without_load)[1])
        self.assertNotEqual(base["registers_sha256"],
                            altered["registers_sha256"])
        without_branch_delay = (*PROGRAM[:8], 0, PROGRAM[9])
        changed_exe, changed_elf = fixture(without_branch_delay)
        changed = self.run_probe(exe=changed_exe, elf=changed_elf)
        self.assertNotEqual(base["registers_sha256"],
                            changed["registers_sha256"])

    def test_code_write_refused_before_mutating_memory(self):
        program = (PROGRAM[0], 0x35080000, PROGRAM[2], *PROGRAM[3:])
        exe, elf = fixture(program)
        stopped = self.run_probe(exe=exe, elf=elf)
        prior = self.run_probe(exe=exe, elf=elf, limit=3)
        self.assertEqual(stopped["steps_completed"], 3)
        self.assertEqual(stopped["stop_reason"], "verified_code_write_refused")
        self.assertEqual(stopped["guest_ram_sha256"],
                         prior["guest_ram_sha256"])

    def test_kseg1_alias_cannot_write_verified_kseg0_code(self):
        program = (0x3c08a001, 0x35080000, PROGRAM[2], *PROGRAM[3:])
        exe, elf = fixture(program)
        report = self.run_probe(exe=exe, elf=elf)
        self.assertEqual(report["stop_reason"], "verified_code_write_refused")
        self.assertEqual(report["stores_completed"], 0)

    def test_unmapped_mmio_and_unaligned_stores_trap_before_side_effect(self):
        for first, second, expected in (
            (0x3c081f80, 0x35081810, "unmapped_or_mmio_access"),
            (0x3c088001, 0x35083001, "unaligned_memory_access"),
        ):
            with self.subTest(expected=expected):
                program = (first, second, PROGRAM[2], *PROGRAM[3:])
                exe, elf = fixture(program)
                result = self.run_probe(exe=exe, elf=elf)
                self.assertEqual(result["steps_completed"], 3)
                self.assertEqual(result["stop_reason"], expected)
                self.assertEqual(result["stores_completed"], 0)

    def test_illegal_branch_in_delay_slot_traps(self):
        program = (*PROGRAM[:8], 0x10000001, PROGRAM[9])
        exe, elf = fixture(program)
        result = self.run_probe(exe=exe, elf=elf)
        self.assertEqual(result["stop_reason"], "control_inside_delay_slot")
        self.assertEqual(result["steps_completed"], 8)

    def test_tampered_executable_elf_pair_cannot_execute(self):
        altered = bytearray(self.elf)
        altered[CODE_OFFSET] ^= 1
        with self.assertRaises(Refused):
            self.run_probe(elf=bytes(altered))

    def test_retail_identity_and_invalid_budget_fail_closed(self):
        with self.assertRaises(Refused):
            bounded_guest_probe(self.exe, self.elf, require_original=True)
        for invalid in (0, MAX_STEPS + 1, True, -1, 1.0, "4"):
            with self.subTest(invalid=invalid), self.assertRaises(Refused):
                self.run_probe(limit=invalid)

    def test_cli_never_runs_public_synthetic_sources_as_original(self):
        with tempfile.TemporaryDirectory(prefix="vh149-private-") as temp:
            root = Path(temp)
            boot = root / "private-boot-plan.json"
            boot.write_text("{}\n")
            boot.chmod(0o600)
            destination = root / "output"
            destination.mkdir(mode=0o700)
            sources = []
            for name, data in (("private-us.exe", self.exe),
                               ("source-elf.elf", self.elf)):
                path = root / name
                path.write_bytes(data)
                path.chmod(0o600)
                sources.append(path)
            call = subprocess.run(
                [sys.executable, "-m", "tools.run_map02_v149_bounded_guest",
                 *map(str, sources), str(boot), str(destination),
                 "--max-steps", "16"],
                cwd=ROOT, capture_output=True, text=True, timeout=20,
                check=False,
            )
            self.assertEqual(call.returncode, 2)
            self.assertEqual(call.stdout, "")
            self.assertEqual(call.stderr.strip(),
                             "VH149_PRIVATE_BOUNDED_GUEST_PROBE_REFUSED")
            self.assertFalse((destination / LEAF).exists())
            for path in sources:
                self.assertNotIn(str(path), call.stderr)

    def test_ci_adds_synthetic_only_without_removing_native_pcsx_proofs(self):
        isolated = (ROOT / ".github/workflows/map02-v149-bounded-guest-probe.yml").read_text()
        original = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("test_map02_v149_bounded_guest.py", isolated)
        self.assertIn("no_retail_code_in_ci=1", isolated)
        self.assertIn("test_map02_v148_original_guest_boot.py", isolated)
        self.assertIn("for mode in 04 13 22 31 40; do", original)
        self.assertIn("VH147_NATIVE_BOUNDED_MMIO_PASS", original)


if __name__ == "__main__":
    unittest.main()
