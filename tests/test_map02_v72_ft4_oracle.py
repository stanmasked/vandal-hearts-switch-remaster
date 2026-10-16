#!/usr/bin/env python3
"""v72 independent PS1 15bpp A0 VRAM texture/FT4/STP ABR regressions."""
from __future__ import annotations
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch
from contextlib import redirect_stdout
from io import StringIO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v72_ft4_mips_exe import (
    build,main,ft4,GP0_SEQUENCE,SCENES,texture_payload,
    expected_pixel,HEADER_SIZE,SECTION_SIZE,MAGIC,START,xy,
)
from tools.make_map02_v70_synthetic_psx_exe import sw
from tools.apply_map02_v72_pcsx_rearmed import oracle_source

class V72FT4VRAMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary,cls.loop,cls.code=build()
    def test_psx_exe_is_exactly_four_kib(self):
        self.assertEqual(len(self.binary),4096)
        self.assertEqual(self.binary[:8],b"PS-X EXE")
    def test_exe_is_not_v71_or_retail(self):
        self.assertEqual(self.binary[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH72SYN!")
        self.assertNotIn(b"Vandal",self.binary)
    def test_exe_mips_entry(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.binary,0x18)[0],START)
    def test_exe_section_size(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x1c)[0],SECTION_SIZE)
    def test_exe_stack_in_ram(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x30)[0],0x801fff00)
    def test_uses_15bpp_texture_page(self):
        self.assertIn(0xe1000100,GP0_SEQUENCE)
    def test_upload_command_starts_with_a0(self):
        pos=GP0_SEQUENCE.index(0xa0000000)
        self.assertEqual(GP0_SEQUENCE[pos:pos+3],(0xa0000000,0,xy(8,4)))
    def test_upload_has_eight_texels_per_scanline(self):
        self.assertEqual(len(texture_payload()),16)
        self.assertEqual(texture_payload()[:4],(
            0x001f001f,0x001f001f,0x801f801f,0x801f801f))
    def test_upload_has_four_scanlines(self):
        self.assertEqual(texture_payload(),texture_payload()[:4]*4)
    def test_cpu_stores_all_gp0_words(self):
        self.assertEqual(sum(w==sw(9,0,8) for w in self.code),
                         len(GP0_SEQUENCE)+1) # +1 GP1
    def test_four_opaque_blue_backdrops(self):
        self.assertEqual(GP0_SEQUENCE.count(0x60ff0000),4)
        for _,x,_,_,_,_ in SCENES:
            self.assertIn(xy(x,32),GP0_SEQUENCE)
    def test_raw_textured_quad_length_nine(self):
        for name,x,u,semi,abr,want in SCENES:
            self.assertEqual(len(ft4(x,u,semi,abr)),9)
    def test_opaque_texture_opcode(self):
        self.assertEqual(ft4(64,0,False,0)[0],0x2d000000)
    def test_semiblend_texture_opcode(self):
        self.assertEqual(ft4(80,4,True,0)[0],0x2f000000)
    def test_tpage_15bpp_abr0(self):
        self.assertEqual(ft4(80,4,True,0)[4]>>16,0x100)
    def test_tpage_15bpp_abr1(self):
        self.assertEqual(ft4(112,4,True,1)[4]>>16,0x120)
    def test_clut_empty_when_15bpp(self):
        for name,x,u,semi,abr,want in SCENES:
            self.assertEqual(ft4(x,u,semi,abr)[2]>>16,0)
    def test_nonzero_texture_u_for_masked_texels(self):
        self.assertEqual(ft4(80,4,True,0)[2]&0xff,4)
        self.assertEqual(ft4(80,4,True,0)[4]&0xff,8)
    def test_vertex_layout(self):
        self.assertEqual(ft4(64,0,False,0)[1],xy(64,32))
        self.assertEqual(ft4(64,0,False,0)[3],xy(68,32))
        self.assertEqual(ft4(64,0,False,0)[5],xy(64,36))
        self.assertEqual(ft4(64,0,False,0)[7],xy(68,36))
    def test_all_four_ft4_opcodes_in_sequence(self):
        self.assertEqual(GP0_SEQUENCE.count(0x2d000000),1)
        self.assertEqual(GP0_SEQUENCE.count(0x2f000000),3)
    def test_abr0_average_formula_is_independent(self):
        blue=31
        red=31
        value=0x8000|((blue//2)<<10)|(red//2)
        self.assertEqual(value,0xbc0f)
    def test_abr1_additive_formula(self):
        blue=31
        red=31
        value=0x8000|(min(31,blue)<<10)|min(31,red)
        self.assertEqual(value,0xfc1f)
    def test_opaque_raw_texture_oracle(self):
        self.assertEqual(expected_pixel(64,32),0x001f)
        self.assertEqual(expected_pixel(67,35),0x001f)
    def test_stp_average_oracle(self):
        self.assertEqual(expected_pixel(80,32),0xbc0f)
        self.assertEqual(expected_pixel(83,35),0xbc0f)
    def test_texture_without_stp_must_ignore_abe(self):
        self.assertEqual(expected_pixel(96,32),0x001f)
        self.assertNotEqual(expected_pixel(96,32),0xbc0f)
    def test_stp_additive_oracle(self):
        self.assertEqual(expected_pixel(112,32),0xfc1f)
    def test_unpainted_guard_zero(self):
        for point in ((63,31),(63,32),(76,33),(92,33),(108,33),(116,37)):
            self.assertEqual(expected_pixel(*point),0)
    def test_oracle_checks_all_378_pixels(self):
        data=[expected_pixel(x,y) for y in range(31,38) for x in range(63,117)]
        self.assertEqual(len(data),378)
        self.assertEqual(data.count(0),314)
        self.assertEqual(data.count(0x001f),32)
        self.assertEqual(data.count(0xbc0f),16)
        self.assertEqual(data.count(0xfc1f),16)
    def test_emitted_mips_program_fits_2kb(self):
        self.assertLessEqual(len(self.code)*4,SECTION_SIZE)
        self.assertEqual(self.binary[HEADER_SIZE:HEADER_SIZE+4],struct.pack("<I",self.code[0]))
    def test_mips_jump_delay_slot(self):
        self.assertEqual(self.code[-1],0)
        self.assertEqual(self.code[-2],(2<<26)|((self.loop>>2)&0x03ffffff))
    def test_real_gpu_freeze_vram_oracle(self):
        source=oracle_source(self.loop)
        self.assertIn("GPU_freeze(1,&snapshot,&vram)",source)
        self.assertIn("vram[y*1024+x]!=expected",source)
    def test_real_oracle_requires_exact_mips_pc(self):
        self.assertIn(f"0x{self.loop:08x}u",oracle_source(self.loop))
        self.assertIn("VH72_MIPS_MARKER_REFUSED",oracle_source(self.loop))
    def test_oracle_exposes_counts_not_raw_pixel_data(self):
        source=oracle_source(self.loop)
        self.assertIn("VH72_FT4_VRAM_REFUSED",source)
        self.assertNotIn("VRAM_UPLOAD",source)
    def test_oracle_rejects_untagged_exe(self):
        self.assertIn('memcmp(tag,"VH72SYN!",8)',oracle_source(self.loop))
    def test_generator_is_stable(self):
        self.assertEqual(build(),(self.binary,self.loop,self.code))
        self.assertEqual(hashlib.sha256(build()[0]).hexdigest(),
                         hashlib.sha256(self.binary).hexdigest())
    def test_cli_writes_synthetic_exe(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"new-synthetic.exe"
            with mock_patch.object(sys,"argv",["v72","--output",str(p)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(p.read_bytes(),self.binary)
    def test_cli_refuses_overwrite_private_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"private.exe";p.write_bytes(b"PRIVATE DATA")
            with mock_patch.object(sys,"argv",["v72","--output",str(p)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(p.read_bytes(),b"PRIVATE DATA")
    def test_diagnostic_keeps_retail_hard_gates_closed(self):
        from tools.apply_map02_v72_pcsx_rearmed import apply
        self.assertIn("original_retail_MAP02_verified=False",Path(
            sys.modules[apply.__module__].__file__).read_text())
    def test_avoids_copying_any_retail_texture(self):
        source=(Path(__file__).resolve().parents[1]/"tools/make_map02_v72_ft4_mips_exe.py").read_text()
        self.assertNotIn("game_disc",source)
        self.assertNotIn("rom_path",source)

if __name__=="__main__":
    unittest.main()
