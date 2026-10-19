#!/usr/bin/env python3
"""v181: exactly four genuine 32-bit MIPS LW/SW RAM provenance cases."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v173_vblank_quiet_mmio import patch_memory as v173
from tools.apply_map02_v174_vblank_read_quiet import patch_memory as v174
from tools.apply_map02_v175_dual_gpu_read_ports import patch_memory as v175
from tools.apply_map02_v176_narrow_gpu_mmio import patch_memory as v176
from tools.apply_map02_v180_nongpu_opcode_provenance import patch_memory as v180
from tools.apply_map02_v181_word_ram_opcodes import (
    CASES,make_variants,write_private,patch_memory,patch_frontend,
    original_native_oracle,witness
)
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

def fake_mem():
    return """u8 psxMemRead8(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;return 0;
}
u16 psxMemRead16(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;return 0;
}
u32 psxMemRead32(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;return 0;
}
void psxMemWrite8(psxRegisters *regs, u32 mem, u32 value) {
 (void)regs;(void)mem;(void)value;
}
void psxMemWrite16(psxRegisters *regs, u32 mem, u32 value) {
 (void)regs;(void)mem;(void)value;
}
void vh140_mmio_enable(unsigned mutate_expected) {
 (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs,u32 mem,u32 value){
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""

def full_memory():
    return patch_memory(v180(v176(v175(v174(v173(fake_mem()))))))

def fake_front():
    return ('\tint vh180_nongpu_verified_id=-1;\n'
            '\t\telse if (!strcmp(argv[i], "--vh180-nongpu-mips-0"))\n'
            '\tif (loadst_f) {\n')

class V181ExactLiveWordRAM(unittest.TestCase):
    def test_four_source_authored_mutants_from_single_signed_wait_word(self):
        image,stops,starts,wait_pc,ops=build()
        offset=2048+wait_pc-START
        self.assertEqual(ops[(wait_pc-START)//4:][:512],(0,)*512)
        self.assertEqual(image[0x4c:0x54],b"VH78SYN!")
        generated=make_variants()
        self.assertEqual(tuple(generated),tuple(x[0] for x in CASES))
        self.assertEqual(tuple(x[1] for x in CASES),
                         (0x8c000000,0x8c000004,0xac000000,0xac000004))
        for name,word,addr,writing in CASES:
            blob=generated[name]
            self.assertEqual(blob[:offset],image[:offset])
            self.assertEqual(blob[offset+4:],image[offset+4:])
            self.assertEqual(blob[offset:offset+4],word.to_bytes(4,"little"))
            self.assertEqual(addr%4,0)
            self.assertIn(writing,(0,1))
        with tempfile.TemporaryDirectory(prefix="vh181-signed-private-") as t:
            d=Path(t)
            created=write_private(d)
            self.assertEqual(len(created),4)
            self.assertTrue(all(x.stat().st_mode & 0o777==0o600 for x in created))
            with self.assertRaises(ValueError):write_private(d)

    def test_true_original_pcsx_read32_and_write32_not_standalone_fake_markers(self):
        source=full_memory()
        for token in (
            "vh181_observe(regs,mem,0u);",
            "vh181_observe(regs,mem,1u);",
            "regs->pc!=",
            "regs->code!=vh181_expected_word[vh181_case]",
            "vh181_seen++",
            "vh181_expected_addr",
            "vh181_expected_write",
        ):self.assertIn(token,source)
        self.assertLess(source.index("vh181_observe(regs,mem,0u);"),
                        source.index("vh180_observe_nongpu(regs,mem,2u,0u);"))
        self.assertLess(source.index("vh181_observe(regs,mem,1u);"),
                        source.index("if(vh173_wait_active) vh173_observe_wait_mmio(mem);"))
        self.assertNotIn("GPUwriteData(",witness())
        self.assertNotIn("psxRegs.cycle=",witness())
        with self.assertRaises(ValueError):patch_memory(source)

    def test_new_cli_has_four_distinct_modes_and_mandatory_negative_exit(self):
        s=patch_frontend(fake_front())
        native=original_native_oracle()
        for i in range(4):self.assertIn(f"--vh181-nongpu-word-{i}",s)
        for marker in (
            "VH181_NATIVE_GUEST_WORD_RAM_PASS",
            "VH181_NATIVE_WORD_UNOBSERVED_REFUSED",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "VH175_GUEST_MIPS_VBLANK_PORTS_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "return 84;",
        ):self.assertIn(marker,s)
        self.assertLess(native.index("vh176_arm_narrow(phase)!=0"),
                        native.index("vh181_arm((unsigned)vh181_nongpu_word_id,phase)!=0"))
        self.assertLess(native.index("vh181_disarm("),
                        native.index("vh176_disarm_narrow(phase)"))
        with self.assertRaises(ValueError):patch_frontend(s)

    def test_c99_compiled_live_opcode_and_ram_address_gate(self):
        compiler=os.environ.get("CC","cc")
        if not shutil.which(compiler):self.skipTest("C compiler missing")
        _,_,_,pc,_=build()
        header=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v) {
 (void)r;(void)a;(void)v;
}
"""
        code=f"""
int main(void) {{
    psxRegisters r={{0}};
    const u32 words[4]={{0x8c000000u,0x8c000004u,0xac000000u,0xac000004u}};
    for(unsigned kind=0;kind<4u;kind++)
      for(unsigned phase=0;phase<4u;phase++) {{
        if(vh173_arm_wait_quiet(phase)!=0 ||
           vh174_arm_wait_read(phase)!=0 ||
           vh175_arm_read_ports(phase)!=0 ||
           vh176_arm_narrow(phase)!=0 ||
           vh181_arm(kind,phase)!=0)return 1;
        r.pc={pc+4}u;
        r.code=words[kind]^1u;
        if(kind<2u)(void)psxMemRead32(&r,kind*4u);
        else psxMemWrite32(&r,(kind-2u)*4u,0u);
        if(vh181_count()!=0u)return 2;
        r.code=words[kind];
        if(kind<2u)(void)psxMemRead32(&r,kind*4u);
        else psxMemWrite32(&r,(kind-2u)*4u,0u);
        if(vh181_count()!=1u || vh181_faults()!=0u ||
           vh173_wait_mmio_faults()!=0u ||
           vh175_gp0_read_faults()!=0u || vh175_gp1_read_faults()!=0u ||
           vh176_narrow_total()!=0u)return 3;
        if(vh181_disarm(kind,phase)!=0 ||
           vh176_disarm_narrow(phase)!=0 ||
           vh175_disarm_read_ports(phase)!=0 ||
           vh174_disarm_wait_read(phase)!=0 ||
           vh173_disarm_wait_quiet(phase)!=0)return 4;
      }}
    puts("VH181_COMPILED_WORD_OPCODE_PC_PASS kinds=4 windows_each=4 wrong_opcode_refused=1 original_retail=0");
    return 0;
}}
"""
        with tempfile.TemporaryDirectory(prefix="vh181-nongpu-") as d:
            src=Path(d)/"native.c";exe=Path(d)/"native"
            src.write_text(header+full_memory()+code)
            comp=subprocess.run([compiler,"-std=c99","-Wall","-Wextra","-Werror","-pedantic",
                str(src),"-o",str(exe)],capture_output=True,text=True,timeout=40)
            self.assertEqual(comp.returncode,0,comp.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH181_COMPILED_WORD_OPCODE_PC_PASS",run.stdout)

    def test_native_workflow_guards_mips_opcode_and_negative_unmodified_exe(self):
        big=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v181-word-ram-opcodes.yml").read_text()
        for token in (
            "apply_map02_v181_word_ram_opcodes",
            "test_map02_v181_word_ram_opcodes.py",
            "--vh181-nongpu-word-",
            "V181_LW_RAM0.EXE","V181_LW_RAM4.EXE",
            "V181_SW_RAM0.EXE","V181_SW_RAM4.EXE",
            "VH181_NATIVE_GUEST_WORD_RAM_PASS",
            "VH181_NATIVE_WORD_UNOBSERVED_REFUSED",
            "VH181_NATIVE_RAM_WORD_PROVENANCE_PASS",
            "V181_UNMODIFIED.EXE",
            'test "$rc" -eq 84',
        ):self.assertIn(token,big)
        self.assertIn("test_map02_v180_nongpu_opcode_provenance.py",own)

if __name__=="__main__":
    unittest.main()
