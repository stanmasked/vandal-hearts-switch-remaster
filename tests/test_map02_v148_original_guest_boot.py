#!/usr/bin/env python3
"""Private PS-X original MIPS guest-load plan, only synthetic fixture in CI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v136_original_code_sections import (
    synthetic_with_exec_section,CODE_BYTES,
)
from tools.analyze_map02_v131_private_mips_mmio import Refused,RAM_BYTES
from tools.analyze_map02_v135_original_us_elf_pair import (
    PINNED_LOAD,PINNED_US_EXE_MD5,
)
from tools.prepare_map02_v148_original_guest_boot import (
    SCHEMA,MANIFEST_LEAF,derive_guest_boot_plan,
    prepare_private_original_boot_plan,read_private_boot_plan,
)


class NativeOriginalBootPreflight(unittest.TestCase):
    def setUp(self):
        self.exe,self.elf=synthetic_with_exec_section()

    def test_guest_ram_entry_and_elf_are_byte_identical(self):
        report=derive_guest_boot_plan(self.exe,self.elf,require_original=False)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["edition"],"synthetic_fixture_only")
        self.assertEqual(report["load_virtual"],PINNED_LOAD)
        self.assertEqual(report["verified_exec_sections"],1)
        self.assertEqual(report["verified_exec_words"],CODE_BYTES//4)
        self.assertEqual(report["ps1_ram_bytes"],RAM_BYTES)
        self.assertEqual(report["verified_source_data_anchors"],3)
        self.assertEqual(report["entry_instruction_sha256"],
            hashlib.sha256(self.exe[2048:2052]).hexdigest())
        self.assertEqual(report["text_sha256"],report["ram_load_sha256"])
        for key in ("retail_guest_code_executed","original_map02_rendered",
                    "disc_and_bios_runtime_ready",
                    "nintendo_switch_hd_parity_verified"):
            self.assertIs(report[key],False)

    def test_synthetic_cannot_pass_original_retail_gate(self):
        self.assertNotEqual(hashlib.md5(self.exe).hexdigest(),
                            PINNED_US_EXE_MD5)
        with self.assertRaises(Refused):
            derive_guest_boot_plan(self.exe,self.elf,require_original=True)

    def test_bad_load_entry_or_out_of_bounds_guest_ram_refused(self):
        for at,value in (
            (0x10,PINNED_LOAD-4),
            (0x10,PINNED_LOAD+CODE_BYTES+16),
            (0x18,PINNED_LOAD+4),
            (0x18,0x801ff000),
            (0x1c,RAM_BYTES+4),
            (0x10,0xa1000000),
        ):
            altered=bytearray(self.exe)
            struct.pack_into("<I",altered,at,value)
            with self.subTest(at=at,value=value),self.assertRaises(Refused):
                derive_guest_boot_plan(bytes(altered),self.elf,
                                       require_original=False)

    def test_corrupt_entry_instruction_and_extracted_code_refused(self):
        for target in ("exe","elf"):
            source=bytearray(self.exe)
            extracted=bytearray(self.elf)
            if target=="exe":
                source[2048]^=0x01
            else:
                extracted[0x800]^=0x01
            with self.subTest(target=target),self.assertRaises(Refused):
                derive_guest_boot_plan(bytes(source),bytes(extracted),
                                       require_original=False)

    def test_overlapping_invalid_bss_and_unmapped_gp_sp_refused(self):
        for field,value in (
            (0x28,PINNED_LOAD),
            (0x28,0xa01ffffc),
            (0x28,0x1f000000),
            (0x14,0x9f800000),
            (0x30,0x9f801000),
        ):
            altered=bytearray(self.exe)
            struct.pack_into("<I",altered,field,value)
            # BSS must have nonzero declared size for the address check.
            if field==0x28:
                struct.pack_into("<I",altered,0x2c,16)
            with self.subTest(field=field),self.assertRaises(Refused):
                derive_guest_boot_plan(bytes(altered),self.elf,
                                       require_original=False)

    def test_separate_nonoverlapping_bss_is_allowed_but_never_run(self):
        changed=bytearray(self.exe)
        struct.pack_into("<I",changed,0x28,0x801f0000)
        struct.pack_into("<I",changed,0x2c,64)
        result=derive_guest_boot_plan(bytes(changed),self.elf,
                                      require_original=False)
        self.assertEqual(result["bss_bytes"],64)
        self.assertIs(result["retail_guest_code_executed"],False)

    def test_public_cli_never_accepts_synthetic_retail_identity(self):
        with tempfile.TemporaryDirectory(prefix="vh148-private-cli-") as temp:
            root=Path(temp)
            output=root/"output"
            output.mkdir(mode=0o700)
            paths=[]
            for leaf,content in (("SYNTHETIC.EXE",self.exe),
                                 ("synthetic.elf",self.elf)):
                p=root/leaf
                p.write_bytes(content)
                p.chmod(0o600)
                paths.append(p)
            args=[sys.executable,"-m",
                  "tools.prepare_map02_v148_original_guest_boot",
                  *(str(p) for p in paths),str(output)]
            run=subprocess.run(args,cwd=ROOT,capture_output=True,
                               text=True,timeout=20,check=False)
            self.assertEqual(run.returncode,2)
            self.assertEqual(run.stdout,"")
            self.assertEqual(run.stderr.strip(),
                             "VH148_PRIVATE_ORIGINAL_BOOT_PLAN_REFUSED")
            for path in paths:
                self.assertNotIn(str(path),run.stderr)
            self.assertFalse((output/MANIFEST_LEAF).exists())

    def test_pure_stage_does_not_embed_game_bytes_or_source_paths(self):
        result=derive_guest_boot_plan(self.exe,self.elf,require_original=False)
        payload=json.dumps(result)
        self.assertNotIn("PS-X EXE",payload)
        self.assertNotIn("SLUS_004.47",payload)
        self.assertNotIn(str(PINNED_US_EXE_MD5),payload)
        self.assertNotIn("original_mips_pc_raw_bytes",payload)

    def test_no_symlink_ancestor_and_no_overwrite_manifest_creation(self):
        with tempfile.TemporaryDirectory(prefix="vh148-native-dir-") as root:
            d=Path(root)/"private"
            d.mkdir(mode=0o700)
            d.chmod(0o700)
            alias=Path(root)/"symlinked"
            alias.symlink_to(d,target_is_directory=True)
            # A synthetic EXE is always rejected before any output file.
            exe=Path(root)/"original-mock"
            elf=Path(root)/"extracted-mock"
            for p,data in ((exe,self.exe),(elf,self.elf)):
                p.write_bytes(data)
                p.chmod(0o600)
            with self.assertRaises(Refused):
                prepare_private_original_boot_plan(exe,elf,alias)
            self.assertFalse((d/MANIFEST_LEAF).exists())

    def test_ci_keeps_original_gate_private_and_existing_pcsx_green(self):
        full=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v148-original-guest-boot-plan.yml").read_text()
        for required in (
            "test_map02_v148_original_guest_boot.py",
            "prepare_map02_v148_original_guest_boot",
            "VH148_PRIVATE_ORIGINAL_BOOT_PLAN_REFUSED",
            "for mode in 04 13 22 31 40; do",
            "VH147_NATIVE_GENERIC_MMIO_SOURCE_BOUND_PASS",
            "path: proof/public/",
        ):
            self.assertIn(required,full)
        for required in (
            "test_map02_v148_original_guest_boot.py",
            "no_retail_exe_in_public_tests=1",
        ):
            self.assertIn(required,isolated)


if __name__=="__main__":
    unittest.main()
