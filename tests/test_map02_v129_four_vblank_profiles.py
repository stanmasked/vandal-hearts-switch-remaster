#!/usr/bin/env python3
"""Independent four-real-VBlank five-split native MIPS DMA/Unai validation."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]

from tools.make_map02_v128_triple_vblank_exe import build as previous_build
from tools.make_map02_v129_four_vblank_exe import build, MAGIC
from tools.apply_map02_v129_pcsx_rearmed import oracle_source, SPLITS
from tools.summarize_map02_v129_four_vblank_profiles import (
    PROFILES,summarize_one,summarize_all
)
from tools.verify_map02_v82_native_trace import Refused

def marker(mode):
    a,b=PROFILES[mode]
    return (
        f"VH129_REAL_VBLANK_PROFILES_PASS mode={mode} gaps={a},0,{b},0 "
        "stages=4 dma=3 nodes=10 words=15 unai=5 intermediate=5 "
        "real_vblanks=4 four_back_gap=4 erased=1\n"
    )

class FourGenuineVblankMatrix(unittest.TestCase):
    def test_cpu_bytecode_is_identical_to_original_v128_except_header_tag(self):
        data,stops,ops,starts,wait_pc=build()
        prior,old_stops,old_ops,old_starts,old_wait_pc=previous_build()
        self.assertEqual(MAGIC,b"VH129SY!")
        self.assertEqual(len(data),10240)
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(prior[0x4c:0x54],b"VH128SY!")
        self.assertEqual(data[:0x4c],prior[:0x4c])
        self.assertEqual(data[0x54:],prior[0x54:])
        self.assertEqual((stops,ops,starts,wait_pc),
                         (old_stops,old_ops,old_starts,old_wait_pc))

    def test_five_real_emulator_vblank_profiles_and_native_histograms(self):
        _,stops,_,_,wait_pc=build()
        src=oracle_source(stops,wait_pc)
        for fragment in (
            "if(vh129_vblank_mode>=0)",
            'memcmp(tag,"VH129SY!",sizeof(tag))==0',
            "{0u,4u}, {1u,3u}, {2u,2u}, {3u,1u}, {4u,0u}",
            "vh129_adjacent_histograms[5][5]",
            "{3u,0u,0u,0u,1u}, {2u,1u,0u,1u,0u}",
            "{2u,0u,2u,0u,0u}, {2u,1u,0u,1u,0u}",
            "expected_total_edges[5]={4u,4u,4u,4u,4u}",
            "return_gap[5]={4u,4u,4u,4u,4u}",
            "vh129_vblank_mode>4",
            "gap<5u?",
            "vh78_vblank_observed_count!=before+edge+1u",
            "vh78_vblank_last_hsync==0u",
            "vh78_vblank_last_frame!=last_real_frame+1u",
            "spin_blocks<8000u",
            "vh115_get_metrics(&after_wait)",
            "vh116_get_gap_metrics(&gaps)",
            "quints.returned_to_four_back[return_gap[vh129_vblank_mode]]!=1u",
            "VH129_REAL_VBLANK_PROFILES_PASS mode=%u",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment,src)
        self.assertIn(f"psxRegs.pc=0x{wait_pc:08x}u;",src)
        self.assertNotIn("vh128_",src)
        self.assertNotIn("VH128_",src)
        self.assertNotIn("VH128SY!",src)
        self.assertNotIn("psxRegs.cycle =",src)
        self.assertNotIn("psxRegs.cycle+=",src)
        self.assertNotIn("vh115_vblank();",src)
        self.assertNotIn("GPU_writeDataMem(",src)
        self.assertNotRegex(src,r"(?m)^[ \t]*GPU_vBlank\s*\(")

    def test_exact_five_splits_and_upper_bound_four(self):
        self.assertEqual(PROFILES,((0,4),(1,3),(2,2),(3,1),(4,0)))
        self.assertEqual(SPLITS,("04","13","22","31","40"))
        self.assertEqual([sum(p) for p in PROFILES],[4]*5)
        self.assertEqual({v for pair in PROFILES for v in pair},set(range(5)))
        profiles=[summarize_one(marker(i),i) for i in range(5)]
        self.assertEqual([p["mode"] for p in profiles],list(SPLITS))
        self.assertTrue(all(p["native_four_back_return_gap"]==4 for p in profiles))
        self.assertTrue(all(p["actual_dma2_linked_lists"]==3 for p in profiles))

    def test_strict_fail_closed_missing_duplicate_swapped_invalid_or_refused(self):
        good=[marker(i) for i in range(5)]
        cases=(
            [],
            good[:4],
            [good[0],good[1],good[2],good[2],good[4]],
            [good[0]+good[0],*good[1:]],
            [good[0].replace("gaps=0,0,4,0","gaps=4,0,0,0"),*good[1:]],
            [good[0].replace("real_vblanks=4","real_vblanks=3"),*good[1:]],
            [good[0].replace("four_back_gap=4","four_back_gap=3"),*good[1:]],
            [good[0].replace("nodes=10","nodes=9"),*good[1:]],
            [good[0].replace("erased=1","erased=0"),*good[1:]],
            ["2026-10-18 VH129_GENUINE_EDGE_REFUSED phase=0\n"+good[0],*good[1:]],
            [good[0]+"VH128_GAP_HISTOGRAM_REFUSED\n",*good[1:]],
            [good[0]+"VH125_DMA_CHAIN_REFUSED\n",*good[1:]],
        )
        for wrong in cases:
            with self.subTest(wrong=wrong),self.assertRaises(Refused):
                summarize_all(wrong)
        with self.assertRaises(Refused):
            summarize_one(good[0],5)

    def test_private_safe_aggregate_has_no_raw_words_pixels_hashes(self):
        report=summarize_all([marker(i) for i in range(5)])
        self.assertTrue(report["all_modes_verified"])
        self.assertTrue(report["all_intervals_0_1_2_3_4_exercised"])
        self.assertTrue(report["native_four_back_return_gap_four_in_all_profiles"])
        self.assertFalse(report["original_retail_MAP02_verified"])
        self.assertFalse(report["HD_replacement_approved"])
        value=json.dumps(report,sort_keys=True)
        for forbidden in ('"sha256":','"raw_vram":','"gpu_word":',
                          '"pixel_value":','"private_runtime_log":',"0x600000ff"):
            self.assertNotIn(forbidden,value)

    def test_full_native_matrix_preserves_v126_v127_v128_proven_witnesses(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for term in (
            "apply_map02_v129_pcsx_rearmed",
            "make_map02_v129_four_vblank_exe",
            "for mode in 04 13 22 31 40; do",
            '"--vh129-vblank-$mode"',
            "VH129_REAL_VBLANK_PROFILES_PASS mode=",
            "summarize_map02_v129_four_vblank_profiles",
            "v129-four-real-vblank-profiles-summary.json",
            "sha256sum -c proof/private/native.sha256",
            "VH128_REAL_VBLANK_PROFILES_PASS mode=",
            "VH127_REAL_VBLANK_PROFILES_PASS mode=",
            "VH126_GENUINE_VBLANK_DMA_PASS stages=4",
        ):
            with self.subTest(term=term):
                self.assertIn(term,workflow)

if __name__=="__main__":
    unittest.main()
