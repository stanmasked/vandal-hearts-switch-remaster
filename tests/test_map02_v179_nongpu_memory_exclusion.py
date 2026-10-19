#!/usr/bin/env python3
"""v179: verify true MIPS VBlank non-GPU memory operations cannot false-positive."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
from struct import unpack
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.make_map02_v179_nongpu_mips_exes import (
    MUTANTS, OUTPUT_PREFIX, mips_word, originals, generate, write_private
)
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

class V179NoFalseGPUReadOrWrite(unittest.TestCase):
    def test_exactly_eight_genuine_mips_cpu_variants_and_register_boundaries(self):
        expected={
            "LB_BELOW_GP0":0x8100ffff,
            "LHU_ABOVE_GP1":0x95000008,
            "LWL_BELOW_GP0":0x8900ffff,
            "LWR_ABOVE_GP1":0x99000008,
            "SB_RAM0":0xa0000000,
            "SH_RAM2":0xa4000002,
            "SWL_RAM2":0xa8000002,
            "SWR_RAM1":0xb8000001,
        }
        self.assertEqual(len(MUTANTS),8)
        for label,((opcode,rs,offset),word) in zip(MUTANTS,zip(MUTANTS.values(),expected.values())):
            self.assertEqual(label,list(expected)[list(MUTANTS).index(label)])
            self.assertEqual(mips_word(opcode,rs,offset),word)
            self.assertEqual((word>>16)&31,0)
        self.assertEqual({offset for _,base,offset in MUTANTS.values() if base==8},{-1,8})
        self.assertEqual({offset for _,base,offset in MUTANTS.values() if base==0},{0,1,2})
        with self.assertRaises(ValueError):mips_word(0x20,8,-32769)

    def test_exact_single_wait_word_mutation_and_signed_original_image(self):
        original,index=originals()
        raw,stops,starts,wait_pc,ops=build()
        self.assertEqual(original,raw)
        self.assertEqual((wait_pc-START)//4,index)
        self.assertEqual(original[:8],b"PS-X EXE")
        self.assertEqual(original[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(ops[index:index+512],(0,)*512)
        off=2048+index*4
        for label,data in generate().items():
            self.assertEqual(len(data),len(raw),label)
            self.assertEqual(data[:off],raw[:off],label)
            self.assertEqual(data[off+4:],raw[off+4:],label)
            self.assertNotEqual(data[off:off+4],raw[off:off+4],label)
            self.assertEqual(unpack("<I",data[off:off+4])[0],
                             mips_word(*MUTANTS[label]))
            self.assertEqual(data[0x4c:0x54],b"VH78SYN!")

    def test_private_outputs_never_overwrite_or_publish_original_game(self):
        with tempfile.TemporaryDirectory(prefix="vh179-positive-") as root:
            d=Path(root)
            written=write_private(d)
            self.assertEqual(len(written),8)
            self.assertTrue(all(x.exists() and x.name.startswith(OUTPUT_PREFIX)
                                and x.stat().st_mode & 0o777==0o600
                                for x in written))
            with self.assertRaises(ValueError):write_private(d)
            self.assertEqual(set(x.name for x in written),
                             {OUTPUT_PREFIX+x+".EXE" for x in MUTANTS})

    def test_native_ci_runs_all_eight_real_synthetic_vblank_pixels(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v179-nongpu-memory-exclusion.yml").read_text()
        for needle in (
            "make_map02_v179_nongpu_mips_exes",
            "V179_NONGPU_",
            "LB_BELOW_GP0", "LHU_ABOVE_GP1",
            "LWL_BELOW_GP0", "LWR_ABOVE_GP1",
            "SB_RAM0", "SH_RAM2", "SWL_RAM2", "SWR_RAM1",
            "--vh176-mips-vblank-narrow-mmio",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "VH175_GUEST_MIPS_VBLANK_PORTS_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "VH78_PHASE_PASS phase=",
            "test_map02_v179_nongpu_memory_exclusion.py",
            "VH179_NATIVE_NONGPU_MEMORY_NO_FALSE_POSITIVE_PASS",
        ):
            self.assertIn(needle,workflow)
        self.assertIn("test_map02_v178_unaligned_gpu_mips.py",own)
        self.assertIn("original_retail_executed=0",own)

if __name__=="__main__":
    unittest.main()
