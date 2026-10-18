#!/usr/bin/env python3
"""Compiled original-synthetic MIPS exact-word + per-DMA-stage C witness."""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from .apply_map02_v138_interpreter_pc import native_probe_declarations
from .apply_map02_v139_mips_word_stages import (
    codeword_expectations,patch_v138_probe_c,
)
from .check_map02_v138_native_pc_observer import REGISTER_BY_CLASS


def sample_source():
    events,words,prefixes=codeword_expectations()
    native=patch_v138_probe_c(native_probe_declarations(events))
    registers=", ".join(
        "0x%08xu"%REGISTER_BY_CLASS[cls] for _,cls,*_ in events)
    source=(
        "#include <stdint.h>\n#include <stdio.h>\n"
        "typedef uint32_t u32;\n"
        "typedef struct psxRegisters {u32 pc;u32 code;} psxRegisters;\n"
        +native+
        "\nstatic const unsigned vh139_test_registers[]={"+registers+"};\n"
        +r"""
/* bit0: modify executed codeword but retain SW opcode and correct PC;
 * bit1: make native observer's OWN expected word wrong;
 * bit2: skip exactly one required original CPU phase checkpoint;
 * bit3: give one checkpoint an incorrect stage index. */
static int run_case(unsigned flags) {
    unsigned i,stage=0u;
    psxRegisters regs={0};
    vh138_pc_enable();
    vh139_enable((flags&2u)!=0u);
    for(i=0;i<VH138_EXPECTED_COUNT;i++) {
        regs.pc=vh138_expected_pc[i]+4u;
        regs.code=vh139_expected_word[i];
        if((flags&1u) && i==2u)
            regs.code^=0x00010000u; /* opcode bits unchanged */
        vh138_pc_observe(&regs,vh139_test_registers[i],0u);
        if(stage<4u && vh138_seen==vh139_stage_prefix[stage]) {
            if((flags&4u) && stage==1u) {
                stage++; /* deliberately miss this CPU boundary */
            } else {
                vh139_check_stage(stage+((flags&8u)&&stage==2u?1u:0u));
                stage++;
            }
        }
    }
    if(vh138_pc_check()!=0u)
        return 42;
    return (int)vh139_verify();
}
int main(void) {
    if(run_case(0u)!=0)
        return 1;
    if(run_case(1u)==0)
        return 2;
    if(run_case(2u)==0)
        return 3;
    if(run_case(4u)==0)
        return 4;
    if(run_case(8u)==0)
        return 5;
    if(run_case(0u)!=0)
        return 6;
    puts("VH139_COMPILED_WORD_STAGE_PASS matched=19 stages=4 "
         "wrong_word=refused bad_expectation=refused "
         "missing_stage=refused wrong_stage=refused");
    return 0;
}
""")
    return source,events,words,prefixes


def run(cc):
    source,events,words,prefixes=sample_source()
    if len(events)!=19 or len(words)!=19 or len(prefixes)!=4:
        raise ValueError("VH139_INVALID_ORIGINAL_SYNTHETIC_FIXTURE")
    with tempfile.TemporaryDirectory(prefix="vh139-compiled-") as folder:
        root=Path(folder)
        file=root/"native.c"
        exe=root/"native"
        file.write_text(source)
        result=subprocess.run(
            [cc,"-std=c11","-O1","-Wall","-Wextra","-Wpedantic",
             "-Werror","-DVH_MAP02_V66_PCSX_PROBE",
             "-fsanitize=bounds,undefined",str(file),"-o",str(exe)],
            capture_output=True,text=True,timeout=30,check=False)
        if result.returncode!=0:
            raise ValueError("VH139_COMPILED_WORD_STAGE_COMPILE_REFUSED")
        result=subprocess.run([str(exe)],capture_output=True,text=True,
                              timeout=15,check=False)
        if (result.returncode!=0 or result.stdout.strip() !=
            "VH139_COMPILED_WORD_STAGE_PASS matched=19 stages=4 "
            "wrong_word=refused bad_expectation=refused "
            "missing_stage=refused wrong_stage=refused"):
            raise ValueError("VH139_COMPILED_WORD_STAGE_EXECUTION_REFUSED")
        print(result.stdout.strip())


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cc",required=True)
    run(p.parse_args().cc)
