#!/usr/bin/env python3
"""v180: native true guest MIPS opcode/PC/address receipt, not mere pixel pass."""
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
from tools.apply_map02_v173_vblank_quiet_mmio import patch_memory as v173_mem
from tools.apply_map02_v174_vblank_read_quiet import patch_memory as v174_mem
from tools.apply_map02_v175_dual_gpu_read_ports import patch_memory as v175_mem
from tools.apply_map02_v176_narrow_gpu_mmio import patch_memory as v176_mem
from tools.apply_map02_v180_nongpu_opcode_provenance import (
    patch_memory, patch_frontend, verified_oracle, witness_source, CASES
)
from tools.make_map02_v179_nongpu_mips_exes import MUTANTS,mips_word,generate
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

def all_memory():
    return patch_memory(v176_mem(v175_mem(v174_mem(v173_mem(fake_mem())))))

def fake_front():
    return ('\tint vh176_mips_vblank_narrow_mmio_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh176-mips-vblank-narrow-mmio"))\n'
            '\tif (loadst_f) {\n')

class V180GuestOpcodeIsActuallyExecuted(unittest.TestCase):
    def test_all_eight_mips_opcodes_and_native_case_mapping_are_source_bound(self):
        data,stops,starts,pc,ops=build()
        idx=(pc-START)//4
        self.assertEqual(ops[idx:idx+512],(0,)*512)
        self.assertEqual(len(CASES),8)
        self.assertEqual(tuple(x[0] for x in CASES),tuple(MUTANTS))
        for i,case in enumerate(CASES):
            opcode=mips_word(*MUTANTS[case[0]])
            self.assertIn(f"0x{opcode:08x}u",witness_source())
            self.assertEqual(generate()[case[0]][2048+4*idx:2048+4*idx+4],
                             opcode.to_bytes(4,"little"))
            self.assertTrue(0<=i<8)

    def test_memory_hooks_are_before_real_pinned_accessor_read_or_write(self):
        source=all_memory()
        for t in (
            "vh180_observe_nongpu(regs,mem,0u,0u);",
            "vh180_observe_nongpu(regs,mem,1u,0u);",
            "vh180_observe_nongpu(regs,mem,2u,0u);",
            "vh180_observe_nongpu(regs,mem,0u,1u);",
            "vh180_observe_nongpu(regs,mem,1u,1u);",
            "regs->pc!=",
            "regs->code!=vh180_expected_word[kind]",
            "vh180_seen1++",
            "vh180_seen2++",
        ):self.assertIn(t,source)
        for t in ("GPUwriteData(", "psxRegs.cycle="):
            self.assertNotIn(t,witness_source())
        with self.assertRaises(ValueError):patch_memory(source)

    def test_frontend_refuses_missing_opcode_and_requires_four_real_windows(self):
        front=patch_frontend(fake_front())
        oracle=verified_oracle()
        for i in range(8):self.assertIn(f"--vh180-nongpu-mips-{i}",front)
        for token in (
            "VH180_GUEST_OPCODE_UNOBSERVED_REFUSED",
            "VH180_NONGPU_GUEST_OPCODE_EXECUTED_PASS",
            "vh180_seen_windows!=4u",
            "vh180_total_primary<4u",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "VH175_GUEST_MIPS_VBLANK_PORTS_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
        ):self.assertIn(token,front)
        self.assertLess(oracle.index("vh176_arm_narrow(phase)!=0"),
                        oracle.index("vh180_arm_nongpu((unsigned)vh180_nongpu_verified_id,phase)!=0"))
        self.assertLess(oracle.index("vh180_disarm_nongpu"),
                        oracle.index("vh176_disarm_narrow(phase)"))
        self.assertLess(oracle.index("VH180_GUEST_OPCODE_UNOBSERVED_REFUSED"),
                        oracle.index("VH176_NARROW_MMIO_REFUSED"))
        with self.assertRaises(ValueError):patch_frontend(front)

    def test_compiled_exact_accessors_refuse_forged_opcode_and_allow_nongpu(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("no C compiler")
        raw,stops,starts,pc,ops=build()
        head=f"""
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {{u32 pc;u32 code;}} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v){{
 (void)r;(void)a;(void)v;
}}
"""
        cases="\n".join(
            "{" + f"{mips_word(*MUTANTS[x[0]])}u,{x[1]}u,{x[2]}u,{x[3]}u,"
            +f"{x[4] if x[4]>=0 else 4294967295}u,{x[5] if x[5]>=0 else 4294967295}u,{x[6]}u"
            +"}," for x in CASES
        )
        tail=f"""
typedef struct {{u32 opcode,width,writing,addr,width2,writing2,addr2;}} test_case;
static const test_case test_cases[8]={{
{cases}
}};
static void memory_touch(psxRegisters *r,unsigned width,unsigned writing,u32 addr) {{
    if(writing) {{
        if(width==0)psxMemWrite8(r,addr,0u);
        else if(width==1)psxMemWrite16(r,addr,0u);
    }} else {{
        if(width==0)(void)psxMemRead8(r,addr);
        else if(width==1)(void)psxMemRead16(r,addr);
        else (void)psxMemRead32(r,addr);
    }}
}}
int main(void) {{
    psxRegisters regs={{0}};
    for(unsigned kind=0;kind<8;kind++) {{
        const test_case *tc=&test_cases[kind];
        for(unsigned phase=0;phase<4;phase++) {{
            if(vh173_arm_wait_quiet(phase)!=0 ||
               vh174_arm_wait_read(phase)!=0 ||
               vh175_arm_read_ports(phase)!=0 ||
               vh176_arm_narrow(phase)!=0 ||
               vh180_arm_nongpu(kind,phase)!=0)return 1;
            regs.pc={pc+4}u;regs.code=tc->opcode ^ 1u;
            memory_touch(&regs,tc->width,tc->writing,tc->addr);
            if(vh180_primary()!=0u)return 2;
            regs.code=tc->opcode;
            memory_touch(&regs,tc->width,tc->writing,tc->addr);
            if(tc->width2!=4294967295u)
                memory_touch(&regs,tc->width2,tc->writing2,tc->addr2);
            if(vh180_primary()!=1u ||
               vh180_secondary()!=(kind>=6?1u:0u) ||
               vh180_faults()!=0u ||
               vh176_narrow_total()!=0u ||
               vh175_gp0_read_faults()!=0u ||
               vh175_gp1_read_faults()!=0u ||
               vh173_wait_mmio_faults()!=0u)return 3;
            if(vh180_disarm_nongpu(kind,phase)!=0 ||
               vh176_disarm_narrow(phase)!=0 ||
               vh175_disarm_read_ports(phase)!=0 ||
               vh174_disarm_wait_read(phase)!=0 ||
               vh173_disarm_wait_quiet(phase)!=0)return 4;
        }}
    }}
    puts("VH180_COMPILED_REAL_OPCODE_ADDR_GATE_PASS cases=8 windows_each=4 primary_per_window=1 secondary_stores=2 stale_opcode_refused=1 original_retail=0");
    return 0;
}}
"""
        with tempfile.TemporaryDirectory(prefix="vh180-true-mips-") as d:
            src=Path(d)/"fixture.c";exe=Path(d)/"fixture"
            src.write_text(head+all_memory()+tail)
            compiled=subprocess.run([cc,"-std=c99","-pedantic","-Wall","-Wextra","-Werror",
                          str(src),"-o",str(exe)],capture_output=True,text=True,timeout=35)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH180_COMPILED_REAL_OPCODE_ADDR_GATE_PASS",run.stdout)

    def test_workflow_exactly_eight_native_opcode_positive_receipts_and_negative_absence(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v180-nongpu-opcode-provenance.yml").read_text()
        for t in (
            "apply_map02_v180_nongpu_opcode_provenance",
            "test_map02_v180_nongpu_opcode_provenance.py",
            "--vh180-nongpu-mips-",
            "VH180_NONGPU_GUEST_OPCODE_EXECUTED_PASS",
            "VH180_GUEST_OPCODE_UNOBSERVED_REFUSED",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "VH180_NATIVE_NONGPU_OPCODE_PROVENANCE_PASS",
            "V180_NEGATIVE_UNMODIFIED.EXE",
            "test \"$rc\" -eq 83",
        ):self.assertIn(t,workflow)
        self.assertIn("test_map02_v179_nongpu_memory_exclusion.py",own)

if __name__=="__main__":
    unittest.main()
