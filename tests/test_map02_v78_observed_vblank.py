#!/usr/bin/env python3
"""v78 source-anchored real VBlank event, MIPS clock and VRAM regressions."""
from __future__ import annotations
import hashlib
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v78_vblank_mips_exe import (
    build,main,MAGIC,HEADER,SECTION_SIZE,WAIT_NOPS,
    PHASE_GP0,PHASE_GP1,EXPECTED_REGS,expected_pixel,START
)
from tools.make_map02_v77_gpu_multiphase_exe import build as build_v77
from tools.apply_map02_v78_pcsx_rearmed import oracle_source,vblank_hook

class V78SourceVblank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe,cls.stop,cls.start,cls.wait,cls.ops=build()
        cls.v77,cls.v77stop,cls.v77ops,cls.v77start=build_v77()
        cls.native=oracle_source(cls.stop,cls.wait)
    def test_exe_10k_full_load(self):
        self.assertEqual(len(self.exe),HEADER+SECTION_SIZE)
        self.assertEqual(self.exe[:8],b"PS-X EXE")
    def test_exe_only_original_synthetic_marker(self):
        self.assertEqual(self.exe[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH78SYN!")
        self.assertNotIn(b"Vandal Hearts",self.exe)
    def test_8k_load_segment(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x1c)[0],SECTION_SIZE)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x18)[0],START)
    def test_stacks_match_v77(self):
        self.assertEqual(self.exe[0x30:0x34],self.v77[0x30:0x34])
    def test_cpu_four_stage_locations_unchanged(self):
        self.assertEqual(self.stop,self.v77stop)
        self.assertEqual(self.start,self.v77start)
    def test_mips_phase_bodies_preserved_exactly(self):
        self.assertEqual(self.ops[:len(self.v77ops)],self.v77ops)
    def test_wait_code_separate_from_four_stages(self):
        self.assertEqual(self.wait,START+len(self.v77ops)*4)
        self.assertGreater(self.wait,self.stop[-1])
    def test_512_real_cpu_noop_instructions(self):
        self.assertEqual(self.ops[len(self.v77ops):len(self.v77ops)+WAIT_NOPS],
                         (0,)*WAIT_NOPS)
    def test_wait_jump_to_same_address(self):
        self.assertEqual(self.ops[-2],(2<<26)|((self.wait>>2)&0x3ffffff))
        self.assertEqual(self.ops[-1],0)
    def test_mips_wait_code_fits_bounded_memory(self):
        self.assertLessEqual(len(self.ops)*4,SECTION_SIZE)
    def test_exact_four_gp1_phase_semantics(self):
        self.assertEqual(PHASE_GP1,(0x01000000,None,0x01000000,0))
    def test_e1_e2_e6_expected_reset_after_phase3(self):
        self.assertEqual(EXPECTED_REGS[-1],
                         (0xe1000000,0xe2000000,0xe6000000))
    def test_four_real_vblank_callbacks_required(self):
        self.assertIn("vh78_vblank_observed_count!=initial_vblank_count+4",self.native)
    def test_hooks_in_original_counter_source_only(self):
        s=Path(__file__).resolve().parents[1].joinpath(
            "tools/apply_map02_v78_pcsx_rearmed.py").read_text()
        self.assertIn('GPU_vBlank( 1, 0 );',s)
        self.assertIn("vh78_vblank_observed_count++;",s)
        self.assertIn("vh78_vblank_last_cycle=psxRegs.cycle",s)
    def test_no_counter_forgery_in_host(self):
        self.assertNotIn("vh78_vblank_observed_count++;",self.native)
        self.assertNotIn("psxRegs.cycle +=",self.native)
        self.assertNotIn("GPU_vBlank( 1, 0 );",self.native)
    def test_source_observer_records_frame_and_hsync(self):
        src=Path(__file__).resolve().parents[1].joinpath(
            "tools/apply_map02_v78_pcsx_rearmed.py").read_text()
        self.assertIn("vh78_vblank_last_frame=frame_counter",src)
        self.assertIn("vh78_vblank_last_hsync=hSyncCount",src)
    def test_cpu_executes_wait_loop_between_each_phase(self):
        self.assertIn("psxRegs.pc=VH78_WAIT_PC".replace("VH78_WAIT_PC",f"0x{self.wait:08x}u"),self.native)
        self.assertIn("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)",self.native)
    def test_cpu_pc_restored_before_next_stage(self):
        self.assertIn("psxRegs.pc=next_stage_pc;",self.native)
    def test_event_interval_one_and_last_cycle_increases(self):
        self.assertIn("vh78_vblank_observed_count!=entry_count+1",self.native)
        self.assertIn("vh78_vblank_last_cycle<=start_cycle",self.native)
    def test_real_vblank_frame_counter_sequential(self):
        self.assertIn("vh78_vblank_last_frame!=previous_vblank_frame+1",self.native)
    def test_each_phase_has_native_gpufreeze(self):
        self.assertIn("GPU_freeze(1,&state,&vram)",self.native)
        self.assertIn("vram[y*1024+x]!=expected",self.native)
    def test_595_pixels_each_observed_vblank(self):
        self.assertIn("checked!=595",self.native)
        self.assertIn("VH78_PHASE_PASS phase=%u checked=595 guard=499",self.native)
    def test_total_2380_expected_samples(self):
        self.assertIn("samples=2380",self.native)
        for phase in range(4):
            samples=[expected_pixel(phase,x,y) for y in range(159,166)
                     for x in range(39,124)]
            self.assertEqual(len(samples),595)
            self.assertEqual(samples.count(0),499)
    def test_vblank_report_emitted_separately(self):
        self.assertIn("VH78_VBLANK_OBSERVED phase=%u event=%u frame=%u loops=%u",self.native)
    def test_oracle_pixel_refusal_before_state_refusal(self):
        self.assertLess(self.native.index("VH78_VRAM_REFUSED"),
                        self.native.index("VH78_GPU_STATE_REFUSED"))
    def test_source_marked_not_physical_vblank(self):
        m=Path(__file__).resolve().parents[1].joinpath(
            "tools/make_map02_v78_vblank_mips_exe.py").read_text()
        self.assertIn("No host-forged cycles",m)
        self.assertIn("no artificial VBlank",self.native)
    def test_no_retail_map02_or_switch_approval(self):
        src=Path(__file__).resolve().parents[1].joinpath(
            "tools/apply_map02_v78_pcsx_rearmed.py").read_text()
        self.assertIn("physical_ps1_vblank_verified=False",src)
        self.assertIn("original_retail_MAP02_verified=False",src)
        self.assertIn("HD_replacement_approved=False",src)
    def test_actual_psxcounters_hook_decl_only(self):
        self.assertIn("vh78_vblank_observed_count;",vblank_hook())
        self.assertNotIn("vh78_vblank_observed_count++",vblank_hook())
    def test_four_phase_gp0_inputs_unchanged(self):
        self.assertEqual(len(PHASE_GP0),4)
        self.assertEqual(self.ops[:len(self.v77ops)],self.v77ops)
    def test_build_deterministic(self):
        self.assertEqual(build(),(self.exe,self.stop,self.start,self.wait,self.ops))
        self.assertEqual(hashlib.sha256(build()[0]).digest(),hashlib.sha256(self.exe).digest())
    def test_cli_writes_only_new_synthetic_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"v78.exe"
            with patch.object(sys,"argv",["v78","--output",str(p)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(p.read_bytes(),self.exe)
    def test_cli_refuses_overwrite_private_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"private.exe";p.write_bytes(b"PRIVATE")
            with patch.object(sys,"argv",["v78","--output",str(p)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(p.read_bytes(),b"PRIVATE")
    def test_no_retail_asset_dependency(self):
        source=Path(__file__).resolve().parents[1].joinpath(
            "tools/make_map02_v78_vblank_mips_exe.py").read_text()
        self.assertNotIn("rom_path",source)
        self.assertNotIn("game_disc",source)

if __name__=="__main__":
    unittest.main()
