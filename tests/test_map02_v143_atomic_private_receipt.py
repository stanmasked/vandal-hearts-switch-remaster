#!/usr/bin/env python3
"""Atomic no-symlink native PCSX receipt publication regressions, synthetic."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from tools.apply_map02_v142_native_private_mmio_receipt import (
    native_private_receipt_code,patch_native_observer,
)
from tools.apply_map02_v143_atomic_private_receipt import (
    native_atomic_private_receipt_code,patch_native_writer,
)
from tools.apply_map02_v138_interpreter_pc import (
    native_probe_declarations,expected_pc_events,
)
from tools.apply_map02_v139_mips_word_stages import patch_v138_probe_c
from tools.apply_map02_v140_mmio_effects import patch_native_value_observer
from tools.check_map02_v143_atomic_receipt import sample_c


class AtomicReceiptNativeGuard(unittest.TestCase):
    def test_new_writer_replaces_exact_old_native_function_only(self):
        src=patch_native_observer(
            patch_native_value_observer(
                patch_v138_probe_c(
                    native_probe_declarations(expected_pc_events()))))
        newer=patch_native_writer(src)
        self.assertEqual(newer.count("vh142_capture(regs,addr,value)"),1)
        self.assertEqual(newer.count("vh142_events[vh142_count].pc=regs->pc-4u"),1)
        self.assertEqual(newer.count("vh142_write_receipt(const char *private_dir"),1)
        self.assertNotIn(
            'fd=openat(dirfd,VH142_RECEIPT_NAME,',newer)
        self.assertNotIn("vh143_open_verified_directory",src)
        self.assertIn("vh143_open_verified_directory",newer)
        self.assertIn("VH143_STAGING_NAME",newer)
        self.assertIn("linkat(dirfd,VH143_STAGING_NAME",newer)

    def test_atomic_publication_requires_complete_durable_receipt(self):
        src=native_atomic_private_receipt_code()
        for text in (
            "VH142_EXPECTED_EVENTS 19u",
            "vh142_count!=VH142_EXPECTED_EVENTS",
            "vh142_write_all(fd,line,(size_t)count)",
            "if(fsync(fd)!=0",
            "linkat(dirfd,VH143_STAGING_NAME",
            "dirfd,VH142_RECEIPT_NAME,0)",
            "if(fsync(dirfd)!=0)",
            "if(ok!=0 && published)",
            "unlinkat(dirfd,VH143_STAGING_NAME,0)",
            "O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600",
            "final_st.st_ino!=st.st_ino",
            "final_st.st_nlink!=2u",
        ):
            self.assertIn(text,src)
        self.assertNotIn('renameat(dirfd,',src)
        self.assertNotIn("GPU_writeData(",src)
        self.assertNotIn("psxRegs.cycle=",src)
        self.assertNotIn("SysPrintf(",src)

    def test_each_component_nofollow_and_permission_policy(self):
        src=native_atomic_private_receipt_code()
        for token in (
            "fd=open(\"/\",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)",
            "next=openat(fd,component,",
            "O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC",
            "count==1u && at[0]=='.'",
            "count==2u && at[0]=='.' && at[1]=='.'",
            "(st.st_mode&0022)!=0",
            "(st.st_mode&0777)!=0700",
            "st.st_uid!=geteuid()",
            "VH143_MAX_PRIVATE_PATH 4096u",
            "VH143_MAX_COMPONENT 255u",
        ):
            self.assertIn(token,src)

    def test_host_compiler_harness_checks_failure_controls(self):
        src=sample_c()
        self.assertIn("vh142_capture(&r,",src)
        self.assertIn("vh142_write_receipt(argv[2],0u)",src)
        self.assertIn('strcmp(argv[1],"accept")',src)
        self.assertIn('strcmp(argv[1],"refuse")',src)
        self.assertIn("vh143_open_verified_directory",src)

    def test_full_pinned_native_and_dedicated_ci_retained(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v143-atomic-private-receipt.yml").read_text()
        for required in (
            "apply_map02_v143_atomic_private_receipt",
            "check_map02_v143_atomic_receipt",
            "test_map02_v143_atomic_private_receipt.py",
            "VH143_COMPILED_ATOMIC_PRIVATE_RECEIPT_PASS",
            "VH142_NATIVE_PRIVATE_RECEIPT_PASS",
            "VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED",
            "VH142_PRIVATE_RECEIPT_DIR",
            "for mode in 04 13 22 31 40; do",
            "sha256sum -c proof/private/v131-same-exe.sha256",
            "path: proof/public/",
        ):
            self.assertIn(required,native)
        for required in (
            "test_map02_v143_atomic_private_receipt.py",
            "check_map02_v143_atomic_receipt",
            "no_retail_exe_in_public_tests=1",
        ):
            self.assertIn(required,isolated)

if __name__=="__main__":
    unittest.main()
