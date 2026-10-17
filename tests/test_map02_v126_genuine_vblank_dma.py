#!/usr/bin/env python3
"""Real psxRcntUpdate VBlank events between three original MIPS DMA lists."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from tools.make_map02_v125_variable_gpu_dma_exe import build as v125_build,chain_entries
from tools.make_map02_v126_vblank_dma_exe import (
    build,MAGIC,START,HEADER_SIZE,SECTION_SIZE,WAIT_NOPS,
)
from tools.apply_map02_v126_pcsx_rearmed import oracle_source
from tools.summarize_map02_v126_genuine_vblank_dma import summarize
from tools.verify_map02_v82_native_trace import Refused

PASS=("VH126_GENUINE_VBLANK_DMA_PASS stages=4 dma=3 nodes=10 words=15 "
      "unai=5 intermediate=5 adjacent_gaps=1,0,1,0 "
      "real_vblanks=2 four_back_gap2=1 erased=1\n")


class GenuineVblankMipsDma(unittest.TestCase):
    def test_new_signed_exe_preserves_original_dma_stages(self):
        older,stops,ops,starts=v125_build()
        data,new_stops,all_ops,new_starts,wait_pc=build()
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(len(data),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(struct.unpack_from("<I",data,0x1c)[0],SECTION_SIZE)
        self.assertEqual(new_stops,stops)
        self.assertEqual(new_starts,starts)
        self.assertEqual(all_ops[:len(ops)],ops)
        self.assertEqual(wait_pc,START+4*len(ops))
        self.assertEqual(build(),(data,new_stops,all_ops,new_starts,wait_pc))

    def test_wait_pad_is_512_interpreted_nops_and_self_jump(self):
        old_ops=v125_build()[2]
        _,_,ops,_,wait_pc=build()
        self.assertEqual(ops[len(old_ops):len(old_ops)+WAIT_NOPS],
                         (0,)*WAIT_NOPS)
        self.assertEqual(ops[-2],(2<<26)|((wait_pc>>2)&0x03ffffff))
        self.assertEqual(ops[-1],0)
        self.assertEqual(wait_pc&3,0)
        self.assertLess(wait_pc+4*(WAIT_NOPS+2),START+SECTION_SIZE)
        self.assertEqual(len(ops)-len(old_ops),WAIT_NOPS+2)

    def test_original_1_2_2_dma_packets_remain_unchanged(self):
        self.assertEqual(chain_entries(0)[1][1]>>24,3)
        self.assertEqual(chain_entries(1)[1][1]>>24,6)
        self.assertEqual(chain_entries(2)[1][1]>>24,3)
        self.assertEqual(dict(chain_entries(2))[0x204],0x600000ff)
        self.assertEqual(len(build()[1]),4)

    def test_native_waits_on_genuine_emulator_vblank_only(self):
        _,stops,_,_,wait_pc=build()
        src=oracle_source(stops,wait_pc)
        for value in (
            "vh78_vblank_observed_count",
            "vh78_vblank_last_cycle",
            "vh78_vblank_last_frame",
            "vh78_vblank_last_hsync",
            "psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)",
            "psxRegs.pc=0x",
            "vh115_get_metrics(&between)",
            "between.vblank_edges!=phase+1u",
            "between.handlers!=cumulative_draws[phase]",
            "phase<2u","waits<8000u",
            "vh78_vblank_observed_count!=initial_vblank+phase+1u",
            "quints.returned_to_four_back[2]!=1u",
            "gap!=2u",
            "vh116_get_gap_metrics(&gaps)",
            "num!=(gap<2u?2u:0u)",
            'memcmp(tag,"VH126SY!",sizeof(tag))',
            "VH126_GENUINE_VBLANK_DMA_PASS",
        ):
            with self.subTest(value=value):
                self.assertIn(value,src)
        self.assertNotIn("psxRegs.cycle =",src)
        self.assertNotIn("psxRegs.cycle+=",src)
        self.assertNotIn("GPU_vBlank(",src)
        self.assertNotIn("vh115_vblank();",src)
        self.assertNotIn("vh80_record(",src)
        self.assertNotIn("GPU_writeDataMem(",src)

    def test_real_waits_are_between_first_second_and_third_dma(self):
        _,stops,_,_,wait_pc=build()
        src=oracle_source(stops,wait_pc)
        self.assertEqual(src.count("psxRegs.pc=0x"),1)
        self.assertIn("psxRegs.pc=next_dma_pc;",src)
        self.assertIn("phase<2u",src)
        self.assertIn("if(vh125_dma_count!=phase+1u",src)
        self.assertIn("vh125_dma_enabled=0",src)
        self.assertLess(src.index("if(vh125_dma_count!=phase+1u"),
                        src.index("if(phase<2u)"))
        self.assertLess(src.index("if(phase<2u)"),
                        src.index("vh125_dma_enabled=0"))
        self.assertIn("vh124_intermediate_seen!=cumulative_draws[phase]",src)

    def test_public_summary_is_strict_and_contains_no_private_data(self):
        result=summarize(PASS)
        self.assertEqual(result["gpu_dma2_linked_list_transfers"],3)
        self.assertEqual(result["real_emulator_vblank_callbacks"],2)
        self.assertEqual(result["sampled_vram_transition_gaps"],[1,0,1,0])
        self.assertEqual(result["native_v119_five_handler_return_gap"],2)
        self.assertEqual(result["native_four_back_return_in_gap2"],1)
        self.assertFalse(result["physical_PS1_verified"])
        self.assertFalse(result["HD_replacement_approved"])
        wire=json.dumps(result,sort_keys=True)
        for forbidden in ('"raw_gpu_words":','"pixel_value":','"sha256":',
                          "0x600000ff","private_jsonl","vram_address"):
            self.assertNotIn(forbidden,wire)

    def test_native_report_refuses_wrong_gaps_or_spoofed_vblank(self):
        attempts=(
            "",PASS+PASS,
            "VH126_REAL_VBLANK_REFUSED phase=0\n"+PASS,
            PASS.replace("dma=3","dma=2"),
            PASS.replace("nodes=10","nodes=11"),
            PASS.replace("words=15","words=14"),
            PASS.replace("unai=5","unai=4"),
            PASS.replace("intermediate=5","intermediate=4"),
            PASS.replace("adjacent_gaps=1,0,1,0","adjacent_gaps=0,0,0,0"),
            PASS.replace("adjacent_gaps=1,0,1,0","adjacent_gaps=0,1,1,0"),
            PASS.replace("real_vblanks=2","real_vblanks=1"),
            PASS.replace("four_back_gap2=1","four_back_gap2=0"),
            PASS.replace("erased=1","erased=0"),
            "VH126_GENUINE_VBLANK_DMA_PASS stages=4 dma=3\n",
        )
        for item in attempts:
            with self.subTest(item=item),self.assertRaises(Refused):
                summarize(item)

    def test_ci_uses_isolated_pinned_emulator_and_unmodified_journal(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for value in (
            "apply_map02_v126_pcsx_rearmed",
            "make_map02_v126_vblank_dma_exe",
            "--vh126-mips-vblank-dma-smoke",
            "VH126_GENUINE_VBLANK_DMA_PASS stages=4",
            "summarize_map02_v126_genuine_vblank_dma",
            "v126-genuine-vblank-dma-summary.json",
            "VH125_VARIABLE_DMA_PASS stages=4",
            "sha256sum -c proof/private/native.sha256",
            "path: proof/public/",
        ):
            self.assertIn(value,flow)

if __name__=="__main__":
    unittest.main()
