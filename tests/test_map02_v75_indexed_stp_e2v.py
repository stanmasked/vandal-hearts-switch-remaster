#!/usr/bin/env python3
"""v75 indexed STP/ABR and vertical E2 real-PCXS pixel oracle regressions."""
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
from tools.make_map02_v75_indexed_stp_e2v_exe import (
    MAGIC,HEADER_SIZE,SECTION_SIZE,PALETTE4,PALETTE8,TEXTURE4,TEXTURE8,
    E2_VERTICAL,REGIONS,GP0_SEQUENCE,expected_pixel,ft4,build,main
)
from tools.make_map02_v74_indexed_clut_exe import upload,xy
from tools.make_map02_v70_synthetic_psx_exe import START,sw
from tools.apply_map02_v75_pcsx_rearmed import oracle_source

class V75CLUTSTPE2V(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image,cls.end,cls.opcodes=build()
    def test_original_psx_exe_size(self):
        self.assertEqual(len(self.image),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(len(self.image),6144)
    def test_magic_psx_exe(self):
        self.assertEqual(self.image[:8],b"PS-X EXE")
    def test_unique_non_game_identity(self):
        self.assertEqual(self.image[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH75SYN!")
        self.assertNotIn(b"Vandal Hearts",self.image)
    def test_program_entry(self):
        self.assertEqual(struct.unpack_from("<I",self.image,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.image,0x18)[0],START)
    def test_program_bounds(self):
        self.assertEqual(struct.unpack_from("<I",self.image,0x1c)[0],SECTION_SIZE)
        self.assertLess(len(self.opcodes)*4,SECTION_SIZE)
    def test_stack_inside_ps1_ram(self):
        self.assertEqual(struct.unpack_from("<I",self.image,0x30)[0],0x801fff00)
    def test_gp1_fifo_reset_precedes_gp0(self):
        self.assertEqual(self.opcodes[4],sw(9,0,8))
    def test_cpu_writes_every_gp0_word(self):
        self.assertEqual(sum(op==sw(9,0,8) for op in self.opcodes),
                         len(GP0_SEQUENCE)+1)
    def test_gpu_draw_area_and_mask_initialized(self):
        self.assertEqual(GP0_SEQUENCE[:6],(
            0xe3000000,0xe407ffff,0xe5000000,0xe6000000,0xe1000000,0xe2000000))
    def test_four_cpu_a0_uploads(self):
        self.assertEqual(GP0_SEQUENCE.count(0xa0000000),4)
    def test_4bpp_texture_twelve_rows(self):
        self.assertEqual(len(TEXTURE4),24)
        self.assertEqual(upload(0,0,2,12,TEXTURE4)[:3],
                         (0xa0000000,0,xy(2,12)))
    def test_4bpp_first_rows_stp_index1(self):
        for row in range(4):
            self.assertEqual(TEXTURE4[row*2],0x1111)
    def test_4bpp_nonstp_second_u_lane(self):
        self.assertEqual(tuple(TEXTURE4[2*i+1] for i in range(12)),(0x2222,)*12)
    def test_e2_window_rows_different_palette_index(self):
        for row in range(8,12):
            self.assertEqual(TEXTURE4[row*2],0x3333)
        self.assertNotEqual(TEXTURE4[0],TEXTURE4[16])
    def test_indexed_8bpp_four_lines(self):
        self.assertEqual(len(TEXTURE8),16)
        self.assertEqual(TEXTURE8[:4],(0x1111,0x1111,0,0))
    def test_8bpp_zero_lane(self):
        for row in range(4):
            self.assertEqual(TEXTURE8[row*4+2:row*4+4],(0,0))
    def test_4bpp_palette_stp_bit15(self):
        self.assertEqual(PALETTE4[1],0x801f)
        self.assertTrue(PALETTE4[1]&0x8000)
    def test_4bpp_nonstp_green_palette(self):
        self.assertEqual(PALETTE4[2],0x03e0)
        self.assertEqual(PALETTE4[2]&0x8000,0)
    def test_4bpp_vertical_window_cyan_palette(self):
        self.assertEqual(PALETTE4[3],0x03ff)
    def test_8bpp_palette_has_stp_red(self):
        self.assertEqual(len(PALETTE8),256)
        self.assertEqual(PALETTE8[17],0x801f)
    def test_palette_zero_is_transparent(self):
        self.assertEqual(PALETTE4[0],0)
        self.assertEqual(PALETTE8[0],0)
    def test_palette_clut_coordinates_are_not_texture_coordinates(self):
        self.assertIn((0xa0000000,512,xy(16,1)),(
            GP0_SEQUENCE[i:i+3] for i,x in enumerate(GP0_SEQUENCE) if x==0xa0000000))
        self.assertIn((0xa0000000,528,xy(256,1)),(
            GP0_SEQUENCE[i:i+3] for i,x in enumerate(GP0_SEQUENCE) if x==0xa0000000))
    def test_all_five_blue_backdrops(self):
        self.assertEqual(GP0_SEQUENCE.count(0x60ff0000),5)
    def test_ft4_4bpp_stp_abr0_packet(self):
        obj=ft4(40,32,0x000,0,True)
        self.assertEqual(len(obj),9)
        self.assertEqual(obj[0],0x2f000000)
        self.assertEqual(obj[2]>>16,32)
        self.assertEqual(obj[4]>>16,0)
    def test_ft4_4bpp_nonstp_uses_same_semicommand(self):
        self.assertEqual(ft4(56,32,0,4,True)[0],0x2f000000)
        self.assertEqual(ft4(56,32,0,4,True)[2]&255,4)
    def test_ft4_8bpp_abr1_command(self):
        part=ft4(72,33,0x0a1,0,True)
        self.assertEqual(part[0],0x2f000000)
        self.assertEqual(part[4]>>16,0x0a1)
        self.assertEqual((part[4]>>21)&3,1)
        self.assertEqual((part[4]>>23)&3,1)
    def test_ft4_8bpp_transparent_index0(self):
        part=ft4(88,33,0x081,4,True)
        self.assertEqual(part[2]&255,4)
        self.assertEqual(part[4]>>16,0x081)
    def test_e2_vertical_exact_bitfields(self):
        self.assertEqual(E2_VERTICAL,0xe2008020)
        self.assertEqual((E2_VERTICAL>>5)&31,1)
        self.assertEqual((E2_VERTICAL>>15)&31,1)
        self.assertEqual(E2_VERTICAL&31,0)
    def test_e2_vertical_remaps_v0_to_v8(self):
        mask,offset=1,1
        self.assertEqual(tuple((v&~(mask*8))|((offset&mask)*8) for v in range(4)),
                         (8,9,10,11))
    def test_e2_reset_follows_window_ft4(self):
        self.assertEqual(GP0_SEQUENCE[-1],0xe2000000)
        self.assertEqual(GP0_SEQUENCE[-11],E2_VERTICAL)
    def test_five_oracle_regions(self):
        self.assertEqual(tuple(left for _,left,_ in REGIONS),(40,56,72,88,104))
        self.assertEqual(tuple(color for _,_,color in REGIONS),
                         (0xbc0f,0x03e0,0xfc1f,0x7c00,0x03ff))
    def test_clut4_stp_average(self):
        self.assertEqual(expected_pixel(40,104),0xbc0f)
        self.assertEqual(0x8000|((31//2)<<10)|(31//2),0xbc0f)
    def test_clut4_non_stp_ignores_abe(self):
        self.assertEqual(expected_pixel(56,105),0x03e0)
        self.assertNotEqual(expected_pixel(56,105),0x7de0)
    def test_8bpp_stp_additive(self):
        self.assertEqual(expected_pixel(72,105),0xfc1f)
    def test_8bpp_zero_index_preserves_blue_backdrop(self):
        self.assertEqual(expected_pixel(88,107),0x7c00)
    def test_vertical_window_draw_samples_v8_palette_cyan(self):
        self.assertEqual(expected_pixel(104,104),0x03ff)
    def test_vram_region_511_samples(self):
        expected=[expected_pixel(x,y) for y in range(103,110) for x in range(39,112)]
        self.assertEqual(len(expected),511)
        self.assertEqual(expected.count(0),431)
        for _,_,value in REGIONS:
            self.assertEqual(expected.count(value),16)
    def test_guard_pixels_untouched(self):
        for xy_pair in ((39,103),(44,106),(55,106),(60,106),
                        (71,106),(76,106),(87,106),(92,106),(111,109)):
            self.assertEqual(expected_pixel(*xy_pair),0)
    def test_cpu_marker_self_branch(self):
        self.assertEqual(self.opcodes[-1],0)
        self.assertEqual(self.opcodes[-2],(2<<26)|((self.end>>2)&0x3ffffff))
    def test_real_pixel_oracle_reads_gpu_freeze_vram(self):
        source=oracle_source(self.end)
        self.assertIn("GPU_freeze(1,&state,&vram)",source)
        self.assertIn("vram[y*1024+x]!=expected",source)
    def test_oracle_checked_pixels_and_independent_colors(self):
        s=oracle_source(self.end)
        self.assertIn("checked!=511",s)
        self.assertIn("0xbc0f,0x03e0,0xfc1f,0x7c00,0x03ff",s)
    def test_untagged_exe_refused(self):
        self.assertIn('memcmp(tag,"VH75SYN!",8)',oracle_source(self.end))
    def test_cpu_marker_required_for_pass(self):
        s=oracle_source(self.end)
        self.assertIn("psxCpu->ExecuteBlock",s)
        self.assertIn("VH75_CPU_MARKER_REFUSED",s)
        self.assertIn(f"0x{self.end:08x}u",s)
    def test_no_original_map02_gate_promotion(self):
        s=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v75_pcsx_rearmed.py").read_text()
        self.assertIn("original_retail_MAP02_verified=False",s)
        self.assertIn("HD_replacement_approved=False",s)
    def test_exe_deterministic_build(self):
        self.assertEqual(build(),(self.image,self.end,self.opcodes))
        self.assertEqual(hashlib.sha256(build()[0]).digest(),hashlib.sha256(self.image).digest())
    def test_cli_writes_exact_synthetic_binary(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"v75-synthetic.exe"
            with patch.object(sys,"argv",["v75","--output",str(path)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(path.read_bytes(),self.image)
    def test_cli_refuses_private_file_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"retail-private.exe";path.write_bytes(b"PRIVATE")
            with patch.object(sys,"argv",["v75","--output",str(path)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(path.read_bytes(),b"PRIVATE")
    def test_no_retail_files_or_rom_dependencies(self):
        s=(Path(__file__).resolve().parents[1]/"tools/make_map02_v75_indexed_stp_e2v_exe.py").read_text()
        self.assertNotIn("rom_path",s)
        self.assertNotIn("game_disc",s)
if __name__=="__main__":
    unittest.main()
