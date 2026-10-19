#!/usr/bin/env python3
"""MAP02 v183: real PCSX guest SW→LW→XORI→SW memory data oracle."""
from __future__ import annotations
from pathlib import Path
from struct import unpack_from
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v183_native_ram_values import (
    RAM_ADDRESS,VALUE,TRANSFORMED,SEED0,SEED1,
    MUTATIONS,signed_sequence,make_variants,write_private,
    native_value_oracle,patch_frontend,lw,xori
)
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

def guest_memory_result(words):
    """Small independent MIPS-I semantics oracle, including load delay."""
    registers=[0]*32
    memory={RAM_ADDRESS:SEED0,RAM_ADDRESS+4:SEED1}
    delayed=None
    for word in words:
        op=word>>26
        rs=(word>>21)&31
        rt=(word>>16)&31
        imm=word&0xffff
        pending=None
        if word==0:
            pass
        elif op==0x0f:
            registers[rt]=(imm<<16)&0xffffffff
        elif op==0x0d:
            registers[rt]=(registers[rs]|imm)&0xffffffff
        elif op==0x0e:
            registers[rt]=(registers[rs]^imm)&0xffffffff
        elif op==0x2b:
            addr=(registers[rs]+(imm if imm<0x8000 else imm-0x10000))&0xffffffff
            memory[addr]=registers[rt]
        elif op==0x23:
            addr=(registers[rs]+(imm if imm<0x8000 else imm-0x10000))&0xffffffff
            pending=(rt,memory.get(addr,0))
        else:
            raise AssertionError(f"unexpected synthetic MIPS operation {op}")
        if delayed is not None:
            registers[delayed[0]]=delayed[1]
        delayed=pending
        registers[0]=0
    return memory

class V183NativeRAMData(unittest.TestCase):
    def test_signed_mips_sequence_has_clobber_load_delay_and_two_distinct_values(self):
        seq=signed_sequence()
        self.assertEqual(len(seq),9)
        self.assertEqual(seq[5],lw(23,0,22))
        self.assertEqual(seq[6],0)
        self.assertEqual(seq[7],xori(23,23,0xffff))
        self.assertEqual(VALUE,0x51a7c3d9)
        self.assertEqual(TRANSFORMED,0x51a73c26)
        self.assertEqual(RAM_ADDRESS,0x001e0000)
        result=guest_memory_result(seq)
        self.assertEqual(result,{RAM_ADDRESS:VALUE,RAM_ADDRESS+4:TRANSFORMED})
        self.assertNotEqual(VALUE,SEED0)
        self.assertNotEqual(TRANSFORMED,SEED1)

    def test_missing_first_guest_store_or_load_cannot_pass_actual_ram_values(self):
        seq=signed_sequence()
        for index in (3,5):
            bad=list(seq)
            bad[index]=0
            state=guest_memory_result(bad)
            self.assertNotEqual(
                (state[RAM_ADDRESS],state[RAM_ADDRESS+4]),
                (VALUE,TRANSFORMED)
            )
        missing_sw=list(seq);missing_sw[3]=0
        self.assertEqual(guest_memory_result(missing_sw)[RAM_ADDRESS],SEED0)
        missing_lw=list(seq);missing_lw[5]=0
        self.assertEqual(guest_memory_result(missing_lw)[RAM_ADDRESS+4],0x0000ff00)

    def test_three_private_images_mutate_only_nine_signed_wait_instructions(self):
        base,_,_,wait_pc,ops=build()
        index=(wait_pc-START)//4
        off=2048+index*4
        self.assertEqual(tuple(ops[index:index+512]),(0,)*512)
        variants=make_variants()
        self.assertEqual(tuple(variants),MUTATIONS)
        for name,image in variants.items():
            self.assertEqual(len(image),len(base))
            self.assertEqual(image[:off],base[:off])
            self.assertEqual(image[off+36:],base[off+36:])
            seq=tuple(unpack_from("<I",image,off+i*4)[0] for i in range(9))
            reference=list(signed_sequence())
            if name=="MISSING_SW":reference[3]=0
            if name=="MISSING_LW":reference[5]=0
            self.assertEqual(seq,tuple(reference))
            self.assertEqual(image[0x4c:0x54],b"VH78SYN!")
        with tempfile.TemporaryDirectory(prefix="vh183-private-test-") as d:
            folder=Path(d)
            self.assertEqual(write_private(folder),3)
            for name in MUTATIONS:
                path=folder/("V183_RAM_"+name+".EXE")
                self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(ValueError):write_private(folder)

    def test_native_oracle_checks_real_pcsx_memory_on_every_vblank_before_pixel_pass(self):
        src=native_value_oracle()
        for marker in (
            "psxMemWrite32(&psxRegs,0x001e0000u,0x1478295au);",
            "psxMemWrite32(&psxRegs,0x001e0004u,0xd15ea5edu);",
            "psxMemRead32(&psxRegs,0x001e0000u)",
            "psxMemRead32(&psxRegs,0x001e0004u)",
            "VH183_NATIVE_RAM_VALUE_REFUSED",
            "VH183_NATIVE_GUEST_RAM_VALUES_PASS",
            "vh183_ram_windows!=4u",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "return 85;",
        ):self.assertIn(marker,src)
        self.assertLess(src.index("vh183_first=psxMemRead32"),
                        src.index("int vh176_disarmed=vh176_disarm_narrow(phase)"))
        self.assertLess(src.index("VH183_NATIVE_RAM_VALUE_REFUSED"),
                        src.index("VH176_NARROW_MMIO_REFUSED"))
        mock=('\tint vh181_nongpu_word_id=-1;\n'
              '\t\telse if (!strcmp(argv[i], "--vh181-nongpu-word-0"))\n'
              '\tif (loadst_f) {\n')
        patched=patch_frontend(mock)
        self.assertIn("--vh183-guest-ram-values",patched)
        with self.assertRaises(ValueError):patch_frontend(patched)

    def test_ci_includes_native_positive_and_two_mips_instruction_negative_controls(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        other=(ROOT/".github/workflows/map02-v183-native-ram-values.yml").read_text()
        for x in (
            "apply_map02_v183_native_ram_values",
            "test_map02_v183_native_ram_values.py",
            "for kind in CORRECT MISSING_SW MISSING_LW; do",
            "V183_RAM_$kind.EXE","--vh183-guest-ram-values",
            "VH183_NATIVE_GUEST_RAM_VALUES_PASS",
            "VH183_NATIVE_RAM_VALUE_REFUSED",
            "VH183_NATIVE_GUEST_RAM_DATA_PASS",
            'test "$rc" -eq 85'
        ):self.assertIn(x,native)
        self.assertIn("test_map02_v182_lw_sw_identity_mismatch.py",other)

if __name__=="__main__":
    unittest.main()
