#!/usr/bin/env python3
"""Actual pinned interpreter PC witness source and C corruption-regression tests."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v138_interpreter_pc_witness import (
    EXPECTED_COUNT,source_authored_expected_sw_sites,native_sw_observer_source,
    enriched_native_oracle,
)
from tools.make_map02_v129_four_vblank_exe import build


def native_harness(sites):
    source=native_sw_observer_source(sites)
    calls="\n".join(
        f"vh138_observe_interpreted_sw(0x{pc:08x}u,"
        f"0x{instruction:08x}u,"
        f"{ {1:'0x1f8010a0',2:'0x1f8010a4',3:'0x1f8010a8'}[kind] }u,"
        f"{'0x01000401u' if linked else '0u'});"
        for pc,kind,instruction,linked in sites
    )
    return """#include <stdint.h>
typedef uint32_t u32;
#define VH_MAP02_V66_PCSX_PROBE 1
"""+source+"""
int main(void){
    vh138_seen=0u;vh138_bad=0u;vh138_enabled=0u;
    vh138_observe_interpreted_sw(0xffffffffu,0u,0x1f8010a8u,0u);
    if(vh138_seen!=0u || vh138_bad!=0u)return 31;
    vh138_enabled=1u;
"""+calls+"""
    if(vh138_seen!=12u || vh138_bad!=0u)return 32;
    vh138_observe_interpreted_sw(0xffffffffu,0u,0x1f8010a8u,0u);
    if(vh138_seen!=12u || vh138_bad!=1u)return 33;
    vh138_enabled=0u;
    vh138_observe_interpreted_sw(0xffffffffu,0u,0x1f8010a8u,0u);
    if(vh138_seen!=12u || vh138_bad!=1u)return 34;
    return 0;
}
"""


class RuntimeSWInstructionPCWitness(unittest.TestCase):
    def test_twelve_cpu_sw_register_sites_from_original_source_authored_exe(self):
        actual=source_authored_expected_sw_sites()
        self.assertEqual(len(actual),EXPECTED_COUNT)
        self.assertEqual([kind for _,kind,_,_ in actual],[3,1,2,3]*3)
        self.assertEqual(sum(flag for _,_,_,flag in actual),3)
        self.assertEqual(len(set(pc for pc,_,_,_ in actual)),12)
        exe,stops,_ops,starts,wait_pc=build()
        for pc,kind,instruction,linked in actual:
            self.assertGreaterEqual(pc,starts[1])
            self.assertLess(pc,stops[-1])
            offset=2048+pc-starts[0]
            self.assertEqual(int.from_bytes(exe[offset:offset+4],"little"),instruction)
            self.assertEqual(instruction>>26,0x2b)

    def test_compiled_original_c_observer_positive_and_corruption_refusals(self):
        original=source_authored_expected_sw_sites()
        code=native_harness(original)
        cc=os.environ.get("CC","gcc")
        with tempfile.TemporaryDirectory(prefix="vh138-native-c-") as temp:
            root=Path(temp)
            file=root/"private-runtime-sw-check.c"
            exe=root/"private-runtime-sw-check"
            file.write_text(code)
            compile=subprocess.run([cc,"-std=c11","-O1","-Wall","-Wextra",
                "-Wpedantic","-Werror","-fsanitize=undefined,bounds",
                str(file),"-o",str(exe)],text=True,capture_output=True,
                timeout=30,check=False)
            self.assertEqual(compile.returncode,0,
                             compile.stderr[-1200:])
            good=subprocess.run([str(exe)],text=True,capture_output=True,
                                timeout=5,check=False)
            self.assertEqual(good.returncode,0,good.stderr[-1200:])
            # An independent run of the identical production C observer
            # must reject mutation of runtime origin PC, instruction
            # word, register target or linked-list CHCR source value.
            needle="    vh138_enabled=1u;\n"
            self.assertEqual(code.count(needle),1)
            base_call=(
                f"vh138_observe_interpreted_sw("
                f"0x{original[0][0]:08x}u,"
                f"0x{original[0][2]:08x}u,"
                "0x1f8010a8u,0u);"
            )
            self.assertIn(base_call,code)
            variants=(
                base_call.replace(f"0x{original[0][0]:08x}u",
                                  f"0x{original[0][0]+4:08x}u"),
                base_call.replace(f"0x{original[0][2]:08x}u",
                                  f"0x{original[0][2]^1:08x}u"),
                base_call.replace("0x1f8010a8u","0x1f8010a4u"),
            )
            for index,replacement in enumerate(variants):
                with self.subTest(index=index):
                    changed=code.replace(base_call,replacement,1)
                    self.assertNotEqual(changed,code)
                    file.write_text(changed)
                    compile=subprocess.run([cc,"-std=c11","-O1","-Wall",
                        "-Wextra","-Wpedantic","-Werror",
                        "-fsanitize=undefined,bounds",str(file),"-o",str(exe)],
                        text=True,capture_output=True,timeout=30,check=False)
                    self.assertEqual(compile.returncode,0,compile.stderr[-900:])
                    refused=subprocess.run([str(exe)],text=True,
                        capture_output=True,timeout=5,check=False)
                    self.assertEqual(refused.returncode,32)

    def test_exact_pinned_cpu_interpreter_hook_and_original_vblank_proof(self):
        from tools.apply_map02_v129_pcsx_rearmed import oracle_source
        exe,stops,ops,starts,wait_pc=build()
        before=oracle_source(stops,wait_pc)
        after=enriched_native_oracle(stops,wait_pc)
        self.assertNotEqual(before,after)
        for required in (
            "vh138_enabled=1u",
            "vh138_enabled=0u",
            "vh138_seen!=12u",
            "vh138_bad!=0u",
            "VH138_CPU_SW_PC_PASS stores=12",
            "VH129_REAL_VBLANK_PROFILES_PASS",
            "VH129_EDGE_TOTAL_REFUSED",
        ):
            self.assertIn(required,after)
        self.assertEqual(after.count("VH138_CPU_SW_PC_PASS stores=12"),1)
        self.assertEqual(after.count("VH129_REAL_VBLANK_PROFILES_PASS"),1)
        source=(ROOT/"tools/apply_map02_v138_interpreter_pc_witness.py").read_text()
        for required in (
            "OP(psxSW) { psxMemWrite32(regs_, _oB_, _rRt_); }",
            "regs_->pc-4u,regs_->code,_oB_,_rRt_",
            "OP(psxSWe)",
            "psxMemWrite32(regs_, _oB_, _rRt_)",
            "apply_v129(root)",
            "libpcsxcore/psxinterpreter.c",
        ):
            self.assertIn(required,source)
        self.assertNotIn("SysPrintf(",native_sw_observer_source(
            source_authored_expected_sw_sites()))

    def test_full_ci_preserves_real_emulator_and_private_gpu_evidence(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v138-native-interpreter-sw-pc.yml").read_text()
        self.assertIn("apply_map02_v138_interpreter_pc_witness upstream-pcsx",
                      workflow)
        self.assertIn("test_map02_v138_native_interpreter_sw_pc.py",workflow)
        self.assertIn("test_map02_v138_native_interpreter_sw_pc.py",standalone)
        self.assertIn("VH138_CPU_SW_PC_PASS stores=12",workflow)
        self.assertIn("for mode in 04 13 22 31 40; do",workflow)
        self.assertIn("sha256sum -c proof/private/v131-same-exe.sha256",workflow)
        self.assertIn("VH129_REAL_VBLANK_PROFILES_PASS mode=",workflow)
        self.assertIn("check_map02_v130_native_bounds",workflow)
        self.assertIn("original_retail_MAP02_verified=False",
                      (ROOT/"tools/apply_map02_v138_interpreter_pc_witness.py").read_text())


if __name__=="__main__":
    unittest.main()
