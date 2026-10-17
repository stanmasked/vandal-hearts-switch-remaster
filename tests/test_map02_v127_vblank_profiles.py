#!/usr/bin/env python3
"""Independent genuine VBlank gap-matrix validation around MIPS GPU DMA."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from tools.make_map02_v126_vblank_dma_exe import build as previous_build
from tools.make_map02_v127_variable_vblank_exe import (
    build,START,MAGIC,HEADER_SIZE,SECTION_SIZE,WAIT_NOPS
)
from tools.apply_map02_v127_pcsx_rearmed import oracle_source
from tools.summarize_map02_v127_vblank_profiles import (
    PROFILES,summarize_one,summarize_all
)
from tools.verify_map02_v82_native_trace import Refused


def marker(mode):
    a,b=PROFILES[mode]
    return (
        f"VH127_REAL_VBLANK_PROFILES_PASS mode={mode} gaps={a},0,{b},0 "
        f"stages=4 dma=3 nodes=10 words=15 unai=5 intermediate=5 "
        f"real_vblanks={a+b} four_back_gap={a+b} erased=1\n"
    )


class TrueVblankMatrix(unittest.TestCase):
    def test_bytecode_identical_to_previous_experiment_except_exe_tag(self):
        data,stops,ops,starts,wait_pc=build()
        old,old_stops,old_ops,old_starts,old_wait_pc=previous_build()
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(old[0x4c:0x54],b"VH126SY!")
        self.assertEqual(len(data),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(stops,old_stops)
        self.assertEqual(starts,old_starts)
        self.assertEqual(ops,old_ops)
        self.assertEqual(wait_pc,old_wait_pc)
        self.assertEqual(data[:0x4c],old[:0x4c])
        self.assertEqual(data[0x54:],old[0x54:])
        self.assertEqual(struct.unpack_from("<I",data,0x10)[0],START)
        self.assertEqual(build(),(data,stops,ops,starts,wait_pc))

    def test_original_mips_wait_pad_retained_without_fake_cycles(self):
        data,stops,ops,starts,wait_pc=build()
        self.assertEqual(ops[-WAIT_NOPS-2:-2],(0,)*WAIT_NOPS)
        self.assertEqual(ops[-2],(2<<26)|((wait_pc>>2)&0x03ffffff))
        self.assertEqual(ops[-1],0)
        self.assertLess(wait_pc+4*(WAIT_NOPS+2),START+SECTION_SIZE)

    def test_native_oracle_generates_four_exact_cpu_only_vblank_profiles(self):
        _,stops,_,_,wait_pc=build()
        source=oracle_source(stops,wait_pc)
        for term in (
            "if(vh127_vblank_mode>=0)",
            'memcmp(tag,"VH127SY!",sizeof(tag))',
            "{0u,0u}, {1u,1u}, {0u,2u}, {2u,0u}",
            "{4u,0u,0u}, {2u,2u,0u}",
            "{3u,0u,1u}, {3u,0u,1u}",
            "vh127_boundary_targets[vh127_vblank_mode][phase]",
            "target=vh127_boundary_targets",
            "spin_blocks<8000u",
            "psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)",
            "vh78_vblank_observed_count==before+edge",
            "vh78_vblank_last_hsync==0u",
            "vh78_vblank_last_cycle<=cycle_before",
            "vh78_vblank_last_frame!=last_real_frame+1u",
            "vh115_get_metrics(&after_wait)",
            "after_wait.vblank_edges!=real_edges_seen",
            "vh116_get_gap_metrics(&gaps)",
            "vh127_adjacent_histograms[vh127_vblank_mode][gap]",
            "quints.returned_to_four_back[return_gap[vh127_vblank_mode]]!=1u",
            "vh115_sample_cache_erased()",
            "VH127_REAL_VBLANK_PROFILES_PASS mode=%u",
        ):
            with self.subTest(term=term):
                self.assertIn(term,source)
        self.assertNotIn("VH127_WAIT_PC;",source)
        self.assertNotIn("VH127_VARIABLE_DMA_PASS",source)
        self.assertIn(f"psxRegs.pc=0x{wait_pc:08x}u;",source)
        self.assertNotIn("psxRegs.cycle =",source)
        self.assertNotIn("psxRegs.cycle+=",source)
        self.assertNotRegex(source,r"(?m)^[ \t]*GPU_vBlank\s*\(")
        self.assertNotIn("vh115_vblank();",source)
        self.assertNotIn("GPU_writeDataMem(",source)

    def test_zero_wait_has_no_fake_edge_and_double_wait_is_bounded(self):
        _,stops,_,_,wait_pc=build()
        src=oracle_source(stops,wait_pc)
        self.assertIn("edge<target",src)
        self.assertIn("target=vh127_boundary_targets[vh127_vblank_mode][phase]",src)
        self.assertIn("spin_blocks<8000u",src)
        self.assertIn("vh78_vblank_observed_count!=before+edge+1u",src)
        self.assertIn("psxRegs.pc=resume_pc;",src)
        self.assertIn("vh127_vblank_mode>3",src)
        self.assertLess(src.index("if(vh125_dma_count!=phase+1u"),
                        src.index("if(phase<2u)"))
        self.assertLess(src.index("if(phase<2u)"),
                        src.index("vh125_dma_enabled=0;"))

    def test_one_exact_private_safe_result_for_each_mode(self):
        self.assertEqual(PROFILES,((0,0),(1,1),(0,2),(2,0)))
        for mode,(a,b) in enumerate(PROFILES):
            with self.subTest(mode=mode):
                report=summarize_one(marker(mode),mode)
                self.assertEqual(report["real_vblank_boundaries"],[a,b])
                self.assertEqual(report["native_post_handler_pair_gaps"],[a,0,b,0])
                self.assertEqual(report["real_vblank_events"],a+b)
                self.assertEqual(report["native_four_back_return_gap"],a+b)
                self.assertEqual(report["gpu_dma_node_visits"],10)
                self.assertEqual(report["unai_post_draw_observations"],5)

    def test_all_four_distinct_proven_profiles_required(self):
        result=summarize_all([marker(i) for i in range(4)])
        self.assertEqual(len(result["profiles"]),4)
        self.assertTrue(result["all_intervals_0_1_2_exercised"])
        self.assertTrue(result["no_host_injected_cycles_vblank_or_gpu_commands"])
        self.assertFalse(result["HD_replacement_approved"])
        serialized=json.dumps(result,sort_keys=True)
        for term in ('"private_runtime_log":','"raw_vram":',
                     '"gpu_word":','"pixel_value":','"sha256":',"0x600000ff"):
            self.assertNotIn(term,serialized)

    def test_strict_refusal_for_swapped_duplicate_missing_or_forged_marker(self):
        good=[marker(i) for i in range(4)]
        for bad in (
            [],
            good[:3],
            [good[0],good[1],good[1],good[3]],
            [good[0]+good[0],*good[1:]],
            ["VH127_GENUINE_EDGE_REFUSED phase=0\n"+good[0],*good[1:]],
            [good[0].replace("gaps=0,0,0,0","gaps=0,0,2,0"),*good[1:]],
            [*good[:2],good[2].replace("four_back_gap=2","four_back_gap=0"),
             good[3]],
            [*good[:3],good[3].replace("real_vblanks=2","real_vblanks=1")],
        ):
            with self.subTest(bad=bad),self.assertRaises(Refused):
                summarize_all(bad)

    def test_pinned_emulator_runs_all_four_modes_in_private_isolated_processes(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for token in (
            "apply_map02_v127_pcsx_rearmed",
            "make_map02_v127_variable_vblank_exe",
            "--vh127-vblank-00",
            "--vh127-vblank-11",
            "--vh127-vblank-02",
            "--vh127-vblank-20",
            "VH127_REAL_VBLANK_PROFILES_PASS mode=",
            "summarize_map02_v127_vblank_profiles",
            "v127-real-vblank-profiles-summary.json",
            "sha256sum -c proof/private/native.sha256",
            "VH126_GENUINE_VBLANK_DMA_PASS stages=4",
            "path: proof/public/",
        ):
            self.assertIn(token,workflow)


if __name__=="__main__":
    unittest.main()
