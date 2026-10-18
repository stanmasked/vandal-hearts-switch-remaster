#!/usr/bin/env python3
"""v159 native GPU dispatch tests: self-authored PS1 MIPS fifth SW only."""
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
from tools.apply_map02_v158_native_gp0_fifth import patch_frontend as patch_v158
from tools.apply_map02_v159_native_gpu_sink import (
    GPU_DISPATCH,patch_hardware,patch_frontend,sink_observer_c
)


def sample_hardware():
    # v68 is ALWAYS installed before v159 by the production patch stack.
    return """void psxHwWrite32(psxRegisters *regs, u32 add, u32 value) {
    switch(add&0xffffu) {
\tcase 0x1810:
#ifdef VH_MAP02_V66_PCSX_PROBE
\t\t(void)vh68_pcsx_gp0_mmio_observe(value);
#endif
\t\tGPU_writeData(value); return;
    case 0x1814: return;
    default: return;
    }
}
"""


def sample_frontend():
    original=(
        "\tint vh157_corrupt_t1_fourth = 0;\n"
        '\t\telse if (!strcmp(argv[i], "--vh157-corrupt-t1-fourth"))\n'
        "    if(vh157_corrupt_t1_fourth &&\n"
        "                if(vh157_corrupt_t1_fourth)\n"
        "                    vh157_arm_t1_fourth();\n"
        "if(vh150_arm(0x80010000u,0x80012000u,\n"
        "                         vh155_four_instructions ? 4u : 3u)!=0){\n"
        "                if(vh156_verify_register_effects){\n"
        "                    if(vh157_corrupt_t1_fourth){"
    )
    return patch_v158(original)


