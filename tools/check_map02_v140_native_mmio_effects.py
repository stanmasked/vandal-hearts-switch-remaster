#!/usr/bin/env python3
"""C11 sanitized exact MMIO address/value comparison for synthesized MIPS."""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from .apply_map02_v138_interpreter_pc import native_probe_declarations
from .apply_map02_v139_mips_word_stages import codeword_expectations,patch_v138_probe_c
from .apply_map02_v140_mmio_effects import (
    expected_actual_mmio,patch_native_value_observer,
)


def sample_source():
    events,words,prefixes=codeword_expectations()
    effects=expected_actual_mmio()
    native=patch_native_value_observer(
        patch_v138_probe_c(native_probe_declarations(events)))
    code=(
        "#include <stdint.h>\n#include <stdio.h>\n"
        "typedef uint32_t u32;\n"
        "typedef struct psxRegisters {u32 pc;u32 code;} psxRegisters;\n"
        +native+r"""
/* mode 1 corrupt actual GP0 data with unchanged word & PC
 * mode 2 supply an aliased effective address accepted by v138's
 *         physical address mask but forbidden by v140 exact equality
 * mode 3 corrupt the EXPECTATION only, not emulated MIPS
 * mode 4 swap two GP0 data words preserving count and class. */
static unsigned trial(unsigned mode) {
    unsigned i,stage=0u;
    psxRegisters regs={0};
    vh138_pc_enable();
    vh139_enable(0u);
    vh140_mmio_enable(mode==3u);
    for(i=0u;i<VH138_EXPECTED_COUNT;i++){
        u32 addr=vh140_expected_addr[i];
        u32 value=vh140_expected_value[i];
        regs.pc=vh138_expected_pc[i]+4u;
        regs.code=vh139_expected_word[i];
        if(mode==1u && i==2u) value^=1u;
        if(mode==2u && i==2u) addr^=0x80000000u;
        if(mode==4u && i==0u) value=vh140_expected_value[1u];
        if(mode==4u && i==1u) value=vh140_expected_value[0u];
        vh138_pc_observe(&regs,addr,value);
        if(stage<4u && vh138_seen==vh139_stage_prefix[stage])
            vh139_check_stage(stage++);
    }
    /* A failed address alias / data value must be detected by v140 even
     * when the previous PC and instruction-word checks still succeed. */
    if(vh138_pc_check()!=0u || vh139_verify()!=0u)
        return 77u;
    return vh140_mmio_verify();
}
int main(void) {
    if(trial(0u)!=0u) return 1;
    if(trial(1u)==0u) return 2;
    if(trial(2u)==0u) return 3;
    if(trial(3u)==0u) return 4;
    if(trial(4u)==0u) return 5;
    if(trial(0u)!=0u) return 6;
    puts("VH140_COMPILED_MMIO_EFFECT_PASS matched=19 gp0=6 "
         "dma2_starts=3 data_tamper=refused alias=refused "
         "bad_expectation=refused order_tamper=refused");
    return 0;
}
""")
    return code,events,effects,prefixes


def run(cc):
    code,events,effects,prefixes=sample_source()
    if len(events)!=19 or len(effects)!=19 or prefixes!=(7,11,15,19):
        raise ValueError("VH140_MMIO_EFFECT_TEST_FIXTURE_REFUSED")
    with tempfile.TemporaryDirectory(prefix="vh140-compiled-") as tmp:
        root=Path(tmp)
        c=root/"effect.c"
        exe=root/"effect"
        c.write_text(code)
        p=subprocess.run([cc,"-std=c11","-O1","-Wall","-Wextra",
                          "-Wpedantic","-Werror",
                          "-DVH_MAP02_V66_PCSX_PROBE",
                          "-fsanitize=bounds,undefined",
                          str(c),"-o",str(exe)],
                         text=True,capture_output=True,check=False,timeout=30)
        if p.returncode:
            raise ValueError("VH140_MMIO_EFFECT_C_COMPILE_REFUSED")
        p=subprocess.run([str(exe)],text=True,capture_output=True,
                         check=False,timeout=15)
        expected=("VH140_COMPILED_MMIO_EFFECT_PASS matched=19 gp0=6 "
                  "dma2_starts=3 data_tamper=refused alias=refused "
                  "bad_expectation=refused order_tamper=refused")
        if p.returncode or p.stdout.strip()!=expected:
            raise ValueError("VH140_MMIO_EFFECT_C_RUNTIME_REFUSED")
        print(expected)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cc",required=True)
    run(parser.parse_args().cc)
