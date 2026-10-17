#!/usr/bin/env python3
"""Regression cases for actual PS1 MIPS delay-slot static MMIO inference."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.analyze_map02_v131_private_mips_mmio import (
    analyze_mips_text as v131_analyze,Refused
)
from tools.analyze_map02_v132_mips_delay_slots import (
    SCHEMA,analyze_delay_aware_text,audit_private_exe
)
from tools.make_map02_v129_four_vblank_exe import build

def ins(*ops):
    return b"".join(struct.pack("<I",v) for v in ops)

def lui(rt,imm):return 0x3c000000|(rt<<16)|imm
def ori(rt,rs,imm):return 0x34000000|(rs<<21)|(rt<<16)|imm
def sw(rt,off,rs):return 0xac000000|(rs<<21)|(rt<<16)|(off&0xffff)
def lw(rt,off,rs):return 0x8c000000|(rs<<21)|(rt<<16)|(off&0xffff)
def branch(rs,rt=0,likely=False):
    return ((0x14 if likely else 0x04)<<26)|(rs<<21)|(rt<<16)|1

class MipsDelaySlotSafeCandidates(unittest.TestCase):
    def test_jump_delay_slot_has_original_known_base_not_false_negative(self):
        program=ins(lui(11,0x1f80),ori(11,11,0x1000),
                    lui(9,0x0100),ori(9,9,0x0401),
                    0x08004000,sw(9,0xa8,11),sw(9,0xa8,11))
        before=v131_analyze(program)
        now,metadata=analyze_delay_aware_text(program)
        self.assertEqual(before["dma2_chcr"],0)
        self.assertEqual(now["dma2_chcr"],1)
        self.assertEqual(now["dma2_linked_list_chcr_literal"],1)
        self.assertEqual(metadata["constant_proven_sw_in_delay_slots"],1)
        self.assertEqual(metadata["likely_conditional_sw_in_delay_slots"],0)
        self.assertEqual(metadata["control_flow_delay_slots"],1)

    def test_conditional_and_branch_likely_are_only_candidates(self):
        setup=(lui(11,0x1f80),ori(11,11,0x1000))
        for likely in (False,True):
            with self.subTest(likely=likely):
                words=ins(*setup,branch(3,2,likely),sw(0,0xa0,11),sw(0,0xa0,11))
                count,meta=analyze_delay_aware_text(words)
                self.assertEqual(count["dma2_madr"],1)
                self.assertEqual(meta["constant_proven_sw_in_delay_slots"],1)
                self.assertEqual(meta["likely_conditional_sw_in_delay_slots"],
                                 int(likely))

    def test_nop_delay_slot_clears_constants_afterward(self):
        counts,meta=analyze_delay_aware_text(ins(lui(11,0x1f80),
            ori(11,11,0x1000),0x08004000,0,sw(0,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],0)
        self.assertEqual(meta["control_flow_delay_slots"],1)

    def test_load_clobber_in_slot_no_sequential_propagation(self):
        count,meta=analyze_delay_aware_text(ins(lui(11,0x1f80),
            ori(11,11,0x1000),0x08004000,lw(11,0,8),sw(9,0xa8,11)))
        self.assertEqual(count["dma2_chcr"],0)
        self.assertEqual(meta["control_flow_delay_slots"],1)

    def test_jalr_link_register_no_spurious_constant(self):
        # MIPS JALR rd=11 overwrites $11 with return PC before the slot.
        jalr=(11<<11)|(4<<21)|0x09
        counts,meta=analyze_delay_aware_text(ins(lui(11,0x1f80),
            ori(11,11,0x1000),jalr,sw(0,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],0)
        self.assertEqual(meta["control_flow_delay_slots"],1)

    def test_ambiguous_control_transfer_inside_slot_is_not_inferred(self):
        counts,meta=analyze_delay_aware_text(ins(lui(11,0x1f80),
            ori(11,11,0x1000),0x08004000,0x08004001,sw(9,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],0)
        self.assertEqual(meta["ambiguous_control_in_delay_slot"],1)

    def test_truncated_delay_slot_and_unaligned_sections_refused(self):
        for raw in (ins(0x08004000),b"\x00",b"",ins(0x08004000,0x08004001)):
            with self.subTest(raw=raw),self.assertRaises(Refused):
                analyze_delay_aware_text(raw)

    def test_source_authored_mips_still_matches_proven_v129_three_dma(self):
        raw,_,_,_,_=build()
        # Zero-filled trailing section is a valid NOP sequence.
        program=raw[2048:]
        baseline=v131_analyze(program)
        current,meta=analyze_delay_aware_text(program)
        self.assertEqual(current,baseline)
        self.assertEqual(current["dma2_madr"],3)
        self.assertEqual(current["dma2_bcr"],3)
        self.assertEqual(current["dma2_chcr"],6)
        self.assertEqual(current["dma2_linked_list_chcr_literal"],3)
        self.assertGreaterEqual(meta["control_flow_delay_slots"],4)
        self.assertEqual(meta["constant_proven_sw_in_delay_slots"],0)
        self.assertEqual(meta["ambiguous_control_in_delay_slot"],0)

    def test_private_output_has_only_aggregate_candidates_and_explicit_limits(self):
        raw,_,_,_,_=build()
        with tempfile.TemporaryDirectory() as directory:
            private=Path(directory)/"owned.exe"
            private.write_bytes(raw)
            private.chmod(0o600)
            report=audit_private_exe(private)
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["candidate_sw_instruction_counts"]["dma2_madr"],3)
            self.assertTrue(report["did_not_execute_mips"])
            self.assertFalse(report["original_retail_MAP02_verified"])
            self.assertFalse(report["physical_PS1_verified"])
            self.assertFalse(report["HD_replacement_approved"])
            public=json.dumps(report)
            for secret in (str(private),"PS-X EXE","sha256","0x1f8010a8",
                           "program_bytes","raw_instructions","SLUS_004.47"):
                self.assertNotIn(secret,public)

    def test_new_ci_runs_actual_synthetic_exe_in_same_native_process_matrix(self):
        ci=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for token in (
            "test_map02_v132_mips_delay_slots.py",
            "analyze_map02_v132_mips_delay_slots",
            "VH132_NATIVE_DELAY_SLOT_STATIC_PASS",
            "for mode in 04 13 22 31 40; do",
            "v131-same-exe.sha256",
            "sha256sum -c proof/private/v131-same-exe.sha256",
            "VH129_REAL_VBLANK_PROFILES_PASS mode=",
        ):
            self.assertIn(token,ci)
        workflow=(ROOT/".github/workflows/map02-v132-mips-delay-slots.yml").read_text()
        self.assertIn("test_map02_v132_mips_delay_slots.py",workflow)
        self.assertIn("test_map02_v131_private_mips_mmio.py",workflow)

if __name__=="__main__":
    unittest.main()
