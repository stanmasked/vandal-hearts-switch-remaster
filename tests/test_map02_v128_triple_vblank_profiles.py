#!/usr/bin/env python3
"""Independent fail-closed metatests of genuine three-VBlank DMA splits."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]

from tools.make_map02_v127_variable_vblank_exe import build as old_build
from tools.make_map02_v128_triple_vblank_exe import build, MAGIC
from tools.apply_map02_v128_pcsx_rearmed import oracle_source, SPLITS
from tools.summarize_map02_v128_triple_vblank_profiles import (
    PROFILES,summarize_one,summarize_all
)
from tools.verify_map02_v82_native_trace import Refused

def marker(mode):
    a,b=PROFILES[mode]
    return (
        f"VH128_REAL_VBLANK_PROFILES_PASS mode={mode} gaps={a},0,{b},0 "
        "stages=4 dma=3 nodes=10 words=15 unai=5 intermediate=5 "
        "real_vblanks=3 four_back_gap=3 erased=1\n"
    )

class TripleVBlankProfiles(unittest.TestCase):
    def test_only_exe_tag_changes_from_previous_cpu_program(self):
        ours,stops,ops,starts,wait_pc=build()
        prior,old_stops,old_ops,old_starts,old_wait_pc=old_build()
        self.assertEqual(MAGIC,b"VH128SY!")
        self.assertEqual(len(ours),10240)
        self.assertEqual(ours[0x4c:0x54],MAGIC)
        self.assertEqual(prior[0x4c:0x54],b"VH127SY!")
        self.assertEqual(ours[:0x4c],prior[:0x4c])
        self.assertEqual(ours[0x54:],prior[0x54:])
        self.assertEqual((stops,ops,starts,wait_pc),
                         (old_stops,old_ops,old_starts,old_wait_pc))

    def test_native_oracle_checks_zero_one_two_three_without_host_forgery(self):
        _,stops,_,_,wait_pc=build()
        src=oracle_source(stops,wait_pc)
        for fragment in (
            "if(vh128_vblank_mode>=0)",
            'memcmp(tag,"VH128SY!",sizeof(tag))==0',
            "{0u,3u}, {1u,2u}, {2u,1u}, {3u,0u}",
            "vh128_adjacent_histograms[4][4]",
            "{3u,0u,0u,1u}, {2u,1u,1u,0u}",
            "{2u,1u,1u,0u}, {3u,0u,0u,1u}",
            "expected_total_edges[4]={3u,3u,3u,3u}",
            "return_gap[4]={3u,3u,3u,3u}",
            "gap<4u?",
            "vh78_vblank_observed_count!=before+edge+1u",
            "vh78_vblank_last_hsync==0u",
            "vh78_vblank_last_frame!=last_real_frame+1u",
            "spin_blocks<8000u",
            "vh116_get_gap_metrics(&gaps)",
            "quints.returned_to_four_back[return_gap[vh128_vblank_mode]]!=1u",
            "VH128_REAL_VBLANK_PROFILES_PASS mode=%u",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment,src)
        self.assertIn(f"psxRegs.pc=0x{wait_pc:08x}u;",src)
        self.assertNotIn("VH127_",src)
        self.assertNotIn("VH127SY!",src)
        self.assertNotIn("vh127_",src)
        self.assertNotIn("psxRegs.cycle =",src)
        self.assertNotIn("psxRegs.cycle+=",src)
        self.assertNotIn("vh115_vblank();",src)
        self.assertNotIn("GPU_writeDataMem(",src)
        self.assertNotRegex(src,r"(?m)^[ \t]*GPU_vBlank\s*\(")

    def test_four_splits_are_distinct_and_have_three_genuine_edges(self):
        self.assertEqual(PROFILES,((0,3),(1,2),(2,1),(3,0)))
        self.assertEqual(SPLITS,("03","12","21","30"))
        self.assertEqual([sum(p) for p in PROFILES],[3]*4)
        self.assertEqual({v for pair in PROFILES for v in pair},{0,1,2,3})
        reports=[summarize_one(marker(i),i) for i in range(4)]
        self.assertEqual([r["mode"] for r in reports],list(SPLITS))
        self.assertTrue(all(r["actual_dma2_linked_lists"]==3 for r in reports))
        self.assertTrue(all(r["native_four_back_return_gap"]==3 for r in reports))

    def test_fail_closed_swapped_missing_duplicate_wrong_gap_and_refusal(self):
        good=[marker(i) for i in range(4)]
        for wrong in (
            [],
            good[:3],
            [good[0],good[1],good[1],good[3]],
            [good[0]+good[0],*good[1:]],
            [good[0].replace("gaps=0,0,3,0","gaps=3,0,0,0"),*good[1:]],
            [good[0].replace("real_vblanks=3","real_vblanks=2"),*good[1:]],
            [good[0].replace("four_back_gap=3","four_back_gap=2"),*good[1:]],
            ["2026-10-18 VH128_GENUINE_EDGE_REFUSED phase=0\n"+good[0],*good[1:]],
            [good[0]+"VH127_GAP_TOTAL_REFUSED\n",*good[1:]],
            [good[0]+"VH125_DMA_CHAIN_REFUSED\n",*good[1:]],
            [good[0].replace("erased=1","erased=0"),*good[1:]],
        ):
            with self.subTest(wrong=wrong),self.assertRaises(Refused):
                summarize_all(wrong)

    def test_aggregate_contains_no_private_witness_data(self):
        report=summarize_all([marker(i) for i in range(4)])
        self.assertTrue(report["all_modes_verified"])
        self.assertTrue(report["all_intervals_0_1_2_3_exercised"])
        self.assertTrue(report["return_gap_three_verified_across_four_distinct_splits"])
        self.assertFalse(report["original_retail_MAP02_verified"])
        self.assertFalse(report["HD_replacement_approved"])
        public=json.dumps(report,sort_keys=True)
        for banned in ('"sha256":','"raw_vram":','"gpu_word":',
                       '"pixel_value":','"private_runtime_log":',"0x600000ff"):
            self.assertNotIn(banned,public)

    def test_pinned_workflow_verifies_each_process_and_private_journal(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for term in (
            "apply_map02_v128_pcsx_rearmed",
            "make_map02_v128_triple_vblank_exe",
            "for mode in 03 12 21 30; do",
            '"--vh128-vblank-$mode"',
            "VH128_REAL_VBLANK_PROFILES_PASS mode=",
            "summarize_map02_v128_triple_vblank_profiles",
            "v128-triple-real-vblank-profiles-summary.json",
            "sha256sum -c proof/private/native.sha256",
            "VH127_REAL_VBLANK_PROFILES_PASS mode=",
            "VH126_GENUINE_VBLANK_DMA_PASS stages=4",
        ):
            with self.subTest(term=term):
                self.assertIn(term,workflow)

if __name__=="__main__":
    unittest.main()