class NativeGpuDispatch159(unittest.TestCase):
    def test_pinned_gpu_dispatch_exact_source_anchor(self):
        self.assertIn("vh68_pcsx_gp0_mmio_observe(value);",GPU_DISPATCH)
        self.assertIn("GPU_writeData(value); return;",GPU_DISPATCH)
        self.assertIn("\tcase 0x1810:",GPU_DISPATCH)
        hw=patch_hardware(sample_hardware())
        self.assertIn("if(vh159_sink_active) vh159_capture_sink(regs,add,value);",hw)
        self.assertIn("GPU_writeData(value); return;",hw)
        self.assertLess(hw.index("vh68_pcsx_gp0_mmio_observe(value);"),
                        hw.index("vh159_capture_sink(regs,add,value);"))
        self.assertLess(hw.index("vh159_capture_sink(regs,add,value);"),
                        hw.index("GPU_writeData(value); return;"))
        self.assertIn("#ifdef VH_MAP02_V66_PCSX_PROBE",hw)
        with self.assertRaises(ValueError):
            patch_hardware(hw)
        # A stock, unpatched upstream source must not bypass v68's bridge.
        with self.assertRaises(ValueError):
            patch_hardware(sample_hardware().replace(GPU_DISPATCH,
                "\\tcase 0x1810: GPU_writeData(value); return;"))
        with self.assertRaises(ValueError):
            patch_hardware(sample_hardware().replace(GPU_DISPATCH,
                GPU_DISPATCH.replace("GPU_writeData(value);",
                                     "GPU_writeData(value+1u);")))

    def test_frontend_requires_sink_and_preserves_v158_markers(self):
        front=patch_frontend(sample_frontend())
        for marker in (
            "vh159_arm_gpu_sink();","vh159_disarm_gpu_sink();",
            "sink!=1u || sink_bad!=0u","sink!=0u || sink_bad!=0u",
            "VH159_NATIVE_GPU_SINK_PASS","VH159_NATIVE_FIFTH_SINK_REFUSED",
            "VH158_NATIVE_GP0_FIFTH_PASS",
            "VH158_NATIVE_FIFTH_OPCODE_REFUSED",
        ):
            self.assertIn(marker,front)
        self.assertLess(front.index("vh158_arm_gp0();"),
                        front.index("vh159_arm_gpu_sink();"))
        with self.assertRaises(ValueError):
            patch_frontend(front)

    def test_compiled_hardware_dispatch_and_fail_closed_boundaries(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("C compiler is unavailable")
        body=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct { u32 pc,code; } psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static unsigned gpu_calls;
static u32 last_gpu_word;
static unsigned bridge_calls;
static unsigned vh68_pcsx_gp0_mmio_observe(u32 value) {
    (void)value;
    bridge_calls++;
    return 0u;
}
static void GPU_writeData(u32 value) {
    gpu_calls++; last_gpu_word=value;
}
""" + patch_hardware(sample_hardware()) + r"""
int main(void){
    psxRegisters r={0x80010014u,0xad090000u};
    /* Disabled diagnostic never changes original GPU submission. */
    psxHwWrite32(&r,0x1f801810u,0xe3000000u);
    if(gpu_calls!=1u || bridge_calls!=1u || vh159_sink_writes() ||
       vh159_sink_faults()) return 1;
    gpu_calls=0u;
    vh159_arm_gpu_sink();
    psxHwWrite32(&r,0x1f801810u,0xe3000000u);
    if(gpu_calls!=1u || bridge_calls!=2u || last_gpu_word!=0xe3000000u ||
       vh159_sink_writes()!=1u || vh159_sink_faults()) return 2;
    /* Duplicate valid write must refuse exactly-one proof. */
    psxHwWrite32(&r,0x1f801810u,0xe3000000u);
    if(gpu_calls!=2u || vh159_sink_writes()!=2u) return 3;
    vh159_disarm_gpu_sink();
    vh159_arm_gpu_sink();
    r.pc=0x80010010u;
    psxHwWrite32(&r,0x1f801810u,0xe3000000u);
    if(vh159_sink_writes()!=0u || vh159_sink_faults()!=1u) return 4;
    vh159_arm_gpu_sink();
    r.pc=0x80010014u;
    r.code=0xac090000u;
    psxHwWrite32(&r,0x1f801810u,0xe3000000u);
    if(vh159_sink_writes()!=0u || vh159_sink_faults()!=1u) return 5;
    vh159_arm_gpu_sink();
    r.code=0xad090000u;
    psxHwWrite32(&r,0x1f801810u,0xe3000001u);
    if(vh159_sink_writes()!=0u || vh159_sink_faults()!=1u) return 6;
    vh159_arm_gpu_sink();
    psxHwWrite32(&r,0x1f801814u,0xe3000000u);
    if(vh159_sink_writes()!=0u || vh159_sink_faults()!=0u) return 7;
    vh159_disarm_gpu_sink();
    puts("VH159_COMPILED_GPU_DISPATCH_PASS gp0_exact=1 duplicate_refused=1 bad_pc=1 bad_opcode=1 bad_data=1 gp1_ignored=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh159-gpu-dispatch-") as td:
            p=Path(td)
            (p/"fixture.c").write_text(body)
            exe=p/"fixture"
            built=subprocess.run([cc,"-std=c99","-Wall","-Wextra","-Werror",
                "-pedantic",str(p/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(built.returncode,0,built.stderr)
            test=subprocess.run([str(exe)],capture_output=True,
                text=True,timeout=10)
            self.assertEqual(test.returncode,0,test.stderr)
            self.assertIn("VH159_COMPILED_GPU_DISPATCH_PASS",test.stdout)

    def test_native_matrix_wired_positive_and_fifth_mutation(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v159-native-gpu-sink.yml").read_text()
        for marker in (
            "apply_map02_v159_native_gpu_sink",
            "test_map02_v159_native_gpu_sink.py",
            "VH159_NATIVE_GPU_SINK_PASS",
            "VH159_NATIVE_FIFTH_SINK_REFUSED",
            "vh159_capture_sink(regs,add,value)",
        ):
            self.assertIn(marker,workflow)
        self.assertIn("test_map02_v158_native_gp0_fifth.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
