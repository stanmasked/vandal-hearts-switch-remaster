#!/usr/bin/env python3
"""v77 actual in-process PCSX multi-phase MIPS + GP1 GPU state checks."""
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
from tools.make_map02_v77_gpu_multiphase_exe import (
    MAGIC,MARKERS,PHASE_NAMES,PHASE_GP0,PHASE_GP1,EXPECTED_REGS,X,Y,
    E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK,CLUT,TEXELS,
    HEADER_SIZE,SECTION_SIZE,START,build,phase_body,expected_pixel,
    tile,sprite,main
)
from tools.make_map02_v70_synthetic_psx_exe import lui,ori,sw,addiu
from tools.apply_map02_v77_pcsx_rearmed import oracle_source

class V77MultiphaseGpuState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe,cls.stops,cls.instructions,cls.starts=build()
    def test_psx_exe_header_and_length(self):
        self.assertEqual(self.exe[:8],b"PS-X EXE")
        self.assertEqual(len(self.exe),HEADER_SIZE+SECTION_SIZE)
    def test_unique_synthetic_marker(self):
        self.assertEqual(self.exe[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH77SYN!")
        self.assertNotIn(b"Vandal Hearts",self.exe)
    def test_entry_and_load_destination(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x18)[0],START)
    def test_bounded_payload_and_stack(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x1c)[0],SECTION_SIZE)
        self.assertLessEqual(len(self.instructions)*4,SECTION_SIZE)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x30)[0],0x801fff00)
    def test_four_phase_names_and_markers(self):
        self.assertEqual(PHASE_NAMES,("setup","persist","fifo_reset","full_reset"))
        self.assertEqual(MARKERS,(0x77010001,0x77010002,0x77010003,0x77010004))
    def test_phase_offsets_strict_increasing(self):
        self.assertEqual(self.starts[0],START)
        self.assertTrue(all(a<b for a,b in zip(self.starts,self.starts[1:])))
    def test_first_three_branches_go_to_next_phase(self):
        self.assertEqual(self.stops[:3],self.starts[1:])
    def test_last_phase_has_self_loop(self):
        self.assertGreaterEqual(self.stops[3],self.starts[3])
        self.assertEqual(self.instructions[-2],
                         (2<<26)|((self.stops[3]>>2)&0x3ffffff))
        self.assertEqual(self.instructions[-1],0)
    def test_cpu_jumps_separate_execute_blocks(self):
        for i in range(4):
            words=phase_body(i)
            at=(self.starts[i]-START)//4
            self.assertEqual(list(self.instructions[at:at+len(words)]),words)
            self.assertEqual(self.instructions[at+len(words)],
                             (2<<26)|((self.stops[i]>>2)&0x3ffffff))
    def test_all_phase_markers_written_as_cpu_sw(self):
        for i in range(4):
            body=phase_body(i)
            self.assertIn(ori(10,10,0x1000+4*i),body)
            self.assertEqual(body[-1],sw(9,0,10))
    def test_gp1_reset_times_explicit(self):
        self.assertEqual(PHASE_GP1,(0x01000000,None,0x01000000,0))
    def test_gp1_fifo_reset_keeps_draw_mode(self):
        self.assertEqual(EXPECTED_REGS[1:3],
                         ((E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK),)*2)
    def test_gp1_full_reset_resets_e1_e2_e6(self):
        self.assertEqual(EXPECTED_REGS[-1],
                         (0xe1000000,0xe2000000,0xe6000000))
    def test_initial_texture_upload_and_clut(self):
        self.assertEqual(PHASE_GP0[0].count(0xa0000000),2)
        self.assertEqual(TEXELS,(0,0x2222,0,0x1111)*4)
        self.assertEqual(CLUT[1:3],(0x801f,0x83e0))
    def test_six_blue_backdrops_before_state_changes(self):
        self.assertEqual(PHASE_GP0[0].count(0x60ff0000),6)
        self.assertEqual(PHASE_GP0[0][-3:],(E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK))
    def test_second_phase_emits_no_register_changes(self):
        self.assertEqual(PHASE_GP0[1],sprite(X[0])+tile(X[1]))
        self.assertIsNone(PHASE_GP1[1])
    def test_fifo_reset_phase_emits_no_gp0_state_changes(self):
        self.assertEqual(PHASE_GP0[2],sprite(X[2])+tile(X[3]))
    def test_full_reset_restores_only_drawing_area(self):
        self.assertEqual(PHASE_GP0[3][:2],(0xe3000000,0xe407ffff))
        self.assertEqual(PHASE_GP0[3][2:],sprite(X[4])+tile(X[5]))
        self.assertNotIn(E1_ABR1,PHASE_GP0[3])
    def test_textured_sprite_uses_gpu_persistent_e1(self):
        self.assertEqual(sprite(X[0])[0],0x67ffffff)
        self.assertEqual(sprite(X[0])[2],(32<<16)|4)
    def test_window_maps_source_u4_to_u12(self):
        self.assertEqual((4&~8)|8,12)
    def test_first_snapshot_contains_only_six_blue_tiles(self):
        self.assertEqual(tuple(expected_pixel(0,x,Y) for x in X),(0x7c00,)*6)
    def test_after_first_execution_e1_e2_e6_still_active(self):
        self.assertEqual(tuple(expected_pixel(1,x,Y) for x in X),
                         (0xfc1f,0x801f,0x7c00,0x7c00,0x7c00,0x7c00))
    def test_after_fifo_reset_pixels_reproduce_without_reprogramming(self):
        self.assertEqual(tuple(expected_pixel(2,x,Y) for x in X),
                         (0xfc1f,0x801f,0xfc1f,0x801f,0x7c00,0x7c00))
    def test_after_full_reset_different_pixels_without_restoring_gpu_state(self):
        self.assertEqual(tuple(expected_pixel(3,x,Y) for x in X),
                         (0xfc1f,0x801f,0xfc1f,0x801f,0xbde0,0x001f))
    def test_four_phases_each_595_native_pixel_checks(self):
        for p in range(4):
            pixels=[expected_pixel(p,x,y) for y in range(159,166)
                    for x in range(39,124)]
            self.assertEqual(len(pixels),595)
            self.assertEqual(pixels.count(0),499)
            self.assertEqual(sum(v!=0 for v in pixels),96)
    def test_total_pixel_count_2380(self):
        self.assertEqual(4*595,2380)
    def test_fence_is_not_asserted_as_ps1_vblank(self):
        src=(Path(__file__).resolve().parents[1]/
             "tools/make_map02_v77_gpu_multiphase_exe.py").read_text()
        self.assertIn("NOT a physical PS1 VBlank",src)
    def test_real_oracle_has_four_cpu_execute_calls(self):
        src=oracle_source(self.stops)
        self.assertIn("phase<4",src)
        self.assertIn("psxCpu->ExecuteBlock",src)
        self.assertIn("VH77_MIPS_PHASE_REFUSED",src)
    def test_real_native_gpu_freeze_after_each_phase(self):
        src=oracle_source(self.stops)
        self.assertIn("GPU_freeze(1,&state,&vram)",src)
        self.assertIn("vram[y*1024+x]!=expected",src)
    def test_gpu_readback_control_registers(self):
        src=oracle_source(self.stops)
        self.assertIn("state.ulControl[ids[i]]",src)
        self.assertIn("0xe1000020u",src)
        self.assertIn("0xe2000401u",src)
        self.assertIn("0xe6000001u",src)
    def test_oracle_verifies_pixel_mismatches_before_register_snapshot(self):
        src=oracle_source(self.stops)
        self.assertLess(src.index("VH77_VRAM_REFUSED"),
                        src.index("VH77_GPU_STATE_REFUSED"))
    def test_real_oracle_binds_all_four_expected_stop_pc(self):
        src=oracle_source(self.stops)
        for addr in self.stops:self.assertIn(f"0x{addr:08x}u",src)
    def test_no_retial_promotion(self):
        src=(Path(__file__).resolve().parents[1]/
             "tools/apply_map02_v77_pcsx_rearmed.py").read_text()
        self.assertIn("original_retail_MAP02_verified=False",src)
        self.assertIn("HD_replacement_approved=False",src)
        self.assertIn("physical_gpu_vblank_boundaries_observed=False",src)
    def test_deterministic_mips_exe(self):
        self.assertEqual(build(),(self.exe,self.stops,self.instructions,self.starts))
        self.assertEqual(hashlib.sha256(build()[0]).digest(),
                         hashlib.sha256(self.exe).digest())
    def test_cli_creates_original_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"v77-original-synth.exe"
            with patch.object(sys,"argv",["v77","--output",str(path)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(path.read_bytes(),self.exe)
    def test_cli_refuses_private_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"private.exe";path.write_bytes(b"PRIVATE")
            with patch.object(sys,"argv",["v77","--output",str(path)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(path.read_bytes(),b"PRIVATE")
    def test_fixture_no_game_asset_path(self):
        src=(Path(__file__).resolve().parents[1]/
             "tools/make_map02_v77_gpu_multiphase_exe.py").read_text()
        self.assertNotIn("rom_path",src)
        self.assertNotIn("game_disc",src)
if __name__=="__main__":unittest.main()
