#!/usr/bin/env python3
"""Self-authored PS-X+ELF32 MIPS code/data separation and full-code mismatch tests."""
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

from test_map02_v135_original_us_elf_pair import synthetic_exe,synthetic_mips_elf
from tools.analyze_map02_v131_private_mips_mmio import Refused,parse_psx_text
from tools.analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text
from tools.analyze_map02_v135_original_us_elf_pair import (
    ANCHORS,PINNED_LOAD,PINNED_US_EXE_MD5,compare_original_data_anchors
)
from tools.analyze_map02_v136_original_code_sections import (
    SCHEMA,_elf_exec_sections,original_code_sections,
    compare_static_code_candidate_counts,analyze_source_verified_pair
)

CODE_OFFSET=0x800
CODE_BYTES=8192
SHOFF=0x80
TEXT_HEADER=SHOFF+4*40

def synthetic_with_exec_section():
    exe=synthetic_exe()
    elf=bytearray(synthetic_mips_elf(exe))
    elf.extend(b"\x00"*(CODE_OFFSET+CODE_BYTES-len(elf)))
    struct.pack_into("<H",elf,48,5)  # ELF32 section count
    struct.pack_into("<IIIIIIIIII",elf,TEXT_HEADER,
        0,1,0x6,PINNED_LOAD,CODE_OFFSET,CODE_BYTES,0,0,4,0)
    elf[CODE_OFFSET:CODE_OFFSET+CODE_BYTES]=exe[2048:2048+CODE_BYTES]
    return exe,bytes(elf)


