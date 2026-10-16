#!/usr/bin/env python3
"""v71 independent MIPS GPU VRAM sample oracle and source patch tests."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch
from contextlib import redirect_stdout
from io import StringIO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v71_synthetic_vram_exe import (
    build,main,expected_color_at,GP0_SEQUENCE,HEADER_SIZE,SECTION_SIZE,
    START,MAGIC,MARKER_ADDR,MARKER_VALUE,
)
from tools.make_map02_v70_synthetic_psx_exe import lui,ori,sw
from tools.apply_map02_v71_pcsx_rearmed import CHECK_CODE

class V71VRAMPixelOracleTests(unittest.TestCase):
    def setUp(self):
        self.binary,self.loop,self.code=build()
    def test_clean_original_exe_signature(self):
        self.assertEqual(self.binary[:8],b"PS-X EXE")
        self.assertEqual(self.binary[0x4c:0x54],b"VH71SYN!")
    def test_separate_from_prior_exe_signature(self):
        self.assertNotEqual(MAGIC,b"VH70SYN!")
    def test_exact_4k_program(self):
        self.assertEqual(len(self.binary),HEADER_SIZE+SECTION_SIZE)
    def test_original_psx_loader_header(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x18)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.binary,0x1c)[0],SECTION_SIZE)
    def test_mips_little_endian_entry(self):
        self.assertEqual(self.binary[2048:2052],struct.pack("<I",lui(8,0x1f80)))
    def test_no_rom_content_in_fixture(self):
        self.assertNotIn(b"Vandal Hearts",self.binary)
        self.assertNotIn(b"Konami",self.binary)
    def test_cpu_gp1_fifo_reset_is_first_gpu_command(self):
        self.assertEqual(self.code[2:5],[lui(9,0x0100),ori(9,9,0),sw(9,0,8)])
    def test_explicit_ps1_drawing_area_and_offset(self):
        self.assertEqual(GP0_SEQUENCE[:3],(0xe3000000,0xe407ffff,0xe5000000))
    def test_explicit_mask_off_before_red(self):
        self.assertEqual(GP0_SEQUENCE[3],0xe6000000)
    def test_red_rectangle_packet(self):
        self.assertEqual(GP0_SEQUENCE[4:7],(0x600000ff,0x00100010,0x00040004))
    def test_mask_set_bit_before_blue(self):
        self.assertEqual(GP0_SEQUENCE[7],0xe6000001)
    def test_blue_rectangle_packet(self):
        self.assertEqual(GP0_SEQUENCE[8:11],(0x60ff0000,0x00100018,0x00040004))
    def test_mask_check_set_before_overwrite(self):
        self.assertEqual(GP0_SEQUENCE[11],0xe6000002)
    def test_green_rectangle_overlap(self):
        self.assertEqual(GP0_SEQUENCE[12:15],(0x6000ff00,0x00100018,0x00040004))
    def test_all_gp0_words_emitted_to_mips_store(self):
        self.assertEqual(sum(1 for w in self.code if w==sw(9,0,8)),len(GP0_SEQUENCE)+1)  # GP1 also uses t0
    def test_expected_flat_red_bgr555(self):
        self.assertEqual(expected_color_at(16,16),0x001f)
        self.assertEqual(expected_color_at(19,19),0x001f)
    def test_expected_masked_blue_bgr555(self):
        self.assertEqual(expected_color_at(24,16),0xfc00)
        self.assertEqual(expected_color_at(27,19),0xfc00)
    def test_green_overwrite_must_not_replace_masked_blue(self):
        self.assertNotEqual(expected_color_at(24,16),0x03e0)
    def test_expected_outside_background(self):
        for p in ((15,15),(21,19),(23,17),(28,19),(29,21)):
            self.assertEqual(expected_color_at(*p),0)
    def test_oracle_probes_105_pixels(self):
        expected=[expected_color_at(x,y) for y in range(15,22) for x in range(15,30)]
        self.assertEqual(len(expected),105)
        self.assertEqual(sum(x==0x001f for x in expected),16)
        self.assertEqual(sum(x==0xfc00 for x in expected),16)
        self.assertEqual(sum(x==0 for x in expected),73)
    def test_cpu_marker_ram_location_and_value(self):
        self.assertEqual(MARKER_ADDR,0x80011000)
        self.assertEqual(MARKER_VALUE,0x70000001)
    def test_bounded_self_loop_program_counter(self):
        self.assertEqual(self.loop,0x800100e0)
        self.assertEqual(self.code[-1],0)
    def test_cli_writes_exact_exe(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"v71-synthetic.exe"
            with mock_patch.object(sys,"argv",["v71","--output",str(path)]),redirect_stdout(StringIO()):
                main()
            self.assertEqual(path.read_bytes(),self.binary)
    def test_cli_refuses_existing_private_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"private.exe";path.write_bytes(b"DO-NOT-OVERWRITE")
            with mock_patch.object(sys,"argv",["v71","--output",str(path)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(path.read_bytes(),b"DO-NOT-OVERWRITE")
    def test_pixel_oracle_uses_real_gpu_freeze_save(self):
        self.assertIn("GPU_freeze(1,&freeze,&vram)",CHECK_CODE)
        self.assertNotIn("GPU_freeze(0,",CHECK_CODE)
    def test_no_user_provenance_promotion(self):
        self.assertIn("VH71_VRAM_ORACLE_PASS",CHECK_CODE)
        self.assertIn("VH71_EXE_REFUSED",CHECK_CODE)
        self.assertNotIn("original_retail_MAP02_verified=true",CHECK_CODE)
    def test_refuses_unknown_exe(self):
        self.assertIn('memcmp(tag,"VH71SYN!",8)',CHECK_CODE)
    def test_checks_real_vram_not_plugin_callback_count(self):
        self.assertIn("vram[y*1024+x]!=expected",CHECK_CODE)
        self.assertNotIn("orig_word(",CHECK_CODE)
    def test_mask_and_guard_samples_checked(self):
        self.assertIn("expected=0xfc00",CHECK_CODE)
        self.assertIn("checked!=105",CHECK_CODE)
    def test_generator_deterministic(self):
        image,pc,code=build()
        self.assertEqual((image,pc,code),(self.binary,self.loop,self.code))
        self.assertEqual(hashlib.sha256(image).digest(),hashlib.sha256(self.binary).digest())

if __name__=="__main__":unittest.main()
