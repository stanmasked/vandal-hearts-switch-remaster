#!/usr/bin/env python3
"""v70 original PS-X EXE MIPS GPU port program and pinned CPU smoke tests."""
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
from tools.make_map02_v70_synthetic_psx_exe import (
    build,main,START,HEADER_SIZE,SECTION_SIZE,MARKER_ADDR,MARKER_VALUE,MAGIC,
    lui,ori,addiu,sw,
)
from tools.apply_map02_v69_pcsx_rearmed import once

class V70CpuExeTests(unittest.TestCase):
    def setUp(self):
        self.binary,self.loop,self.instructions=build()
    def test_full_psx_exe_header_and_payload(self):
        self.assertEqual(len(self.binary),4096)
        self.assertEqual(self.binary[:8],b"PS-X EXE")
        self.assertEqual(len(self.binary[2048:]),SECTION_SIZE)
    def test_original_diagnostic_marker(self):
        self.assertEqual(self.binary[0x4c:0x54],MAGIC)
        self.assertNotIn(b"Vandal",self.binary)
    def test_entry_and_load_offset(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",self.binary,0x18)[0],START)
    def test_section_size_exact(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x1c)[0],2048)
    def test_stack_in_ps1_ram(self):
        self.assertEqual(struct.unpack_from("<I",self.binary,0x30)[0],0x801fff00)
    def test_payload_is_little_endian_mips(self):
        self.assertEqual(self.binary[2048:2052],struct.pack("<I",lui(8,0x1f80)))
    def test_gp0_mmio_address_setup(self):
        self.assertEqual(self.instructions[0:2],[lui(8,0x1f80),ori(8,8,0x1810)])
    def test_gp0_mask_command_and_store(self):
        self.assertEqual(self.instructions[2:4],[lui(9,0xe600),sw(9,0,8)])
    def test_gp0_rectangle_exact_four_total_words(self):
        self.assertEqual([self.instructions[x] for x in (3,6,8,10)],[sw(9,0,8)]*4)
    def test_gp0_flat_rectangle_opcode(self):
        self.assertEqual(self.instructions[4],lui(9,0x6000))
        self.assertEqual(self.instructions[5],ori(9,9,0x00ff))
    def test_gp0_rectangle_position_and_dimensions(self):
        self.assertEqual(self.instructions[7],ori(9,0,0))
        self.assertEqual(self.instructions[9],ori(9,0,0x0404))
    def test_gp1_fifo_reset_command(self):
        self.assertEqual(self.instructions[11:14],
                         [addiu(8,8,4),lui(9,0x0100),sw(9,0,8)])
    def test_cpu_marker_ram_address(self):
        self.assertEqual(MARKER_ADDR,0x80011000)
        self.assertEqual(self.instructions[14:16],[lui(10,0x8001),ori(10,10,0x1000)])
    def test_cpu_marker_value_and_store(self):
        self.assertEqual(MARKER_VALUE,0x70000001)
        self.assertEqual(self.instructions[16:19],
                         [lui(9,0x7000),ori(9,9,1),sw(9,0,10)])
    def test_exact_branch_pc_for_bounded_execute_block(self):
        self.assertEqual(self.loop,0x8001004c)
        self.assertEqual(self.instructions[-2],(0x02<<26)|((self.loop>>2)&0x3ffffff))
        self.assertEqual(self.instructions[-1],0)
    def test_no_external_assets_or_network_in_generator(self):
        source=(Path(__file__).resolve().parents[1]/"tools/make_map02_v70_synthetic_psx_exe.py").read_text()
        self.assertNotIn("requests.",source)
        self.assertNotIn("urllib",source)
    def test_deterministic_hash(self):
        a,l,ops=build()
        self.assertEqual((a,l,ops),(self.binary,self.loop,self.instructions))
        self.assertEqual(hashlib.sha256(a).digest(),hashlib.sha256(self.binary).digest())
    def test_cli_generates_file_with_expected_size(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"synthetic.exe"
            with mock_patch.object(sys,"argv",["v70","--output",str(out)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(out.read_bytes(),self.binary)
    def test_cli_refuses_overwrite_of_existing_binary(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"secret.exe";out.write_text("PRIVATE")
            with mock_patch.object(sys,"argv",["v70","--output",str(out)]),self.assertRaises(SystemExit):
                main()
            self.assertEqual(out.read_text(),"PRIVATE")
    def test_patch_unique_anchor_refuses_unpinned_edit(self):
        with self.assertRaises(ValueError):once("abc","no match","insert","v70")
        with self.assertRaises(ValueError):once("abc abc","abc","insert","v70")
    def test_source_inspection_preserves_existing_v69_mode(self):
        source=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v70_pcsx_rearmed.py").read_text()
        self.assertIn("vh69_core_smoke",source)
        self.assertIn("--vh70-exe-smoke",source)
        self.assertIn("v69_apply(root)",source)
    def test_source_requires_interpreter_and_marker(self):
        source=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v70_pcsx_rearmed.py").read_text()
        self.assertIn("Config.Cpu!=1",source)
        self.assertIn("VH70SYN!",source)
        self.assertIn("psxCpu->ExecuteBlock",source)
    def test_source_contains_bounded_interpreter_program_counter_gate(self):
        source=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v70_pcsx_rearmed.py").read_text()
        self.assertIn("0x8001004cu",source)
        self.assertIn("VH70_MIPS_EXEC_PASS",source)
    def test_source_hard_refusal_for_unknown_game_file(self):
        source=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v70_pcsx_rearmed.py").read_text()
        self.assertIn("VH70_SYNTHETIC_EXE_REFUSED",source)
        self.assertIn("return 2;",source)
    def test_no_provenance_promotion(self):
        source=(Path(__file__).resolve().parents[1]/"tools/apply_map02_v70_pcsx_rearmed.py").read_text()
        self.assertIn("original_retail_MAP02_verified=False",source)
        self.assertIn("HD_replacement_approved=False",source)

if __name__=="__main__":
    unittest.main()
