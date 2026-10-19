#!/usr/bin/env python3
"""v178: self-authored genuine interpreter unaligned GPU wait sentinels."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.check_map02_v178_native_unaligned_routes import check, get_function, MARKER
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

MUTANTS={
    "LWL_GP0":(0x22,1,0x89090001,81,"VH175_VBLANK_GPU_READ_PORT_REFUSED phase=0 gp0="),
    "LWR_GP1":(0x26,6,0x99090006,81,"VH175_VBLANK_GPU_READ_PORT_REFUSED phase=0 gp0=0 gp1="),
    "SWL_GP0":(0x2a,2,0xa9090002,82,"VH176_NARROW_MMIO_REFUSED phase=0"),
    "SWR_GP1":(0x2e,5,0xb9090005,82,"VH176_NARROW_MMIO_REFUSED phase=0"),
}

def native_excerpt():
    return """
static void doLWL(psxRegisters *regs, u32 rt, u32 addr) {
    mem = psxMemRead32(regs, addr & ~3);
    doLoad(regs, rt, val);
}
static void doLWR(psxRegisters *regs, u32 rt, u32 addr) {
    mem = psxMemRead32(regs, addr & ~3);
    doLoad(regs, rt, val);
}
OP(psxLWL) { doLWL(regs_, _Rt_, _oB_); }
static void doSWL(psxRegisters *regs, u32 rt, u32 addr) {
    switch(addr & 3) {
      case 2:
        psxMemWrite16(regs, addr & ~3, val >> 8);
        psxMemWrite8( regs, addr, val >> 24); break;
      case 3: psxMemWrite32(regs, addr & ~3, val); break;
    }
}
static void doSWR(psxRegisters *regs, u32 rt, u32 addr) {
    switch(addr & 3) {
      case 0: psxMemWrite32(regs, addr, val); break;
      case 1:
        psxMemWrite8(regs, addr, val & 0xff);
        psxMemWrite16(regs, addr + 1, val >> 8); break;
      case 2: psxMemWrite16(regs, addr, val); break;
    }
}
OP(psxSWR) { doSWR(regs_, _Rt_, _oB_); }
"""

class V178UnalignedGPU(unittest.TestCase):
    def test_exactly_four_first_wait_nop_mutations(self):
        raw,stops,starts,pc,ops=build()
        index=(pc-START)//4
        self.assertEqual(len(stops),4)
        self.assertEqual(len(starts),4)
        self.assertEqual(raw[:8],b"PS-X EXE")
        self.assertEqual(raw[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(ops[index:index+512],(0,)*512)
        for kind,(opcode,offset,word,exit_code,marker) in MUTANTS.items():
            self.assertEqual(word,(opcode<<26)|(8<<21)|(9<<16)|offset)
            self.assertEqual((word>>21)&31,8)
            self.assertEqual((word>>16)&31,9)
            self.assertIn(exit_code,(81,82))
            self.assertTrue(marker.startswith("VH17"),kind)

    def test_pinned_interpreter_route_audit_requires_all_paths(self):
        source=native_excerpt()
        self.assertEqual(len(check(source)),4)
        self.assertEqual(len(check(source.replace(
            "psxMemWrite8(regs, addr, val & 0xff);",
            "psxMemWrite8 (regs, addr, val & 0xff);"))),4)
        self.assertIn("psxMemRead32",get_function(source,"doLWL"))
        self.assertIn("psxMemWrite16",get_function(source,"doSWR"))
        for mutation in (
            ("psxMemRead32(regs, addr & ~3)","psxMemRead8(regs, addr)"),
            ("psxMemWrite16(regs, addr & ~3","psxMemWrite8(regs, addr & ~3"),
            ("psxMemWrite16(regs, addr + 1","psxMemWrite16(regs, addr + 2"),
            ("switch(addr & 3)","switch(addr & 1)"),
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    check(source.replace(mutation[0],mutation[1]))
        with self.assertRaises(ValueError):check(source.replace("static void doLWR","static void doNOTLWR"))
        self.assertIn("original_retail=0",MARKER)

    def test_both_real_pinned_compilers_have_separate_positive_and_negatives(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v178-unaligned-gpu-mips.yml").read_text()
        for item in (
            "check_map02_v178_native_unaligned_routes",
            "test_map02_v178_unaligned_gpu_mips.py",
            "V178_SYNTHETIC.EXE",
            "V178_BAD_",
            "--vh176-mips-vblank-narrow-mmio",
            "VH178_PINNED_MIPS_UNALIGNED_GPU_ROUTES_PASS",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "VH175_VBLANK_GPU_READ_PORT_REFUSED",
            "VH176_NARROW_MMIO_REFUSED",
            "0x89090001","0x99090006","0xa9090002","0xb9090005",
            'test "$rc" -eq "$want_rc"',
        ):self.assertIn(item,workflow)
        self.assertIn("test_map02_v177_narrow_gpu_lanes.py",own)
        self.assertIn("original_retail_executed=0",own)

if __name__=="__main__":
    unittest.main()
