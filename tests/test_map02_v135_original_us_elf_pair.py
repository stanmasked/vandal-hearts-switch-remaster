#!/usr/bin/env python3
"""Source-pinned original US retail identity and ELF section anchor regressions.

The public test pair is built from the already authored synthetic v129 MIPS EXE,
extended with *generated* deterministic anchor bytes. No original game data
are read or shipped to GitHub, and synthetic cannot pass the retail MD5 gate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.make_map02_v129_four_vblank_exe import build
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.analyze_map02_v135_original_us_elf_pair import (
    ANCHORS,ELF_MAX_BYTES,PINNED_US_EXE_MD5,PINNED_LOAD,SCHEMA,
    parse_loaded_mips_elf_sections,compare_original_data_anchors,
    read_private_elf,analyze_pinned_original_pair
)


def synthetic_exe():
    raw,*_=build()
    length=max(addr-PINNED_LOAD+size for _,addr,size in ANCHORS)
    code=bytearray(length)
    code[:len(raw)-2048]=raw[2048:]
    for index,(_,addr,size) in enumerate(ANCHORS):
        start=addr-PINNED_LOAD
        code[start:start+size]=bytes(
            (index*37+i*11+5)%256 for i in range(size))
    header=bytearray(raw[:2048])
    struct.pack_into("<I",header,0x1c,len(code))
    return bytes(header+code)


def synthetic_mips_elf(exe):
    shoff=0x80
    data=bytearray(0x300+1152)
    data[0:7]=b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHIIIIIHHHHHH",data,16,
        2,8,1,PINNED_LOAD,0,shoff,0,52,0,0,40,4,0)
    for i,(_,addr,size) in enumerate(ANCHORS):
        source=2048+addr-PINNED_LOAD
        target=0x200 if i==0 else 0x240 if i==1 else 0x300
        struct.pack_into("<IIIIIIIIII",data,shoff+(i+1)*40,
            0,1,0x2,addr,target,size,0,0,4,0)
        data[target:target+size]=exe[source:source+size]
    return bytes(data)


class OriginalUsElfAnchorBinding(unittest.TestCase):
    def test_pinned_original_source_anchors_and_legacy_selector(self):
        self.assertEqual(PINNED_US_EXE_MD5,
                         "596bb082a2de5f1fe977dd3d7e160b03")
        self.assertEqual(PINNED_LOAD,0x80010000)
        self.assertEqual(ANCHORS,(
            ("original_map32_data",0x801009bc,32),
            ("original_map35_data",0x80100e9c,32),
            ("original_ascii_font_bitmap",0x801012e4,128*9),
        ))
        # The original source-anchored parser must not claim full execution.
        source=(ROOT/"tools/analyze_map02_v135_original_us_elf_pair.py").read_text()
        for required in (
            '"extracted_mips_elf_full_code_equivalence_proven":False',
            '"actual_mips_instructions_executed":False',
            '"map02_gameplay_or_rendering_verified":False',
            '"physical_ps1_equivalence_verified":False',
            '"nintendo_switch_hd_parity_verified":False',
            '"game_bytes_or_private_hashes_exported":False',
            '"legacy_md5_is_not_collision_resistant_authentication":True',
        ):
            self.assertIn(required,source)

    def test_generated_anchor_bytes_match_own_synthetic_elf(self):
        exe=synthetic_exe()
        elf=synthetic_mips_elf(exe)
        self.assertNotEqual(hashlib.md5(exe).hexdigest(),PINNED_US_EXE_MD5)
        names=compare_original_data_anchors(exe,elf)
        self.assertEqual(names,[name for name,_,_ in ANCHORS])
        self.assertEqual(len(parse_loaded_mips_elf_sections(elf)),3)
        self.assertEqual(sum(length for _,_,length in ANCHORS),1216)

    def test_single_byte_anchor_mismatch_or_missing_section_fails(self):
        exe=synthetic_exe()
        elf=synthetic_mips_elf(exe)
        for index,(_,addr,size) in enumerate(ANCHORS):
            with self.subTest(anchor=index):
                corrupt=bytearray(elf)
                start=0x200 if index==0 else 0x240 if index==1 else 0x300
                corrupt[start+size-1]^=1
                with self.assertRaises(Refused):
                    compare_original_data_anchors(exe,bytes(corrupt))
        # Section header has valid bytes, but its allocated flag vanishes.
        corrupt=bytearray(elf)
        struct.pack_into("<I",corrupt,0x80+40+8,0)
        with self.assertRaises(Refused):
            compare_original_data_anchors(exe,bytes(corrupt))
        # A second allocated matching section makes the first anchor ambiguous.
        corrupt=bytearray(elf)
        struct.pack_into("<I",corrupt,0x80+2*40+12,ANCHORS[0][1])
        with self.assertRaises(Refused):
            compare_original_data_anchors(exe,bytes(corrupt))

    def test_header_region_and_mips_elf_architecture_fail_closed(self):
        exe=synthetic_exe()
        elf=synthetic_mips_elf(exe)
        wrong_load=bytearray(exe)
        struct.pack_into("<I",wrong_load,0x18,0x80020000)
        with self.assertRaises(Refused):
            compare_original_data_anchors(bytes(wrong_load),elf)
        for bad in (
            b"not an ELF file",
            elf[:51],
            elf[:0x80+40],
            elf[:4]+b"\x02"+elf[5:],
        ):
            with self.subTest(length=len(bad)),self.assertRaises(Refused):
                parse_loaded_mips_elf_sections(bad)
        alien=bytearray(elf)
        struct.pack_into("<H",alien,18,3) # not MIPS
        with self.assertRaises(Refused):
            compare_original_data_anchors(exe,bytes(alien))
        overflow=bytearray(elf)
        struct.pack_into("<I",overflow,0x80+40+20,len(elf)+1)
        with self.assertRaises(Refused):
            compare_original_data_anchors(exe,bytes(overflow))

    def test_private_elf_read_two_pass_and_nosymlink_ancestors(self):
        exe=synthetic_exe()
        raw=synthetic_mips_elf(exe)
        with tempfile.TemporaryDirectory(prefix="vh135-elf-") as tmp:
            directory=Path(tmp)
            good=directory/"actual"
            good.mkdir(mode=0o700)
            src=good/"synthetic-mips.elf"
            src.write_bytes(raw)
            src.chmod(0o600)
            self.assertEqual(read_private_elf(src),raw)
            src.chmod(0o644)
            with self.assertRaises(Refused):
                read_private_elf(src)
            src.chmod(0o600)
            alias=directory/"linked-parent"
            alias.symlink_to(good,target_is_directory=True)
            with self.assertRaises(Refused):
                read_private_elf(alias/src.name)
            alias.unlink()
            with self.assertRaises(Refused):
                read_private_elf(directory/"nothing.elf")
            self.assertEqual(read_private_elf(src),raw)

    def test_pinned_original_gate_refuses_valid_source_authored_synthetic_pair(self):
        exe=synthetic_exe()
        elf=synthetic_mips_elf(exe)
        with tempfile.TemporaryDirectory(prefix="vh135-private-") as tmp:
            root=Path(tmp)
            image=root/"SLUS_004.47"
            image.write_bytes(exe)
            image.chmod(0o600)
            extracted=root/"extracted-mips.elf"
            extracted.write_bytes(elf)
            extracted.chmod(0o600)
            self.assertEqual(read_private_elf(extracted),elf)
            with self.assertRaisesRegex(Refused,"pinned US retail selector"):
                analyze_pinned_original_pair(image,extracted)
            process=subprocess.run(
                [sys.executable,"-m","tools.analyze_map02_v135_original_us_elf_pair",
                 str(image),str(extracted)],
                cwd=ROOT,capture_output=True,text=True,timeout=15,check=False)
            self.assertEqual(process.returncode,2)
            self.assertEqual(process.stdout,"")
            self.assertEqual(process.stderr.strip(),
              "VH135_PRIVATE_ORIGINAL_MIPS_ELF_BINDING_REFUSED")
            self.assertNotIn(str(image),process.stderr)
            self.assertNotIn(str(extracted),process.stderr)

    def test_native_and_host_ci_remain_source_only(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v135-original-us-elf-gate.yml").read_text()
        for marker in ("test_map02_v135_original_us_elf_pair.py",
                       "test_map02_v134_dirfd_private_exe.py",
                       "test_map02_v133_nonblocking_private_exe.py"):
            self.assertIn(marker,native)
            self.assertIn(marker,standalone)
        self.assertIn("for mode in 04 13 22 31 40; do",native)
        self.assertIn("no_retail_psx_input_in_ci=1",standalone)
        self.assertNotIn("SLUS_004.47",standalone)


if __name__=="__main__":
    unittest.main()
