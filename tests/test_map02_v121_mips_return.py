#!/usr/bin/env python3
"""v121 genuine interpreter-submitted GP0 with bounded CPU-phase proof."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.make_map02_v121_mips_gp0_return_exe import (
    MAGIC,SECTION_SIZE,HEADER_SIZE,MARKERS,COLORS,
    EXPECTED_PIXELS,SETUP,RECT_XY,RECT_SIZE,START,
    build,stage_body,gpu_writes,
)
from tools.make_map02_v70_synthetic_psx_exe import lui,ori,sw
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v121_mips_return import summarize

PASS=("VH121_MIPS_GP0_RETURN_PASS stages=6 mips_rectangles=5 "
      "native_unai=5 readbacks=5 four_back=1 vblanks=0 erased=1\n")


class SyntheticMipsProgram(unittest.TestCase):
    def test_signed_psx_exe_and_bounded_load(self):
        data,stops,ops,starts=build()
        self.assertEqual(len(data),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(struct.unpack_from("<I",data,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",data,0x1c)[0],SECTION_SIZE)
        self.assertEqual(len(stops),6)
        self.assertEqual(starts[0],START)
        self.assertEqual(stops[:-1],starts[1:])
        self.assertEqual(tuple(struct.unpack_from("<"+str(len(ops))+"I",
                          data,HEADER_SIZE)),tuple(ops))
        self.assertEqual(build(),(data,stops,ops,starts))

    def test_every_rectangle_sent_by_mips_sw_to_gp0_register(self):
        _,_,ops,_=build()
        gp0_store=sw(9,0,8)
        cpu_marker_store=sw(9,0,10)
        self.assertEqual(ops.count(gp0_store),len(SETUP)+15)
        self.assertEqual(ops.count(cpu_marker_store),6)
        for phase,color in enumerate(COLORS):
            body=stage_body(phase+1)
            commands=(color,RECT_XY,RECT_SIZE)
            self.assertEqual(body[2:11],tuple(gpu_writes(commands)))
            self.assertEqual(body.count(gp0_store),3)
            self.assertNotIn(sw(9,4,8),body)
        self.assertNotIn(0,MARKERS)
        self.assertEqual(len(set(MARKERS)),6)

    def test_stage_zero_sets_gpu_draw_area_without_host_submission(self):
        body=stage_body(0)
        self.assertEqual(body[2:2+len(SETUP)*3],tuple(gpu_writes(SETUP)))
        self.assertEqual(tuple(EXPECTED_PIXELS),
                         (0x001f,0x03e0,0x7c00,0x03ff,0x001f))
        self.assertEqual(COLORS[0],COLORS[-1])
        self.assertEqual(len(set(COLORS[:4])),4)

    def test_cpu_markers_located_in_psx_ram(self):
        for stage in range(6):
            body=stage_body(stage)
            self.assertIn(lui(10,0x8001),body)
            self.assertIn(ori(10,10,0x1100+4*stage),body)
            self.assertEqual(body[-1],sw(9,0,10))

    def test_native_oracle_requires_mips_interpreter_and_vram_readback(self):
        src=(ROOT/"tools/apply_map02_v121_pcsx_rearmed.py").read_text()
        for token in (
            'memcmp(tag,"VH121SY!",sizeof(tag))==0',
            "Config.Cpu!=1","psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)",
            "vh121_marks[phase+1u]","vh121_stops[phase+1u]",
            "vh80_reset()","vh84_set_sampling(1)","vh115_enable(1)",
            "GPU_freeze(1,&freeze_state,&vram)",
            "vram[y*1024u+x]!=vh121_colors[phase]",
            "metrics.handlers!=phase+1u","metrics.vblank_edges!=0u",
            "five.returned_to_four_back[0]!=1u",
            "vh115_sample_cache_erased()",
        ):
            self.assertIn(token,src)
        self.assertNotIn("GPU_writeDataMem(",src)
        self.assertNotIn("GPU_writeData(",src)
        self.assertIn("apply_v120(root)",src)
        # GP0 MMIO CPU SW uses GPUwriteData's native buffered FIFO:
        # the MIPS setup must be flushed BEFORE enabling sample equality.
        self.assertIn("GPU_freeze(1,&setup_freeze,&setup_pixels)",src)
        self.assertLess(src.index("GPU_freeze(1,&setup_freeze,&setup_pixels)"),
                        src.index("vh80_reset();"))
        self.assertLess(src.index("vh80_reset();"),
                        src.index("vh115_enable(1);"))
        self.assertIn("VH121_SETUP_DRAIN_REFUSED",src)

    def test_aggregate_public_report_contains_no_mips_words_or_pixels(self):
        result=summarize(PASS)
        self.assertEqual(result["native_unai_handlers"],5)
        self.assertEqual(result["exact_four_back_returns"],1)
        self.assertTrue(result["mips_store_to_gp0_executed_in_emulator"])
        self.assertFalse(result["host_submitted_gpu_draw_commands_in_this_run"])
        self.assertFalse(result["HD_replacement_approved"])
        rendered=json.dumps(result,sort_keys=True)
        for forbidden in ("0x600000ff",'"raw_pixels":','"raw_gp0":',
                          "vram_address","private_event_jsonl"):
            self.assertNotIn(forbidden,rendered)

    def test_missing_duplicate_corrupted_or_failed_status_is_refused(self):
        bad=[
            "",PASS+PASS,"VH121_MIPS_SETUP_REFUSED\n"+PASS,
            PASS.replace("stages=6","stages=5"),
            PASS.replace("mips_rectangles=5","mips_rectangles=4"),
            PASS.replace("native_unai=5","native_unai=4"),
            PASS.replace("readbacks=5","readbacks=4"),
            PASS.replace("four_back=1","four_back=0"),
            PASS.replace("vblanks=0","vblanks=1"),
            PASS.replace("erased=1","erased=0"),
            "VH121_MIPS_GP0_RETURN_PASS stages=6\n",
        ]
        for sample in bad:
            with self.subTest(sample=sample),self.assertRaises(Refused):
                summarize(sample)

    def test_pinned_host_runs_separate_cpu_exe_and_keeps_private_jsonl(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v121_pcsx_rearmed",flow)
        self.assertIn("make_map02_v121_mips_gp0_return_exe",flow)
        self.assertIn("--vh121-mips-gp0-return-smoke",flow)
        self.assertIn("VH121_MIPS_GP0_RETURN_PASS stages=6",flow)
        self.assertIn("sha256sum -c proof/private/native.sha256",flow)
        self.assertIn("summarize_map02_v121_mips_return",flow)
        self.assertIn("v121-mips-gp0-return-summary.json",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
