#!/usr/bin/env python3
"""Standalone compiled C regression of pinned interpreter PC witness logic.

This is a *unit* model only: actual PCSX psxMemWrite32 runs separately in
the pinned native GCC/Clang workflows, not claimed from this stub.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from .apply_map02_v138_interpreter_pc import (
    expected_pc_events,native_probe_declarations,CLASS_CODES,REGISTER_MAP,
)

MAX_TEST_EVENTS=128
REGISTER_BY_CLASS={CLASS_CODES[kind]:addr for addr,kind in REGISTER_MAP.items()}


def sample_program():
    events=expected_pc_events()
    expected=len(events)
    src=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct psxRegisters {u32 pc;u32 code;} psxRegisters;
""" + native_probe_declarations(events) + r"""
static int vh138_feed_all(unsigned alter_index) {
    unsigned i;
    const unsigned addresses[] = { VH138_REGISTERS };
    psxRegisters regs={0};
    if(sizeof(addresses)/sizeof(addresses[0]) !=
       sizeof(vh138_expected_kind)/sizeof(vh138_expected_kind[0]))
        return 5;
    vh138_pc_enable();
    for(i=0;i<VH138_EXPECTED_COUNT;i++){
        regs.pc=vh138_expected_pc[i]+4u;
        regs.code=0xac000000u; /* Original 0x2b MIPS SW opcode. */
        if(alter_index==i)
            regs.pc+=4u;
        vh138_pc_observe(&regs,addresses[i],0u);
    }
    return (int)vh138_pc_check();
}
int main(void) {
    psxRegisters regs={0};
    if(vh138_feed_all(9999u)!=0)
        return 11;
    if(vh138_pc_count()!=VH138_EXPECTED_COUNT)
        return 12;
    if(vh138_feed_all(2u)==0)
        return 13;
    if(vh138_feed_all(9999u)!=0)
        return 14;
    /* Same PC but a different register class cannot be accepted. */
    vh138_pc_enable();
    regs.pc=vh138_expected_pc[0]+4u;
    regs.code=0xac000000u;
    vh138_pc_observe(&regs,0x1f8010a8u,0u);
    if(vh138_pc_check()==0)
        return 15;
    /* Every captured event must have a true native SW opcode. */
    vh138_pc_enable();
    regs.pc=vh138_expected_pc[0]+4u;
    regs.code=0x20000000u;
    vh138_pc_observe(&regs,addresses[0],0u);
    if(vh138_pc_check()==0)
        return 16;
    /* Any forced mutation must cause refusal, never just relabel PASS. */
    if(vh138_feed_all(9999u)!=0)
        return 17;
    vh138_pc_inject_error();
    if(vh138_pc_check()==0)
        return 18;
    printf("VH138_COMPILED_PC_OBSERVER_PASS matched=VH138_COUNT "
           "positive=1 wrong_pc_refused=1 wrong_class_refused=1 "
           "non_sw_refused=1 forced_corruption_refused=1\n");
    return 0;
}
"""
    addrlist=", ".join(
        f"0x{REGISTER_BY_CLASS[class_code]:08x}u"
        for _,class_code,*_ in events)
    return (src.replace("VH138_REGISTERS",addrlist)
               .replace("VH138_COUNT",str(expected))),events


def check(cc):
    source,events=sample_program()
    if not 10<len(events)<MAX_TEST_EVENTS:
        raise ValueError("invalid synthetic interpreter witness expectation")
    with tempfile.TemporaryDirectory(prefix="vh138-source-") as temporary:
        base=Path(temporary)
        file=base/"observer.c"
        exe=base/"observer"
        file.write_text(source)
        result=subprocess.run(
            [cc,"-std=c11","-O1","-Wall","-Wextra","-Wpedantic",
             "-Werror","-DVH_MAP02_V66_PCSX_PROBE",
             "-fsanitize=undefined,bounds",str(file),"-o",str(exe)],
            capture_output=True,text=True,check=False,timeout=30)
        if result.returncode!=0:
            raise ValueError("VH138_NATIVE_C_OBSERVER_COMPILE_REFUSED")
        result=subprocess.run([str(exe)],capture_output=True,text=True,
                              check=False,timeout=15)
        if (result.returncode!=0 or
            f"VH138_COMPILED_PC_OBSERVER_PASS matched={len(events)} " not in
                result.stdout):
            raise ValueError("VH138_NATIVE_C_OBSERVER_EXECUTION_REFUSED")
        print(result.stdout.strip())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cc",required=True)
    args=parser.parse_args()
    check(args.cc)


if __name__=="__main__":
    main()
