#!/usr/bin/env python3
"""v146 exact-inode native ELF launch: synthetic positive and path-race proof."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.check_map02_v145_native_build_binding import (
    prepare,MANIFEST_FILE,
)
from tools.run_map02_v146_verified_fd_native import (
    execute_exact_inode,_open_private_dirfd,_create_private_log,POSITIVE,NEGATIVE,
)


class VerifiedInodeNativeExec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix="vh146-binaries-",dir=ROOT)
        base=Path(cls.tmp.name)
        cls.older=base/"older"
        cls.newer=base/"newer"
        cc=os.environ.get("CC","cc")
        for path,label in ((cls.older,"OLDER"),(cls.newer,"NEWER")):
            c=path.with_suffix(".c")
            c.write_text(
                "#include <stdio.h>\n"
                "int main(int argc,char **argv) {"
                " puts(\"VH146_"+label+"_ACTUALLY_EXECUTED\"); return 0; }\n")
            p=subprocess.run(
                [cc,"-O1","-Wall","-Wextra","-Werror",str(c),"-o",str(path)],
                capture_output=True,text=True,timeout=35,check=False)
            if p.returncode:
                raise AssertionError("synthetic host ELF compilation refused")
            path.chmod(0o700)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmpdir=tempfile.TemporaryDirectory(prefix="vh146-run-",dir=ROOT)
        root=Path(self.tmpdir.name)
        self.root=root
        self.logdir=root/"protected-logs"
        self.logdir.mkdir(mode=0o700)
        self.logdir.chmod(0o700)
        self.mdir=root/"binding"
        self.mdir.mkdir(mode=0o700)
        self.mdir.chmod(0o700)
        self.external=root/"control"
        self.external.mkdir(mode=0o700)
        self.external.chmod(0o700)
        self.challenge=self.external/"challenge.hex"
        self.challenge.write_bytes(b"1d4f78a2e3b04c569ab87d2015ef0c36\n")
        self.challenge.chmod(0o600)
        self.binary=root/"native-host-elf"
        shutil.copyfile(self.older,self.binary)
        self.binary.chmod(0o700)
        self.assertTrue(prepare(self.binary,self.challenge,self.mdir))
        self.manifest=self.mdir/MANIFEST_FILE

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_kernel_executes_exact_verified_file_descriptor(self):
        logfile=self.logdir/"native.log"
        self.assertTrue(execute_exact_inode(
            self.binary,self.manifest,self.challenge,logfile,
            ("--synthetic-host-smoke",),timeout=15))
        self.assertEqual(logfile.stat().st_mode&0o777,0o600)
        self.assertIn(b"VH146_OLDER_ACTUALLY_EXECUTED",logfile.read_bytes())
        self.assertNotIn(b"VH146_NEWER_ACTUALLY_EXECUTED",logfile.read_bytes())

    def test_racing_path_swap_executes_pinned_inode_but_rejects_final_path(self):
        logfile=self.logdir/"race.log"
        def replace_after_verified_fd():
            self.binary.rename(self.root/"retired-old-inode")
            shutil.copyfile(self.newer,self.binary)
            self.binary.chmod(0o700)
        with self.assertRaises(Refused):
            execute_exact_inode(
                self.binary,self.manifest,self.challenge,logfile,("--synthetic-host-smoke",),
                timeout=15,prelaunch_hook=replace_after_verified_fd)
        # A post-verification pathname swap cannot force executing NEWER:
        # kernel actually executed the open old file descriptor.
        self.assertIn(b"VH146_OLDER_ACTUALLY_EXECUTED",logfile.read_bytes())
        self.assertNotIn(b"VH146_NEWER_ACTUALLY_EXECUTED",logfile.read_bytes())

    def test_same_content_new_inode_path_replacement_is_refused(self):
        logfile=self.logdir/"same-digest-new-inode.log"
        def replace_after_verified_fd():
            self.binary.rename(self.root/"retired")
            shutil.copyfile(self.older,self.binary)
            self.binary.chmod(0o700)
        with self.assertRaises(Refused):
            execute_exact_inode(self.binary,self.manifest,self.challenge,
                                logfile,("--synthetic-host-smoke",),timeout=15,
                                prelaunch_hook=replace_after_verified_fd)
        self.assertIn(b"VH146_OLDER_ACTUALLY_EXECUTED",logfile.read_bytes())

    def test_manifest_digest_and_private_challenge_changes_refused(self):
        self.challenge.write_bytes(b"0"*32+b"\n")
        with self.assertRaises(Refused):
            execute_exact_inode(self.binary,self.manifest,self.challenge,
                                self.logdir/"rejected.log",("--synthetic-host-smoke",),timeout=15)
        self.assertFalse((self.logdir/"rejected.log").exists())

    def test_no_overwrite_of_existing_private_log(self):
        existing=self.logdir/"already.log"
        existing.write_bytes(b"unchanged")
        existing.chmod(0o600)
        with self.assertRaises(Refused):
            execute_exact_inode(self.binary,self.manifest,self.challenge,
                                existing,("--synthetic-host-smoke",),timeout=15)
        self.assertEqual(existing.read_bytes(),b"unchanged")

    def test_symlinked_log_ancestor_and_mutable_parent_refused(self):
        alias=self.root/"alias"
        alias.symlink_to(self.logdir,target_is_directory=True)
        with self.assertRaises(Refused):
            _create_private_log(alias/"evil.log")
        unsafe=self.root/"mutable"
        unsafe.mkdir(mode=0o700)
        inner=unsafe/"private"
        inner.mkdir(mode=0o700)
        inner.chmod(0o700)
        unsafe.chmod(0o777)
        with self.assertRaises(Refused):
            _create_private_log(inner/"evil.log")
        unsafe.chmod(0o700)
        self.assertFalse((inner/"evil.log").exists())

    def test_symlinked_binary_path_or_unsafe_mode_refused(self):
        alias=self.root/"host-symlink"
        alias.symlink_to(self.binary)
        with self.assertRaises(Refused):
            execute_exact_inode(alias,self.manifest,self.challenge,
                                self.logdir/"symlink.log",("--synthetic-host-smoke",),timeout=15)
        self.binary.chmod(0o766)
        with self.assertRaises(Refused):
            execute_exact_inode(self.binary,self.manifest,self.challenge,
                                self.logdir/"mode.log",("--synthetic-host-smoke",),timeout=15)

    def test_timeout_bounds_and_extra_args_are_refused(self):
        for timeout in (0,-1,181,True,1.2):
            with self.subTest(timeout=timeout),self.assertRaises(Refused):
                execute_exact_inode(self.binary,self.manifest,self.challenge,
                                    self.logdir/"invalid.log",("--synthetic-host-smoke",),timeout=timeout)
        for args in (("",),("flag\x00leak",),(3,)):
            with self.subTest(args=args),self.assertRaises(Refused):
                execute_exact_inode(self.binary,self.manifest,self.challenge,
                                    self.logdir/"invalid.log",args,timeout=15)

    def test_explicitly_allow_only_synthetic_mips_native_cli_flags(self):
        self.assertIn("--vh129-vblank-04",POSITIVE)
        self.assertIn("--vh142-private-receipt",POSITIVE)
        self.assertEqual(NEGATIVE[-1],"--vh142-corrupt-receipt")
        self.assertNotIn("--vh146-original-retail",POSITIVE)
        proc=subprocess.run([
            sys.executable,"-m","tools.run_map02_v146_verified_fd_native",
            "--binary",str(self.binary),"--manifest",str(self.manifest),
            "--challenge",str(self.challenge),
            "--private-log",str(self.logdir/"denied.log"),
            "--","-novid","--vh146-original-retail"],
            cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,2)
        self.assertEqual(proc.stdout,"")
        self.assertEqual(proc.stderr.strip(),
                         "VH146_VERIFIED_FD_NATIVE_LAUNCH_REFUSED")

    def test_ci_checks_actual_pcsx_fd_run_without_changing_previous_modes(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v146-fd-native-launch.yml").read_text()
        for word in (
            "run_map02_v146_verified_fd_native",
            "VH146_VERIFIED_FD_NATIVE_LAUNCH_PASS",
            "VH145_NATIVE_BUILD_AND_RECEIPT_BOUND_PASS",
            "VH144_NATIVE_RUN_CHALLENGE_BOUND_PASS",
            "for mode in 04 13 22 31 40; do",
            "path: proof/public/",
        ):
            self.assertIn(word,workflow)
        for word in ("test_map02_v146_verified_fd_native.py",
                     "no_retail_exe_in_public_tests=1"):
            self.assertIn(word,isolated)


if __name__=="__main__":
    unittest.main()
