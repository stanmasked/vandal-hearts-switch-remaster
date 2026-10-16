#!/usr/bin/env python3
"""v76 source-authored GPU layering, CLUT change and E1/E2/E6 state test."""
from __future__ import annotations
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v76_gpu_state_order_exe import (
    MAGIC,HEADER_SIZE,SECTION_SIZE,REGIONS,GP0_SEQUENCE,PALETTE_A,PALETTE_B,
    SOURCE_4BPP,CLUT_A,CLUT_B,Y,avg,ft4,sprite,tile,build,expected_pixel,main
)
from tools.apply_map02_v76_pcsx_rearmed import oracle_source
from tools.make_map02_v70_synthetic_psx_exe import START,sw

class V76OrderedGPUStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe,cls.end,cls.mips=build()
    def test_original_psx_exe_6k(self):
        self.assertEqual(len(self.exe),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(len(self.exe),6144)
    def test_psx_exe_tag_and_nonretail(self):
        self.assertEqual(self.exe[:8],b"PS-X EXE")
        self.assertEqual(self.exe[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH76SYN!")
        self.assertNotIn(b"Vandal Hearts",self.exe)
    def test_cpu_load_entry_and_stack(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x18)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x1c)[0],SECTION_SIZE)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x30)[0],0x801fff00)
    def test_all_gpu_words_issued_as_cpu_store(self):
        self.assertEqual(sum(x==sw(9,0,8) for x in self.mips),len(GP0_SEQUENCE)+1)
    def test_one_gpu_fifo_reset_before_gp0(self):
        self.assertEqual(self.mips[4],sw(9,0,8))
    def test_three_cpu_to_vram_uploads(self):
        self.assertEqual(GP0_SEQUENCE.count(0xa0000000),3)
    def test_four_texels_per_lane(self):
        self.assertEqual(SOURCE_4BPP[:4],(0x1111,0x2222,0x3333,0x4444))
        self.assertEqual(len(SOURCE_4BPP),16)
    def test_two_palette_uploads_at_different_vram_locations(self):
        self.assertIn(512,GP0_SEQUENCE)
        self.assertIn(528,GP0_SEQUENCE)
        self.assertEqual(CLUT_A,32)
        self.assertEqual(CLUT_B,33)
    def test_source_palette_stp_and_opaque_entries(self):
        self.assertEqual((PALETTE_A[1],PALETTE_A[2],PALETTE_A[3],PALETTE_A[4]),
                         (0x801f,0x83e0,0x001f,0x03e0))
    def test_second_palette_distinct_at_index3(self):
        self.assertEqual(PALETTE_B[3],0x03ff)
        self.assertNotEqual(PALETTE_A[3],PALETTE_B[3])
    def test_blue_background_for_all_11_regions(self):
        self.assertEqual(GP0_SEQUENCE.count(0x60ff0000),11)
    def test_two_stp_layer_orders_have_distinct_results(self):
        self.assertEqual(REGIONS[0][2],0x9de7)
        self.assertEqual(REGIONS[1][2],0x9cef)
        self.assertNotEqual(REGIONS[0][2],REGIONS[1][2])
    def test_semitransparency_average_rounded_down(self):
        self.assertEqual(avg(0x7c00,0x801f),0xbc0f)
        self.assertEqual(avg(0x7c00,0x83e0),0xbde0)
    def test_red_then_green_order_in_gpu_packets(self):
        seq=ft4(40,32,0,True)+ft4(40,32,4,True)
        self.assertIn(seq,tuple(GP0_SEQUENCE[i:i+len(seq)]
                          for i in range(len(GP0_SEQUENCE)-len(seq)+1)))
    def test_green_then_red_order_in_gpu_packets(self):
        seq=ft4(56,32,4,True)+ft4(56,32,0,True)
        self.assertIn(seq,tuple(GP0_SEQUENCE[i:i+len(seq)]
                          for i in range(len(GP0_SEQUENCE)-len(seq)+1)))
    def test_clut_switch_maintains_identical_index(self):
        a=ft4(72,32,8)
        b=ft4(88,33,8)
        self.assertEqual(a[2]&0xff,b[2]&0xff)
        self.assertEqual(a[2]>>16,32)
        self.assertEqual(b[2]>>16,33)
    def test_clut_switch_changes_actual_color(self):
        self.assertEqual(expected_pixel(72,Y),0x001f)
        self.assertEqual(expected_pixel(88,Y),0x03ff)
    def test_e2_window_set_then_restored(self):
        pos=GP0_SEQUENCE.index(0xe2000401)
        self.assertEqual(GP0_SEQUENCE[pos+1:pos+10],ft4(104,32,4))
        self.assertEqual(GP0_SEQUENCE[pos+10],0xe2000000)
    def test_e2_window_remaps_u4_to_u12(self):
        self.assertEqual((4&~8)|8,12)
        self.assertEqual(expected_pixel(104,Y),0x03e0)
        self.assertEqual(expected_pixel(120,Y),0x001f)
    def test_e6_mask_set_protect_restore(self):
        set_i=GP0_SEQUENCE.index(0xe6000001)
        check_i=GP0_SEQUENCE.index(0xe6000002)
        self.assertLess(set_i,check_i)
        self.assertEqual(GP0_SEQUENCE[check_i+1:check_i+10],ft4(136,32,12))
        self.assertEqual(GP0_SEQUENCE[check_i+10],0xe6000000)
    def test_e6_protected_vs_restored_pixels(self):
        self.assertEqual(expected_pixel(136,Y),0x801f)
        self.assertEqual(expected_pixel(152,Y),0x03e0)
    def test_sprite_uses_e1_persistent_state(self):
        self.assertEqual(sprite(168,32,0)[0],0x67ffffff)
        self.assertEqual(len(sprite(168,32,0)),4)
        self.assertEqual(sprite(184,32,0)[0],0x67ffffff)
    def test_e1_abr1_and_restore_are_between_sprites(self):
        start=GP0_SEQUENCE.index(0xe1000020)
        self.assertEqual(GP0_SEQUENCE[start+1:start+5],sprite(184,32,0))
        self.assertEqual(GP0_SEQUENCE[start+5],0xe1000000)
        self.assertEqual(GP0_SEQUENCE[start+6:start+10],sprite(200,32,0))
    def test_e1_abr0_and_abr1_samples_independent(self):
        self.assertEqual(expected_pixel(168,Y),0xbc0f)
        self.assertEqual(expected_pixel(184,Y),0xfc1f)
        self.assertEqual(expected_pixel(200,Y),0xbc0f)
    def test_state_resets_at_end(self):
        self.assertEqual(GP0_SEQUENCE[-2:],(0xe2000000,0xe6000000))
    def test_ordered_e2_e6_e1_resets_are_not_noops(self):
        states=[x for x in GP0_SEQUENCE if x in (
            0xe2000401,0xe6000001,0xe6000002,0xe1000020)]
        self.assertEqual(states,(0xe2000401,0xe6000001,0xe6000002,0xe1000020))
    def test_11_independent_expected_regions(self):
        self.assertEqual(len(REGIONS),11)
        self.assertEqual(tuple(x for _,x,_ in REGIONS),
                         (40,56,72,88,104,120,136,152,168,184,200))
    def test_oracle_1162_samples_986_guards(self):
        px=[expected_pixel(x,y) for y in range(127,134) for x in range(39,205)]
        self.assertEqual(len(px),1162)
        self.assertEqual(px.count(0),986)
        self.assertEqual(sum(bool(c) for c in px),176)
    def test_each_area_has_exactly_16_pixels(self):
        for _,left,color in REGIONS:
            self.assertEqual([expected_pixel(x,y) for x in range(left,left+4)
                              for y in range(Y,Y+4)],[color]*16)
    def test_guard_points_unpainted(self):
        for pt in ((39,127),(44,129),(55,130),(60,128),(71,130),
                   (76,129),(103,128),(108,129),(151,128),(204,133)):
            self.assertEqual(expected_pixel(*pt),0)
    def test_actual_oracle_uses_native_gpu_vram(self):
        src=oracle_source(self.end)
        self.assertIn("GPU_freeze(1,&freeze,&vram)",src)
        self.assertIn("vram[y*1024+x]!=wanted",src)
    def test_actual_oracle_refuses_any_wrong_pixel(self):
        src=oracle_source(self.end)
        self.assertIn("total_bad",src)
        self.assertIn("VH76_VRAM_REFUSED",src)
        self.assertIn("checked!=1162",src)
    def test_actual_oracle_matches_full_region_count(self):
        self.assertIn("region_pixels=176 guard=986",oracle_source(self.end))
    def test_actual_oracle_verifies_real_cpu_marker(self):
        src=oracle_source(self.end)
        self.assertIn("psxCpu->ExecuteBlock",src)
        self.assertIn("VH76_CPU_MARKER_REFUSED",src)
        self.assertIn(f"0x{self.end:08x}u",src)
    def test_actual_oracle_refuses_other_program(self):
        self.assertIn('memcmp(tag,"VH76SYN!",8)',oracle_source(self.end))
    def test_cpu_bounded_jump(self):
        self.assertEqual(self.mips[-1],0)
        self.assertEqual(self.mips[-2],(2<<26)|((self.end>>2)&0x3ffffff))
    def test_mips_payload_size(self):
        self.assertLessEqual(len(self.mips)*4,SECTION_SIZE)
    def test_original_data_provenance_gates_closed(self):
        src=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v76_pcsx_rearmed.py").read_text()
        self.assertIn("original_retail_MAP02_verified=False",src)
        self.assertIn("HD_replacement_approved=False",src)
    def test_deterministic_binary(self):
        self.assertEqual(build(),(self.exe,self.end,self.mips))
        self.assertEqual(hashlib.sha256(build()[0]).digest(),hashlib.sha256(self.exe).digest())
    def test_cli_creates_synthetic_exe(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"v76-synthetic.exe"
            with patch.object(sys,"argv",["v76","--output",str(p)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(p.read_bytes(),self.exe)
    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"private.exe";p.write_bytes(b"PROPRIETARY")
            with patch.object(sys,"argv",["v76","--output",str(p)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(p.read_bytes(),b"PROPRIETARY")
    def test_no_original_game_asset_paths(self):
        src=(Path(__file__).resolve().parents[1]/"tools/make_map02_v76_gpu_state_order_exe.py").read_text()
        self.assertNotIn("rom_path",src)
        self.assertNotIn("game_disc",src)

if __name__=="__main__":
    unittest.main()
