#!/usr/bin/env python3
"""Actual no-symlink ancestor directory tests for local PS1 MIPS EXE audit."""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.analyze_map02_v131_private_mips_mmio import (
    _open_private_exe_dirfd,read_private_exe,Refused,
    audit_private_exe as baseline_audit
)
from tools.analyze_map02_v132_mips_delay_slots import (
    audit_private_exe as delay_audit
)
from tools.make_map02_v129_four_vblank_exe import build


class ProtectedAncestorWalk(unittest.TestCase):
    def test_absolute_nosymlink_multiple_directory_components(self):
        raw,*_=build()
        with tempfile.TemporaryDirectory(prefix="vh134-real-") as temp:
            nested=Path(temp)/"nested"/"deep"
            nested.mkdir(parents=True,mode=0o700)
            target=nested/"synthetic_only.exe"
            target.write_bytes(raw)
            target.chmod(0o600)
            self.assertEqual(read_private_exe(target),raw)
            self.assertEqual(
                baseline_audit(target)["candidate_sw_instruction_counts"],
                delay_audit(target)["candidate_sw_instruction_counts"])

    def test_parent_and_final_symlinks_are_refused_without_following(self):
        raw,*_=build()
        with tempfile.TemporaryDirectory(prefix="vh134-symlink-") as temp:
            root=Path(temp)
            actual=root/"actual"
            actual.mkdir(mode=0o700)
            original=actual/"only_synthetic.exe"
            original.write_bytes(raw)
            original.chmod(0o600)
            parent_alias=root/"alias"
            parent_alias.symlink_to(actual,target_is_directory=True)
            endpoint_alias=root/"file-alias.exe"
            endpoint_alias.symlink_to(original)
            for bad in (parent_alias/original.name,endpoint_alias):
                with self.subTest(which="parent" if bad.parent==parent_alias else "leaf"):
                    with self.assertRaises(Refused):
                        read_private_exe(bad)
                    with self.assertRaises(Refused):
                        baseline_audit(bad)
                    with self.assertRaises(Refused):
                        delay_audit(bad)
            self.assertEqual(read_private_exe(original),raw)

    def test_ancestor_replacement_after_directory_open_stays_fd_bound(self):
        """Deterministic TOCTOU test: swap path after obtaining ancestor FD."""
        from unittest.mock import patch
        raw,*_=build()
        swapped=bytearray(raw)
        swapped[2048]^=1
        with tempfile.TemporaryDirectory(prefix="vh134-fd-race-") as temp:
            root=Path(temp)
            live=root/"live"
            saved=root/"pinned"
            diversion=root/"diversion"
            live.mkdir(mode=0o700)
            diversion.mkdir(mode=0o700)
            name="synthetic.exe"
            (live/name).write_bytes(raw)
            (live/name).chmod(0o600)
            (diversion/name).write_bytes(bytes(swapped))
            (diversion/name).chmod(0o600)
            genuine_open=os.open
            changed=[False]

            def swap_after_fd_open(path,flags,*args,**kwargs):
                fd=genuine_open(path,flags,*args,**kwargs)
                if (path=="live" and "dir_fd" in kwargs and
                        not changed[0]):
                    # The OS directory FD is already pinned to the real
                    # inode. Retargeting the textual name must not redirect
                    # the later leaf open into 'diversion'.
                    changed[0]=True
                    live.rename(saved)
                    live.symlink_to(diversion,target_is_directory=True)
                return fd

            with patch("os.open",side_effect=swap_after_fd_open):
                actual=read_private_exe(live/name)
            self.assertTrue(changed[0])
            self.assertEqual(actual,raw)
            self.assertNotEqual(actual,bytes(swapped))
            self.assertTrue(live.is_symlink())
            with self.assertRaises(Refused):
                read_private_exe(live/name)
            self.assertEqual(read_private_exe(saved/name),raw)

    def test_dotdot_and_dot_components_cannot_bypass_anchoring(self):
        raw,*_=build()
        with tempfile.TemporaryDirectory(prefix="vh134-traversal-") as temp:
            root=Path(temp)
            file=root/"fixture.exe"
            file.write_bytes(raw)
            file.chmod(0o600)
            # Preserve literal path strings, not Path.resolve() or sanitizing
            # normalization, so the reader can fail on traversal.
            for bad in (
                str(root)+"/../"+root.name+"/fixture.exe",
                str(root)+"/./fixture.exe",
                str(root)+"/nothing/../fixture.exe",
                "",
                ".",
                "..",
                "/",
                "./fixture.exe",
            ):
                with self.subTest(path_kind="traversal" if bad else "empty"):
                    with self.assertRaises(Refused):
                        read_private_exe(bad)
            self.assertEqual(read_private_exe(file),raw)

    def test_relative_path_without_dot_segments_stays_within_cwd_fd(self):
        raw,*_=build()
        with tempfile.TemporaryDirectory(prefix="vh134-relative-") as temp:
            root=Path(temp)
            file=root/"safe.exe"
            file.write_bytes(raw)
            file.chmod(0o600)
            before=Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(read_private_exe("safe.exe"),raw)
            finally:
                os.chdir(before)

    def test_closed_directory_fds_and_actual_absolute_regular_input(self):
        raw,*_=build()
        with tempfile.TemporaryDirectory(prefix="vh134-openfds-") as temp:
            root=Path(temp)
            directory=root/"a"/"b"
            directory.mkdir(parents=True,mode=0o700)
            original=directory/"original-synthetic.exe"
            original.write_bytes(raw)
            original.chmod(0o600)
            # Linux-only fd-count is a useful regression against one leaked
            # intermediate directory descriptor per audited MIPS image.
            proc_fds=Path("/proc/self/fd")
            before=len(list(proc_fds.iterdir())) if proc_fds.is_dir() else None
            for _ in range(16):
                self.assertEqual(read_private_exe(original),raw)
                with self.assertRaises(Refused):
                    _open_private_exe_dirfd(directory/"absent.exe")
            after=len(list(proc_fds.iterdir())) if proc_fds.is_dir() else None
            if before is not None:
                self.assertEqual(before,after)

    def test_production_cli_refuses_parent_symlink_with_no_path_leak(self):
        raw,*_=build()
        with tempfile.TemporaryDirectory(prefix="vh134-cli-") as temp:
            root=Path(temp)
            real=root/"real"
            real.mkdir(mode=0o700)
            target=real/"original-private.exe"
            target.write_bytes(raw)
            target.chmod(0o600)
            alias=root/"symbolic-parent"
            alias.symlink_to(real,target_is_directory=True)
            supplied=alias/target.name
            for module,marker in (
                ("tools.analyze_map02_v131_private_mips_mmio",
                 "VH131_PRIVATE_RETAIL_EXE_REFUSED"),
                ("tools.analyze_map02_v132_mips_delay_slots",
                 "VH132_PRIVATE_MIPS_DELAY_SLOT_REFUSED"),
            ):
                with self.subTest(module=module):
                    p=subprocess.run(
                        [sys.executable,"-m",module,str(supplied)],
                        cwd=ROOT,capture_output=True,text=True,
                        timeout=3,check=False)
                    self.assertEqual(p.returncode,2)
                    self.assertEqual(p.stdout,"")
                    self.assertIn(marker,p.stderr)
                    self.assertNotIn(str(supplied),p.stderr)

    def test_source_and_native_workflows_require_real_ancestor_refusals(self):
        safe=inspect.getsource(_open_private_exe_dirfd)
        for token in (
            "os.O_DIRECTORY","os.O_NOFOLLOW",
            "dir_fd=directory","os.close(directory)",
            'part in (".","..")', "os.O_NONBLOCK", "os.O_NOCTTY",
        ):
            self.assertIn(token,safe)
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("test_map02_v134_dirfd_private_exe.py",workflow)
        self.assertIn("test_map02_v133_nonblocking_private_exe.py",workflow)
        self.assertIn("for mode in 04 13 22 31 40; do",workflow)
        self.assertIn("sha256sum -c proof/private/v131-same-exe.sha256",workflow)
        ci=(ROOT/".github/workflows/map02-v134-dirfd-private-exe.yml").read_text()
        self.assertIn("test_map02_v134_dirfd_private_exe.py",ci)


if __name__=="__main__":
    unittest.main()
