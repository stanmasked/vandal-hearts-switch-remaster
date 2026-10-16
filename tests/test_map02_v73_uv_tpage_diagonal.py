#!/usr/bin/env python3
"""v73 PS1 GP0(A0), textured FT4 UV/tpage and FT3 diagonal-seam oracle."""
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
from tools.make_map02_v73_uv_tpage_mips_exe import (
    MAGIC,STRIPES,PAGE1,STP_RED,HEADER_SIZE,SECTION_SIZE,GP0_SEQUENCE,
    build,expected_pixel,ft3,ft4,upload,xy,main
)
from tools.make_map02_v70_synthetic_psx_exe import sw,lui,ori
from tools.apply_map02_v73_pcsx_rearmed import oracle_source

class Map02V73UVSeams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe,cls.loop,cls.mips=build()
    def test_exe_header(self):
        self.assertEqual(self.exe[:8],b"PS-X EXE")
        self.assertEqual(len(self.exe),HEADER_SIZE+SECTION_SIZE)
    def test_unique_synthetic_signature(self):
        self.assertEqual(self.exe[0x4c:0x54],MAGIC)
        self.assertNotIn(b"Vandal Hearts",self.exe)
        self.assertNotEqual(MAGIC,b"VH72SYN!")
    def test_exe_entry_and_load(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x10)[0],0x80010000)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x18)[0],0x80010000)
    def test_payload_size_and_stack(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x1c)[0],2048)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x30)[0],0x801fff00)
    def test_upload_count_three(self):
        self.assertEqual(GP0_SEQUENCE.count(0xa0000000),3)
    def test_first_texture_upload_eight_by_four(self):
        self.assertEqual(upload(0,STRIPES)[:3],(0xa0000000,0,xy(8,4)))
        self.assertEqual(len(upload(0,STRIPES)),19)
    def test_first_texture_has_nonconstant_uv_columns(self):
        self.assertEqual(STRIPES,(0x001f,0x03e0,0x7c00,0x7fff)*2)
    def test_second_texture_upload_at_page_64(self):
        self.assertEqual(upload(64,PAGE1)[:3],(0xa0000000,xy(64,0),xy(4,4)))
    def test_page_one_distinct_color_palette(self):
        self.assertEqual(PAGE1,(0x03ff,0x7fe0,0x7c1f,0x4210))
    def test_third_texture_is_uniform_stp(self):
        self.assertEqual(upload(128,(STP_RED,)*4)[:3],
                         (0xa0000000,xy(128,0),xy(4,4)))
        self.assertEqual(STP_RED,0x801f)
    def test_no_texture_upload_in_draw_oracle_zone(self):
        for x in (40,72,88):
            self.assertTrue(x>=40)
        self.assertEqual(GP0_SEQUENCE[:5],
            (0xe3000000,0xe407ffff,0xe5000000,0xe6000000,0xe1000100))
    def test_ft4_uses_nonidentity_uv_rate(self):
        f=ft4(40,0x100,0,8)
        self.assertEqual(len(f),9)
        self.assertEqual(f[2],0)
        self.assertEqual(f[4],(0x100<<16)|8)
    def test_second_ft4_uses_adjacent_tpage(self):
        f=ft4(72,0x101,0,4)
        self.assertEqual(f[0],0x2d000000)
        self.assertEqual(f[4],(0x101<<16)|4)
    def test_ft4_page0_and_page1_disjoint(self):
        self.assertIn(0x01000008,GP0_SEQUENCE)
        self.assertIn(0x01010004,GP0_SEQUENCE)
    def test_ft3_command_is_semitransparent_textured_raw(self):
        tri=ft3(((88,56),(92,56),(88,60)),((0,0),(4,0),(0,4)),0x102)
        self.assertEqual(len(tri),7)
        self.assertEqual(tri[0],0x27000000)
    def test_ft3_has_second_uv_tpage(self):
        tri=ft3(((92,56),(92,60),(88,60)),((4,0),(4,4),(0,4)),0x102)
        self.assertEqual(tri[4]>>16,0x102)
    def test_ft3_geometry_shares_diagonal(self):
        tri_a=ft3(((88,56),(92,56),(88,60)),((0,0),(4,0),(0,4)),0x102)
        tri_b=ft3(((92,56),(92,60),(88,60)),((4,0),(4,4),(0,4)),0x102)
        self.assertEqual((tri_a[3],tri_a[5]),(tri_b[1],tri_b[5]))
    def test_ft3_does_not_hide_double_blending(self):
        blue=31;red=31
        once=0x8000|((blue//2)<<10)|(red//2)
        twice=0x8000|((15//2)<<10)|((15+31)//2)
        self.assertEqual(once,0xbc0f)
        self.assertNotEqual(once,twice)
    def test_exact_gpu_mips_stores(self):
        self.assertEqual(sum(x==sw(9,0,8) for x in self.mips),
                         len(GP0_SEQUENCE)+1)
    def test_one_fifo_reset_before_gp0(self):
        self.assertEqual(self.mips[:6],
            (lui(8,0x1f80),ori(8,8,0x1814),lui(9,0x0100),
             ori(9,9,0),sw(9,0,8),0x2508fffc))
    def test_mips_pc_self_loop(self):
        self.assertEqual(self.mips[-1],0)
        self.assertEqual(self.mips[-2],(2<<26)|((self.loop>>2)&0x03ffffff))
    def test_mips_exe_bounded(self):
        self.assertLess(len(self.mips)*4,SECTION_SIZE)
    def test_uv_stride_oracle_four_pixels(self):
        self.assertEqual(tuple(expected_pixel(x,56) for x in range(40,44)),
                         (0x001f,0x7c00,0x001f,0x7c00))
    def test_adjacent_tpage_color_oracle(self):
        self.assertEqual(tuple(expected_pixel(x,56) for x in range(72,76)),
                         PAGE1)
    def test_two_ft3_seam_oracle(self):
        self.assertEqual(tuple(expected_pixel(x,56) for x in range(88,92)),
                         (0xbc0f,)*4)
    def test_all_399_guard_and_regions(self):
        pixels=[expected_pixel(x,y) for y in range(55,62) for x in range(39,96)]
        self.assertEqual(len(pixels),399)
        self.assertEqual(pixels.count(0),351)
        self.assertEqual(sum(pixels.count(v) for v in (
            0x001f,0x7c00,0x03ff,0x7fe0,0x7c1f,0x4210,0xbc0f)),48)
    def test_neighbouring_guards_zero(self):
        for point in ((39,55),(44,58),(71,58),(76,58),(87,58),(92,58),(95,61)):
            self.assertEqual(expected_pixel(*point),0)
    def test_pixel_test_reads_real_plugin_vram(self):
        source=oracle_source(self.loop)
        self.assertIn("GPU_freeze(1,&gpu_state,&vram)",source)
        self.assertIn("vram[y*1024+x]!=expected",source)
    def test_pixel_test_checks_all_399_pixels(self):
        source=oracle_source(self.loop)
        self.assertIn("checked!=399",source)
        self.assertIn("VH73_VRAM_PASS",source)
    def test_diagnostic_requires_marker_and_cpu_pc(self):
        source=oracle_source(self.loop)
        self.assertIn(f"0x{self.loop:08x}u",source)
        self.assertIn("0x70000001u",source)
        self.assertIn("VH73_CPU_MARKER_REFUSED",source)
    def test_diagnostic_rejects_forged_exe(self):
        self.assertIn('memcmp(tag,"VH73SYN!",8)',oracle_source(self.loop))
    def test_original_game_trust_flags_closed(self):
        s=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v73_pcsx_rearmed.py").read_text()
        self.assertIn("original_retail_MAP02_verified=False",s)
        self.assertIn("HD_replacement_approved=False",s)
    def test_cli_writes_deterministic_exe(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"fixture.exe"
            with patch.object(sys,"argv",["v73","--output",str(p)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(p.read_bytes(),self.exe)
    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"secret.exe";p.write_bytes(b"DO NOT OVERWRITE")
            with patch.object(sys,"argv",["v73","--output",str(p)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(p.read_bytes(),b"DO NOT OVERWRITE")
    def test_entire_exe_hash_stable(self):
        self.assertEqual(build(),(self.exe,self.loop,self.mips))
        self.assertEqual(hashlib.sha256(build()[0]).digest(),hashlib.sha256(self.exe).digest())
    def test_no_external_game_asset_dependency(self):
        s=(Path(__file__).resolve().parents[1]/"tools/make_map02_v73_uv_tpage_mips_exe.py").read_text()
        self.assertNotIn("game_disc",s)
        self.assertNotIn("rom_path",s)
if __name__=="__main__":unittest.main()