class ByteExactExecutableMipsCode(unittest.TestCase):
    def test_only_executable_elf_sections_are_scanned(self):
        exe,elf=synthetic_with_exec_section()
        self.assertEqual(compare_original_data_anchors(exe,elf),
                         [name for name,_,_ in ANCHORS])
        self.assertEqual(_elf_exec_sections(elf),
                         [(PINNED_LOAD,PINNED_LOAD+CODE_BYTES,CODE_OFFSET)])
        extracted=original_code_sections(exe,elf)
        self.assertEqual(extracted,[exe[2048:2048+CODE_BYTES]])
        sections,words,candidates,delays=compare_static_code_candidate_counts(exe,elf)
        self.assertEqual((sections,words),(1,CODE_BYTES//4))
        self.assertEqual(candidates["dma2_madr"],3)
        self.assertEqual(candidates["dma2_bcr"],3)
        self.assertEqual(candidates["dma2_chcr"],6)
        self.assertEqual(candidates["dma2_linked_list_chcr_literal"],3)
        self.assertEqual(candidates["dma_dpcr"],1)
        self.assertGreater(candidates["gpu_gp0"],0)
        self.assertEqual(delays["constant_proven_sw_in_delay_slots"],0)

    def test_changed_instruction_refused_even_if_all_data_anchors_match(self):
        exe,elf=synthetic_with_exec_section()
        changed=bytearray(elf)
        changed[CODE_OFFSET+16]^=1
        self.assertEqual(compare_original_data_anchors(exe,bytes(changed)),
                         [name for name,_,_ in ANCHORS])
        with self.assertRaises(Refused):
            original_code_sections(exe,bytes(changed))
        with self.assertRaises(Refused):
            compare_static_code_candidate_counts(exe,bytes(changed))

    def test_data_bytes_imitating_dma_sw_are_never_classified_as_code(self):
        exe,elf=synthetic_with_exec_section()
        source=bytearray(exe)
        extracted=bytearray(elf)
        pos=2048+ANCHORS[0][1]-PINNED_LOAD
        # LUI $11,0x1f80; ORI $11,$11,0x1000; SW $zero,0xa8($11).
        fake=struct.pack("<III",0x3c0b1f80,0x356b1000,0xad6000a8)
        source[pos:pos+len(fake)]=fake
        extracted[0x200:0x200+len(fake)]=fake
        source=bytes(source)
        extracted=bytes(extracted)
        self.assertEqual(len(compare_original_data_anchors(source,extracted)),3)
        _,_,verified,delays=compare_static_code_candidate_counts(source,extracted)
        _,raw=analyze_delay_aware_text(parse_psx_text(source))
        all_counts,_=analyze_delay_aware_text(parse_psx_text(source))
        self.assertEqual(verified["dma2_chcr"],6)
        self.assertGreater(all_counts["dma2_chcr"],verified["dma2_chcr"])
        self.assertFalse(delays["ambiguous_control_in_delay_slot"])

    def test_missing_text_section_or_bogus_executable_flags_refuse(self):
        exe,elf=synthetic_with_exec_section()
        for offset,value in (
            (TEXT_HEADER+8,0x2), # loaded data, not executable
            (TEXT_HEADER+4,8), # NOBITS, not backed by bytes
            (TEXT_HEADER+8,4), # SHF_EXECINSTR without SHF_ALLOC
            (TEXT_HEADER+12,3), # unaligned text address
            (TEXT_HEADER+16,CODE_OFFSET+1), # unaligned file offset
            (TEXT_HEADER+20,CODE_BYTES-1), # unaligned byte length
            (TEXT_HEADER+16,len(elf)+4), # text outside ELF
            (TEXT_HEADER+12,PINNED_LOAD-4), # maps before PS-X load
        ):
            with self.subTest(offset=offset,value=value):
                changed=bytearray(elf)
                struct.pack_into("<I",changed,offset,value)
                with self.assertRaises(Refused):
                    original_code_sections(exe,bytes(changed))
        # Mislabeling source-pinned original MAP32 data as executable is refused.
        changed=bytearray(elf)
        struct.pack_into("<I",changed,SHOFF+40+8,0x6)
        with self.assertRaises(Refused):
            original_code_sections(exe,bytes(changed))

    def test_duplicate_or_overlapping_executable_sections_refused(self):
        exe,elf=synthetic_with_exec_section()
        duplicate=bytearray(elf)
        struct.pack_into("<H",duplicate,48,6)
        struct.pack_into("<IIIIIIIIII",duplicate,SHOFF+5*40,
            0,1,0x6,PINNED_LOAD+16,CODE_OFFSET+16,64,0,0,4,0)
        with self.assertRaises(Refused):
            original_code_sections(exe,bytes(duplicate))

    def test_retained_real_us_gate_rejects_artificial_exe_without_disclosure(self):
        exe,elf=synthetic_with_exec_section()
        self.assertNotEqual(hashlib.md5(exe).hexdigest(),PINNED_US_EXE_MD5)
        with tempfile.TemporaryDirectory(prefix="vh136-private-fixture-") as temp:
            root=Path(temp)
            game=root/"private-user-input.exe"
            extracted=root/"only-generated-code.elf"
            game.write_bytes(exe)
            game.chmod(0o600)
            extracted.write_bytes(elf)
            extracted.chmod(0o600)
            with self.assertRaisesRegex(Refused,"selector"):
                analyze_source_verified_pair(game,extracted)
            result=subprocess.run([
                sys.executable,"-m",
                "tools.analyze_map02_v136_original_code_sections",
                str(game),str(extracted)],
                cwd=ROOT,capture_output=True,text=True,timeout=15,check=False)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,"")
            self.assertEqual(result.stderr.strip(),
                             "VH136_ORIGINAL_MIPS_CODE_SECTION_REFUSED")
            self.assertNotIn(str(game),result.stderr)
            self.assertNotIn(str(extracted),result.stderr)

    def test_original_evidence_limit_flags_and_all_legacy_suites_remain(self):
        source=(ROOT/"tools/analyze_map02_v136_original_code_sections.py").read_text()
        for field in (
            '"full_original_executable_code_equivalence_proven":False',
            '"instruction_reachability_or_execution_proven":False',
            '"original_map02_gameplay_or_rendering_verified":False',
            '"physical_ps1_equivalence_verified":False',
            '"switch_hd_graphics_parity_verified":False',
            '"game_bytes_or_private_hashes_exported":False',
            "read_private_exe(exe_path)!=exe",
            "read_private_elf(elf_path)!=elf",
            "compare_original_data_anchors(exe,elf)",
        ):
            self.assertIn(field,source)
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v136-original-code-sections.yml").read_text()
        for required in (
            "test_map02_v136_original_code_sections.py",
            "test_map02_v135_original_us_elf_pair.py",
            "test_map02_v134_dirfd_private_exe.py",
            "test_map02_v133_nonblocking_private_exe.py",
        ):
            self.assertIn(required,native)
            self.assertIn(required,standalone)
        self.assertIn("for mode in 04 13 22 31 40; do",native)
        self.assertIn("no_real_game_data_in_ci=1",standalone)


if __name__=="__main__":
    unittest.main()
