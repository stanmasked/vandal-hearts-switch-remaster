#!/usr/bin/env python3
"""v83 observer source/provenance tests, exclusively synthetic fixtures."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.verify_map02_v82_native_trace import validate,Refused
from tools.summarize_map02_v83_unai_vblank import summarize
from tools import apply_map02_v83_pcsx_rearmed as patch

def record(kind,seq,value,cycle,frame):
    return json.dumps(dict(kind=kind,seq=seq,value=value,cycle=cycle,frame=frame),separators=(",",":"))+"\n"

def sample():
    return "".join([
        record("gp1_mmio",1,0xe1000020,90,0),
        record("vblank",2,0,100,10),
        record("gp0_unai_handled",3,0xe1000020,0,0),
        record("gp0_unai_handled",4,0x600000ff,0,0),
        record("gp1_mmio",5,0x01000000,120,0),
        record("vblank",6,0,200,11),
        record("vblank",7,0,300,12),
        record("vblank",8,0,400,13),
    ]).encode("ascii")

class V83Test(unittest.TestCase):
    def test_renderer_events_separate_from_gp1_and_dma2(self):
        r=validate(sample())
        self.assertEqual(r["gp0_unai_handled"],2)
        self.assertEqual(r["vblank_edges"],4)
        self.assertEqual(r["gp1_mmio"],2)
        self.assertEqual(r["gpu_dma2_start"],0)
        self.assertFalse(r["original_retail_MAP02_verified"])
        self.assertFalse(r["HD_replacement_approved"])
    def test_exact_unai_dispatch_intervals(self):
        result=summarize(sample())
        self.assertEqual([v["unai_handler_events"] for v in result["between_vblanks"]],[2,0,0])
        self.assertEqual(result["before_first_vblank"],0)
        self.assertEqual(result["after_last_vblank"],0)
        self.assertFalse(result["commands_completed_pixel_change_verified"])
    def test_refuse_forged_renderer_cycle(self):
        parsed=[json.loads(x) for x in sample().decode().splitlines()]
        next(e for e in parsed if e["kind"]=="gp0_unai_handled")["cycle"]=100
        raw=("".join(json.dumps(e,separators=(",",":"))+"\\n" for e in parsed)).encode()
        with self.assertRaises(Refused):summarize(raw)
    def test_refuse_unrecognized_renderer_command(self):
        parsed=[json.loads(x) for x in sample().decode().splitlines()]
        command=next(e for e in parsed if e["kind"]=="gp0_unai_handled")
        command["value"]=0x10000000
        p=("".join(json.dumps(e,separators=(",",":"))+"\\n" for e in parsed)).encode()
        with self.assertRaises(Refused):validate(p)
    def test_refuse_unimplemented_unai_opcode_gaps(self):
        for command_byte in (0x44,0x47,0x54,0x57,0x6c,0x6f):
            with self.subTest(command_byte=command_byte):
                parsed=[json.loads(x) for x in sample().decode().splitlines()]
                next(e for e in parsed if e["kind"]=="gp0_unai_handled")["value"]=command_byte<<24
                raw=("".join(json.dumps(e,separators=(",",":"))+"\\n" for e in parsed)).encode()
                with self.assertRaises(Refused):summarize(raw)
    def test_refuse_asserted_renderer_frame(self):
        p=sample().replace(b'"cycle":0,"frame":0',b'"cycle":0,"frame":12',1)
        with self.assertRaises(Refused):validate(p)
    def test_refuse_bad_vblank_order(self):
        p=sample().replace(b'"cycle":200,"frame":11',b'"cycle":200,"frame":10')
        with self.assertRaises(Refused):validate(p)
    def test_opt_in_source_injects_after_switch(self):
        s=(ROOT/"tools/apply_map02_v83_pcsx_rearmed.py").read_text()
        self.assertIn("cmd == 0x02",s)
        self.assertIn("cmd >= 0xe1 && cmd <= 0xe6",s)
        self.assertIn("vh80_record(VH83_GP0_UNAI_HANDLED,le32_to_u32(*list),0,0)",s)
        self.assertIn("vh83_renderer_smoke && observed_unai==0",s)
        self.assertIn("original_retail_MAP02_verified=False",s)
    def test_cpp_abi_declares_c_linkage(self):
        s=(ROOT/"tools/map02_v80_native_timeline.h").read_text()
        self.assertIn('extern "C" {',s)
        self.assertIn("VH83_GP0_UNAI_HANDLED=4",s)
    def test_formatter_does_not_label_rendering_as_pixel_write(self):
        s=(ROOT/"tools/map02_v81_event_jsonl.c").read_text()
        self.assertIn('kind="gp0_unai_handled"',s)
        self.assertNotIn('kind="vram_write"',s)
    def test_unai_source_hook_is_scoped_to_specific_renderer(self):
        s=(ROOT/"tools/apply_map02_v83_pcsx_rearmed.py").read_text()
        self.assertIn("plugins/gpu_unai/gpulib_if.cpp",s)
        self.assertIn("Old renderer / skipped commands not recorded.",s)
        self.assertIn("native_vram_write_trace_verified=False",s)

if __name__=="__main__":unittest.main()
