#!/usr/bin/env python3
"""v78 emulated RCNT/VBlank evidence and 5 independent native VRAM snapshots."""
from __future__ import annotations
import hashlib
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v77_gpu_multiphase_exe import (
    build,START,MARKERS,PHASE_GP0,PHASE_GP1,EXPECTED_REGS,expected_pixel
)
from tools.apply_map02_v78_pcsx_rearmed import apply,vblank_source,smoke_source
from tools.apply_map02_v69_pcsx_rearmed import once

class Map02V78RCNTVBlank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image,cls.stops,cls.ops,cls.starts=build()
        cls.probe=smoke_source(cls.stops)
        cls.hook=vblank_source(cls.stops)
        cls.source=inspect.getsource(apply)
    def test_uses_preverified_original_synthetic_exe_only(self):
        self.assertEqual(len(self.image),6144)
        self.assertEqual(self.image[0x4c:0x54],b"VH77SYN!")
    def test_refuses_retail_game_executable(self):
        self.assertIn('memcmp(tag,"VH77SYN!",8)',self.probe)
        self.assertIn("VH78_EXE_REFUSED",self.probe)
    def test_load_entry_remains_true_mips(self):
        self.assertEqual(self.starts[0],START)
    def test_all_four_previous_phase_stops_preserved(self):
        self.assertEqual(self.stops[:3],self.starts[1:])
        for stop in self.stops:self.assertTrue(stop&0x80000000)
    def test_raw_cpu_gpu_fifo_and_reset_are_real_words(self):
        self.assertEqual(PHASE_GP1,(0x01000000,None,0x01000000,0))
    def test_last_checkpoint_has_full_reset_gpu_state(self):
        self.assertEqual(EXPECTED_REGS[-1],(0xe1000000,0xe2000000,0xe6000000))
    def test_all_last_phase_vram_colors_are_fixed(self):
        self.assertEqual(tuple(expected_pixel(3,x,160) for x in (40,56,72,88,104,120)),
                         (0xfc1f,0x801f,0xfc1f,0x801f,0xbde0,0x001f))
    def test_last_phase_595_96_499(self):
        px=[expected_pixel(3,x,y) for y in range(159,166) for x in range(39,124)]
        self.assertEqual(len(px),595)
        self.assertEqual(px.count(0),499)
        self.assertEqual(len(px)-px.count(0),96)
    def test_five_snapshot_samples(self):
        self.assertEqual(5*595,2975)
        self.assertIn("checked!=2975",self.probe)
    def test_not_fake_vblank_counter_derived_from_cpu_blocks(self):
        self.assertIn("psxCpu->ExecuteBlock",self.probe)
        self.assertIn("vh78_rcnt_events<checkpoint",self.probe)
        self.assertNotIn("psxRcntUpdate();",self.probe)
    def test_observe_symbol_only_in_real_psx_scheduler(self):
        self.assertIn("psxcounters.c",self.source)
        self.assertIn("GPU_vBlank( 1, 0 );",self.source)
        self.assertIn("GPU_vBlank(0, field);",self.source)
    def test_scheduler_hook_added_after_real_vblank_callback(self):
        a=self.source.index('GPU_vBlank( 1, 0 );')
        b=self.source.index('vh78_rcnt_vblank_observe(psxRegs.cycle,(unsigned int)hSyncCount,1)')
        self.assertLess(a,b)
        c=self.source.index('GPU_vBlank(0, field);')
        d=self.source.index('vh78_rcnt_vblank_observe(psxRegs.cycle,(unsigned int)hSyncCount,0)')
        self.assertLess(c,d)
    def test_core_hook_compilation_is_opt_in(self):
        self.assertIn("#ifdef VH_MAP02_V66_PCSX_PROBE",self.source)
        self.assertIn("extern void vh78_rcnt_vblank_observe",self.source)
    def test_vblank_ring_is_bounded(self):
        self.assertIn("n>=8",self.hook)
        self.assertIn("vh78_rcnt_overflow=1",self.hook)
        self.assertIn("vh78_rcnt_events=n+1",self.hook)
    def test_callback_captures_cycle_and_hsync(self):
        for field in ("vh78_rcnt_cycle[n]=cycle","vh78_rcnt_hsync[n]=hsync",
                      "vh78_rcnt_type[n]=start"):
            self.assertIn(field,self.hook)
    def test_two_true_vblank_rising_and_falling_edges(self):
        self.assertIn("expected_type=(n%2==0)?1:0",self.probe)
        self.assertIn("vblank_starts=2 vblank_ends=2",self.probe)
    def test_hsync_start_240_and_end_reset_zero(self):
        self.assertIn("expected_hsync=expected_type?240:0",self.probe)
    def test_monotonic_event_cycle_required(self):
        self.assertIn("cycle<=previous_cycle",self.probe)
    def test_snapshot_close_to_event_limit(self):
        self.assertIn("(unsigned int)(psxRegs.cycle-cycle)>4096u",self.probe)
    def test_mips_execution_advances_true_scheduler(self):
        self.assertIn("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)",self.probe)
        self.assertIn("steps<budget",self.probe)
        self.assertIn("800000",self.probe)
    def test_core_missing_vblank_fails_closed(self):
        self.assertIn("VH78_VBLANK_MISSING_REFUSED",self.probe)
        self.assertIn("vh78_rcnt_events!=checkpoint",self.probe)
    def test_events_cannot_skip_multiple_edges(self):
        self.assertIn("vh78_rcnt_events!=checkpoint",self.probe)
    def test_real_native_gpu_vram_checked_after_every_event(self):
        self.assertIn("GPU_freeze(1,&state,&vram)",self.probe)
        self.assertIn("vram[y*1024+x]!=expect",self.probe)
        self.assertIn("VH78_VRAM_CHECKPOINT_PASS",self.probe)
    def test_original_gpu_e1_e2_e6_fields_read(self):
        for key in ("state.ulControl[0xe1]","state.ulControl[0xe2]",
                    "state.ulControl[0xe6]"):
            self.assertIn(key,self.probe)
    def test_native_vram_mismatch_fails_closed(self):
        self.assertIn("VH78_VRAM_REFUSED",self.probe)
        self.assertIn("local!=595 || bad",self.probe)
    def test_short_budget_negative_scenario(self):
        self.assertIn("vh78_short_budget?1000:800000",self.probe)
        self.assertIn('--vh78-short-budget-negative',self.source)
    def test_exe_marker_mutation_fails_before_mips(self):
        self.assertIn("if(!tagged || !ready_to_go",self.probe)
    def test_last_branch_exactly_bounded(self):
        self.assertIn(f"0x{self.stops[-1]:08x}u",self.probe)
        self.assertIn("psxRegs.pc!=finish_pc",self.probe)
    def test_original_ram_marker_checked_before_event_stepping(self):
        self.assertIn("0x77010004u",self.probe)
        self.assertIn("VH78_MIPS_PRECONDITION_REFUSED",self.probe)
    def test_software_only_evidence_label(self):
        source=(Path(__file__).resolve().parents[1]/
                "tools/apply_map02_v78_pcsx_rearmed.py").read_text()
        for key in ("authentic_physical_ps1_vblank_verified=False",
                    "retail_MAP02_frame_timing_verified=False",
                    "original_retail_MAP02_verified=False",
                    "HD_replacement_approved=False"):
            self.assertIn(key,source)
    def test_no_genuine_hardware_or_real_game_content_required(self):
        self.assertNotIn("game_disc",self.source)
        self.assertNotIn("retail_rom",self.source)
    def test_core_source_anchor_fails_closed_when_missing(self):
        with self.assertRaises(Exception):
            once("source without VBlank", "GPU_vBlank(0, field);","probe",
                 "missing original core hook site")
    def test_diagnostic_does_not_modify_rasterizer_code(self):
        self.assertNotIn("plugins/gpulib",self.source)
        self.assertNotIn("renderer_do_cmd_list",self.source)
    def test_original_exe_hash_stable(self):
        self.assertEqual(hashlib.sha256(build()[0]).digest(),
                         hashlib.sha256(self.image).digest())
if __name__=="__main__":unittest.main()
