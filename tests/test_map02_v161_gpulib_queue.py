#!/usr/bin/env python3
"""v161: pinned gpulib command-buffer enqueue witness; synthetic code only."""
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
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v159_native_gpu_sink import sample_frontend
from tools.apply_map02_v159_native_gpu_sink import patch_frontend as patch_v159
from tools.apply_map02_v160_plugin_callback import patch_frontend as patch_v160
from tools.apply_map02_v161_gpulib_queue import (
    QUEUE_APPEND,GPU_ENTRY,queue_probe_c,patch_gpu,patch_frontend
)


def gpu_fixture():
    return """void GPUwriteData(uint32_t data)
{
  gpu.cmd_buffer[gpu.cmd_len++] = HTOLE32(data);
  if (gpu.cmd_len >= CMD_BUFFER_LEN) gpu.cmd_len = 0;
}
"""


class NativeGpulibQueue161(unittest.TestCase):
    def test_exact_pinned_append_and_unique_patch(self):
        self.assertIn("gpu.cmd_buffer[gpu.cmd_len++] = HTOLE32(data)",QUEUE_APPEND)
        patched=patch_gpu(gpu_fixture())
        self.assertIn("vh161_observe_gpu_queue(data);",patched)
        self.assertLess(patched.index(QUEUE_APPEND),patched.index(
            "vh161_observe_gpu_queue(data);"))
        self.assertIn("gpu.cmd_buffer[gpu.cmd_len++]",patched)
        with self.assertRaises(ValueError):
            patch_gpu(patched)
        with self.assertRaises(ValueError):
            patch_gpu(gpu_fixture().replace(QUEUE_APPEND,
                "  gpu.cmd_buffer[gpu.cmd_len++] = data;"))
        with self.assertRaises(ValueError):
            patch_gpu(gpu_fixture()+"\n"+gpu_fixture())

    def test_frontend_gates_success_and_mutation_on_real_enqueue(self):
        prior=patch_v160(patch_v159(sample_frontend()))
        patched=patch_frontend(prior)
        for marker in (
            "if(vh161_arm_gpu_queue()!=0){",
            "VH161_QUEUE_ARM_REFUSED",
            "vh161_gpu_queue_stores();",
            "vh161_gpu_queue_faults();",
            "vh161_disarm_gpu_queue();",
            "queue!=1u || queue_bad!=0u || queue_disarmed!=0",
            "queue!=0u || queue_bad!=0u || queue_disarmed!=0",
            "VH161_NATIVE_GPULIB_QUEUE_PASS",
            "VH161_NATIVE_FIFTH_QUEUE_REFUSED",
            "VH160_NATIVE_PLUGIN_CALLBACK_PASS",
            "VH159_NATIVE_GPU_SINK_PASS",
        ):
            self.assertIn(marker,patched)
        self.assertLess(patched.index("if(vh160_arm_plugin_callback()!=0){"),
                        patched.index("if(vh161_arm_gpu_queue()!=0){"))
        with self.assertRaises(ValueError):
            patch_frontend(patched)

    def test_compiled_real_append_refusal_and_fault_boundaries(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("C compiler unavailable")
        code=r"""
#include <stdint.h>
#include <stdio.h>
#define VH_MAP02_V66_PCSX_PROBE 1
#define CMD_BUFFER_LEN 16
#define HTOLE32(x) (x)
struct {
    uint32_t cmd_buffer[CMD_BUFFER_LEN];
    int cmd_len;
} gpu;
""" + patch_gpu(gpu_fixture()) + r"""
int main(void) {
    /* Disabled observer must not change the genuine append. */
    GPUwriteData(0xe3000000u);
    if(gpu.cmd_len!=1 || gpu.cmd_buffer[0]!=0xe3000000u ||
       vh161_gpu_queue_stores() || vh161_gpu_queue_faults()) return 1;

    if(vh161_arm_gpu_queue()!=0 || vh161_arm_gpu_queue()==0) return 2;
    GPUwriteData(0xe3000000u);
    if(vh161_gpu_queue_stores()!=1u || vh161_gpu_queue_faults() ||
       gpu.cmd_buffer[1]!=0xe3000000u) return 3;
    if(vh161_disarm_gpu_queue()!=0 || vh161_disarm_gpu_queue()==0)
        return 4;

    /* Multiple writes may not be mistaken for exactly one. */
    if(vh161_arm_gpu_queue()!=0) return 5;
    GPUwriteData(0xe3000000u);
    GPUwriteData(0xe3000000u);
    GPUwriteData(0xe3000000u);
    if(vh161_gpu_queue_stores()!=2u ||
       vh161_gpu_queue_faults()!=1u) return 6;
    if(vh161_disarm_gpu_queue()!=0) return 7;

    /* The original gpulib buffer still receives the wrong word, but
     * diagnostic success is refused. */
    if(vh161_arm_gpu_queue()!=0) return 8;
    GPUwriteData(0xe3000001u);
    if(vh161_gpu_queue_stores()!=0u ||
       vh161_gpu_queue_faults()!=1u ||
       gpu.cmd_buffer[gpu.cmd_len-1]!=0xe3000001u) return 9;
    if(vh161_disarm_gpu_queue()!=0) return 10;

    /* Mutated fifth MIPS instruction: no underlying GPU callback. */
    if(vh161_arm_gpu_queue()!=0) return 11;
    if(vh161_gpu_queue_stores() || vh161_gpu_queue_faults())
        return 12;
    if(vh161_disarm_gpu_queue()!=0) return 13;

    /* Refuse unsafe arming before a full array; never write here. */
    gpu.cmd_len=CMD_BUFFER_LEN;
    if(vh161_arm_gpu_queue()==0) return 14;
    gpu.cmd_len=0;
    if(vh161_arm_gpu_queue()!=0) return 15;
    /* A mutated queue storage index cannot masquerade as valid. */
    gpu.cmd_len=2;
    GPUwriteData(0xe3000000u);
    if(vh161_gpu_queue_stores() ||
       vh161_gpu_queue_faults()!=1u) return 16;
    if(vh161_disarm_gpu_queue()!=0) return 17;
    puts("VH161_COMPILED_GPU_QUEUE_PASS appended=1 duplicate_refused=1 wrong_word_refused=1 mutation_zero=1 queue_index_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh161-gpulib-") as td:
            p=Path(td)
            (p/"test.c").write_text(code)
            exe=p/"test"
            build=subprocess.run([cc,"-std=c99","-Wall","-Wextra",
                "-Werror","-pedantic",str(p/"test.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,
                timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH161_COMPILED_GPU_QUEUE_PASS",run.stdout)

    def test_workflows_use_native_gpu_c_and_real_positive_negative(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        stand=(ROOT/".github/workflows/map02-v161-native-gpulib-queue.yml").read_text()
        for marker in (
            "apply_map02_v161_gpulib_queue",
            "test_map02_v161_gpulib_queue.py",
            "VH161_NATIVE_GPULIB_QUEUE_PASS",
            "VH161_NATIVE_FIFTH_QUEUE_REFUSED",
            "vh161_observe_gpu_queue(data)",
            "plugins/gpulib/gpu.c",
        ):
            self.assertIn(marker,native)
        self.assertIn("test_map02_v160_plugin_callback.py",stand)
        self.assertIn("original_retail_executed=0",stand)


if __name__=="__main__":
    unittest.main()
