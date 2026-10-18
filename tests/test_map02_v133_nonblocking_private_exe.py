#!/usr/bin/env python3
"""Refuse nonregular private PS-X EXE inputs without blocking or leaking paths."""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.analyze_map02_v131_private_mips_mmio import (
    Refused,read_private_exe,audit_private_exe
)
from tools.analyze_map02_v132_mips_delay_slots import (
    audit_private_exe as audit_delay
)
from tools.make_map02_v129_four_vblank_exe import build


class PrivateExeNonblockingInputs(unittest.TestCase):
    def test_open_flags_no_symlinks_no_fifo_wait_no_terminal(self):
        from tools.analyze_map02_v131_private_mips_mmio import (
            _open_private_exe_dirfd
        )
        source=inspect.getsource(read_private_exe)
        safe_open=inspect.getsource(_open_private_exe_dirfd)
        for key in ("O_NOFOLLOW","O_CLOEXEC","O_NONBLOCK","O_NOCTTY",
                    "O_DIRECTORY","dir_fd=directory"):
            with self.subTest(flag=key):
                self.assertIn(key,safe_open)
        for key in ("_open_private_exe_dirfd(path)",
                    "os.fstat(fd)","stat.S_ISREG","st.st_nlink != 1",
                    "hashlib.sha256(first).digest()"):
            with self.subTest(guard=key):
                self.assertIn(key,source)

    def test_fifo_never_blocks_even_when_it_has_no_writer(self):
        if not hasattr(os,"mkfifo"):
            self.skipTest("POSIX FIFO creation unavailable")
        with tempfile.TemporaryDirectory(prefix="vh133-only-synthetic-") as root:
            fifo=Path(root)/"pretend_user_owned_exe"
            os.mkfifo(fifo,0o600)
            # Spawn a separate interpreter: removing O_NONBLOCK would
            # make the open(2) hang, and this test fails after 3 seconds
            # instead of wedging the entire GitHub Actions job.
            script=(
                "import sys\n"
                "from tools.analyze_map02_v131_private_mips_mmio "
                "import read_private_exe,Refused\n"
                "try:\n"
                "    read_private_exe(sys.argv[1])\n"
                "except Refused:\n"
                "    print('VH133_FIFO_REFUSED')\n"
                "    sys.exit(0)\n"
                "sys.exit(7)\n"
            )
            result=subprocess.run(
                [sys.executable,"-c",script,str(fifo)],
                cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,check=False,timeout=3)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout.strip(),"VH133_FIFO_REFUSED")
            self.assertNotIn(str(fifo),result.stdout+result.stderr)

    def test_v131_and_v132_cli_fail_closed_without_raw_paths(self):
        if not hasattr(os,"mkfifo"):
            self.skipTest("POSIX FIFO creation unavailable")
        with tempfile.TemporaryDirectory(prefix="vh133-private-") as root:
            fifo=Path(root)/"private_fifo"
            os.mkfifo(fifo,0o600)
            for module,token in (
                ("tools.analyze_map02_v131_private_mips_mmio",
                 "VH131_PRIVATE_RETAIL_EXE_REFUSED"),
                ("tools.analyze_map02_v132_mips_delay_slots",
                 "VH132_PRIVATE_MIPS_DELAY_SLOT_REFUSED"),
            ):
                with self.subTest(module=module):
                    outcome=subprocess.run(
                        [sys.executable,"-m",module,str(fifo)],cwd=ROOT,
                        text=True,capture_output=True,check=False,timeout=3)
                    self.assertEqual(outcome.returncode,2)
                    self.assertIn(token,outcome.stderr)
                    self.assertEqual(outcome.stdout,"")
                    self.assertNotIn(str(fifo),outcome.stderr)

    def test_existing_synthetic_regular_file_passes_two_pass_hash_and_both_audits(self):
        raw,_,_,_,_=build()
        with tempfile.TemporaryDirectory(prefix="vh133-synthetic-") as root:
            original=Path(root)/"only_source_authored_mips.exe"
            original.write_bytes(raw)
            original.chmod(0o600)
            self.assertTrue(stat.S_ISREG(original.stat().st_mode))
            self.assertEqual(read_private_exe(original),raw)
            a=audit_private_exe(original)
            b=audit_delay(original)
            self.assertEqual(a["candidate_sw_instruction_counts"],
                             b["candidate_sw_instruction_counts"])
            self.assertEqual(a["candidate_sw_instruction_counts"]["dma2_madr"],3)
            self.assertEqual(a["candidate_sw_instruction_counts"]["dma2_bcr"],3)
            self.assertEqual(a["candidate_sw_instruction_counts"]["dma2_chcr"],6)
            self.assertEqual(
                a["candidate_sw_instruction_counts"]["dma2_linked_list_chcr_literal"],3)
            self.assertFalse(a["retail_map02_scene_identity_verified"])
            self.assertFalse(b["original_retail_MAP02_verified"])

    def test_owned_directory_and_character_device_refuse(self):
        with tempfile.TemporaryDirectory(prefix="vh133-nonfile-") as root:
            with self.assertRaises(Refused):
                read_private_exe(root)
        if Path("/dev/null").exists():
            with self.assertRaises(Refused):
                read_private_exe("/dev/null")

    def test_pinned_emulator_runs_all_older_proofs_and_private_open_tests(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for part in (
            "test_map02_v133_nonblocking_private_exe.py",
            "test_map02_v132_mips_delay_slots.py",
            "test_map02_v131_private_mips_mmio.py",
            "check_map02_v130_native_bounds",
            "for mode in 04 13 22 31 40; do",
            "sha256sum -c proof/private/v131-same-exe.sha256",
            "VH132_NATIVE_DELAY_SLOT_STATIC_PASS",
        ):
            with self.subTest(part=part):
                self.assertIn(part,workflow)
        standalone=(ROOT/".github/workflows/map02-v133-nonblocking-private-exe.yml").read_text()
        for part in ("test_map02_v133_nonblocking_private_exe.py",
                     "test_map02_v132_mips_delay_slots.py",
                     "test_map02_v131_private_mips_mmio.py"):
            self.assertIn(part,standalone)


if __name__=="__main__":
    unittest.main()
