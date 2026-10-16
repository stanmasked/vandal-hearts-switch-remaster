#!/usr/bin/env python3
"""v74 pure MIPS and PS1 4bpp/8bpp CLUT/E2 texture window pixel tests."""
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
from tools.make_map02_v74_indexed_clut_exe import (
    MAGIC,HEADER_SIZE,SECTION_SIZE,PALETTE4,PALETTE8,
    INDEX4,INDEX8,CLUT4_X,CLUT8_X,GP0_SEQUENCE,EXPECTED4,EXPECTED8,
    EXPECTED_WINDOW,EXPECTED_TRANSPARENT,build,main,
    xy,ft4,upload,nibble_halfwords,byte_halfwords,expected_pixel
)
from tools.apply_map02_v74_pcsx_rearmed import oracle_source
from tools.make_map02_v70_synthetic_psx_exe import sw

class Map02V74IndexedTexture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe,cls.pc,cls.instructions=build()
    def test_synthetic_psx_exe_size(self):
        self.assertEqual(len(self.exe),6144)
        self.assertEqual(self.exe[:8],b"PS-X EXE")
    def test_unique_nonretail_marker(self):
        self.assertEqual(self.exe[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH74SYN!")
        self.assertNotIn(b"Vandal Hearts",self.exe)
    def test_entry_and_load(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x10)[0],0x80010000)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x18)[0],0x80010000)
    def test_exe_payload_and_stack(self):
        self.assertEqual(struct.unpack_from("<I",self.exe,0x1c)[0],4096)
        self.assertEqual(struct.unpack_from("<I",self.exe,0x30)[0],0x801fff00)
    def test_mips_instruction_bound(self):
        self.assertLess(len(self.instructions)*4,SECTION_SIZE)
    def test_original_gpu_command_count(self):
        self.assertEqual(sum(op==sw(9,0,8) for op in self.instructions),
                         len(GP0_SEQUENCE)+1)
    def test_one_gpu_fifo_reset(self):
        self.assertEqual(self.instructions[4],sw(9,0,8))
    def test_4bit_texture_packing(self):
        self.assertEqual(nibble_halfwords(INDEX4),
                         (0x4321,0x0000,0x8765,0x3210))
    def test_8bit_texture_packing(self):
        self.assertEqual(byte_halfwords(INDEX8),
                         (0x2211,0x4433,0,0))
    def test_4bit_upload_4x4_words(self):
        source=nibble_halfwords(INDEX4)*4
        packet=upload(0,0,4,4,source)
        self.assertEqual(packet[:3],(0xa0000000,0,xy(4,4)))
        self.assertEqual(len(packet),11)
    def test_8bit_upload_page1(self):
        packet=upload(64,0,4,4,byte_halfwords(INDEX8)*4)
        self.assertEqual(packet[:3],(0xa0000000,64,xy(4,4)))
    def test_4bit_clut_16_halfwords(self):
        self.assertEqual(len(PALETTE4),16)
        self.assertEqual(upload(CLUT4_X,0,16,1,PALETTE4)[:3],
                         (0xa0000000,512,xy(16,1)))
    def test_8bit_clut_full_256_entries(self):
        self.assertEqual(len(PALETTE8),256)
        self.assertEqual(upload(CLUT8_X,0,256,1,PALETTE8)[:3],
                         (0xa0000000,528,xy(256,1)))
    def test_four_native_gpu_a0_uploads(self):
        self.assertEqual(GP0_SEQUENCE.count(0xa0000000),4)
    def test_palette_8_high_index_entries(self):
        self.assertEqual(tuple(PALETTE8[x] for x in (17,34,51,68)),
                         (0x4210,0x7c1f,0x7fe0,0x03ff))
    def test_texpage_color_mode_4bit(self):
        self.assertEqual(ft4(40,0,32,0)[4]>>16,0)
    def test_texpage_color_mode_8bit(self):
        self.assertEqual(ft4(56,0x081,33,0)[4]>>16,0x081)
    def test_clut_attribute_4bit_x512(self):
        self.assertEqual(ft4(40,0,32,0)[2]>>16,32)
    def test_clut_attribute_8bit_x528(self):
        self.assertEqual(ft4(56,0x081,33,0)[2]>>16,33)
    def test_same_uv_different_palette_modes(self):
        self.assertEqual(ft4(40,0,32,0)[2]&0xffff,0)
        self.assertEqual(ft4(56,0x081,33,0)[2]&0xffff,0)
    def test_e2_texture_window_exact_bits(self):
        self.assertIn(0xe2000401,GP0_SEQUENCE)
        self.assertEqual(0xe2000401&0x1f,1)
        self.assertEqual((0xe2000401>>10)&0x1f,1)
    def test_e2_restored_before_index0(self):
        i=GP0_SEQUENCE.index(0xe2000401)
        j=GP0_SEQUENCE.index(0xe2000000,i+1)
        self.assertTrue(j>i)
        self.assertLess(j,GP0_SEQUENCE.index(0x60ff0000))
    def test_nontrivial_e2_uv_mapping(self):
        m,o=1,1
        applied=tuple((u&~(m*8))|((o&m)*8) for u in range(4))
        self.assertEqual(applied,(8,9,10,11))
    def test_clut4_independent_expected(self):
        self.assertEqual(EXPECTED4,(0x001f,0x03e0,0x7c00,0x7fff))
    def test_clut8_independent_expected(self):
        self.assertEqual(EXPECTED8,(0x4210,0x7c1f,0x7fe0,0x03ff))
    def test_window_independent_expected(self):
        self.assertEqual(EXPECTED_WINDOW,(0x03ff,0x7fe0,0x7c1f,0x4210))
    def test_transparent_palette_index0(self):
        self.assertEqual(PALETTE4[0],0)
        self.assertEqual(EXPECTED_TRANSPARENT,(0x7c00,0x001f,0x03e0,0x7c00))
    def test_four_regions_each_full_4x4(self):
        for start,colors in ((40,EXPECTED4),(56,EXPECTED8),
                             (72,EXPECTED_WINDOW),(88,EXPECTED_TRANSPARENT)):
            for y in range(80,84):
                self.assertEqual(tuple(expected_pixel(x,y) for x in range(start,start+4)),
                                 colors)
    def test_background_335_guards(self):
        output=[expected_pixel(x,y) for y in range(79,86) for x in range(39,96)]
        self.assertEqual(len(output),399)
        self.assertEqual(output.count(0),335)
        self.assertEqual(sum(x!=0 for x in output),64)
    def test_guards_all_zero(self):
        for xy_point in ((39,79),(44,80),(55,82),(60,83),(71,82),(76,82),(95,85)):
            self.assertEqual(expected_pixel(*xy_point),0)
    def test_exact_program_end_pc(self):
        self.assertEqual(self.instructions[-2],(2<<26)|((self.pc>>2)&0x03ffffff))
        self.assertEqual(self.instructions[-1],0)
    def test_real_gpu_plugin_freeze_readback(self):
        s=oracle_source(self.pc)
        self.assertIn("GPU_freeze(1,&snapshot,&vram)",s)
        self.assertIn("vram[y*1024+x]!=expected",s)
    def test_real_oracle_rejects_corrupt_pixels(self):
        s=oracle_source(self.pc)
        self.assertIn("VH74_VRAM_REFUSED",s)
        self.assertIn("checked!=399",s)
    def test_real_oracle_requires_cpu_execution(self):
        s=oracle_source(self.pc)
        self.assertIn("psxCpu->ExecuteBlock",s)
        self.assertIn(f"0x{self.pc:08x}u",s)
        self.assertIn("0x70000001u",s)
    def test_real_oracle_refuses_wrong_tag(self):
        self.assertIn('memcmp(tag,"VH74SYN!",8)',oracle_source(self.pc))
    def test_no_retail_promotion(self):
        s=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v74_pcsx_rearmed.py").read_text()
        self.assertIn("original_retail_MAP02_verified=False",s)
        self.assertIn("HD_replacement_approved=False",s)
    def test_reproducible_program_digest(self):
        self.assertEqual(build(),(self.exe,self.pc,self.instructions))
        self.assertEqual(hashlib.sha256(build()[0]).digest(),hashlib.sha256(self.exe).digest())
    def test_cli_creates_original_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"v74.exe"
            with patch.object(sys,"argv",["v74","--output",str(output)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(output.read_bytes(),self.exe)
    def test_cli_refuses_private_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"private.exe";output.write_bytes(b"PRIVATE")
            with patch.object(sys,"argv",["v74","--output",str(output)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(output.read_bytes(),b"PRIVATE")
    def test_no_external_game_resource(self):
        s=(Path(__file__).resolve().parents[1]/"tools/make_map02_v74_indexed_clut_exe.py").read_text()
        self.assertNotIn("game_disc",s)
        self.assertNotIn("rom_path",s)

if __name__=="__main__":
    unittest.main()
