#!/usr/bin/env python3
"""v160: synthetic-only native plugin callback entry/return regression tests."""
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
from test_map02_v159_native_gpu_sink import sample_frontend as v158_frontend_fixture
from tools.apply_map02_v159_native_gpu_sink import patch_frontend as v159_frontend
from tools.apply_map02_v160_plugin_callback import (
    callback_probe_c,patch_plugin,patch_frontend,PLUGIN_ANCHOR,
)


class NativePluginCallback160(unittest.TestCase):
    def test_retain_v69_wrapper_and_restore_on_disarm(self):
        original=(ROOT/"tools/map02_v69_pcsx_plugin_wrap.c").read_text()
        patched=patch_plugin(original)
        self.assertEqual(original.count(PLUGIN_ANCHOR),1)
        self.assertIn("vh160_saved_writeData(value);",patched)
        self.assertIn("GPU_writeData=vh160_callback;",patched)
        self.assertIn("GPU_writeData=vh160_saved_writeData;",patched)
        self.assertIn("static void CALLBACK wrapped_writeData(uint32_t word)",patched)
        self.assertIn("vh69_gpu_wrap_loaded_plugin(void)",patched)
        self.assertLess(patched.index("vh160_arm_plugin_callback"),
                        patched.index(PLUGIN_ANCHOR))
        with self.assertRaises(ValueError):
            patch_plugin(patched)
        with self.assertRaises(ValueError):
            patch_plugin(original.replace(
                "static void CALLBACK wrapped_writeData(uint32_t word)",
                "static void CALLBACK broken_writeData(uint32_t word)"))

    def test_frontend_require_callback_before_success(self):
        source=v159_frontend(v158_frontend_fixture())
        patched=patch_frontend(source)
        for marker in (
            "VH160_CALLBACK_ARM_REFUSED",
            "VH160_NATIVE_PLUGIN_CALLBACK_PASS",
            "VH160_NATIVE_FIFTH_CALLBACK_REFUSED",
            "VH159_NATIVE_GPU_SINK_PASS",
            "VH158_NATIVE_GP0_FIFTH_PASS",
            "VH158_NATIVE_FIFTH_OPCODE_REFUSED",
            "callback_enters!=1u || callback_returns!=1u",
            "callback_enters!=0u || callback_returns!=0u",
            "callback_bad!=0u || callback_restored!=0",
            "vh160_disarm_plugin_callback();",
        ):
            self.assertIn(marker,patched)
        self.assertLess(patched.index("vh159_arm_gpu_sink();"),
                        patched.index("vh160_arm_plugin_callback();"))
        with self.assertRaises(ValueError):
            patch_frontend(patched)

    def test_compiled_real_callback_pointer_forwarding_and_refusal(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("C compiler unavailable")
        program=r"""
#include <stdint.h>
#include <stdio.h>
#define CALLBACK
typedef void (CALLBACK *GPUwriteData)(uint32_t);
static unsigned real_calls;
static uint32_t last_word;
static void CALLBACK real_gpu(uint32_t value) {
    real_calls++;
    last_word=value;
}
static void CALLBACK foreign_gpu(uint32_t value) {
    (void)value;
}
/* Simulates the existing v69 callback wrapper installed before v160. */
static unsigned existing_wrapper_calls;
static void CALLBACK existing_wrapper(uint32_t value) {
    existing_wrapper_calls++;
    real_gpu(value);
}
static GPUwriteData GPU_writeData=real_gpu;
""" + callback_probe_c() + r"""
int main(void) {
    if(vh160_callback_enters() || vh160_callback_returns() ||
       vh160_callback_faults()) return 1;
    if(vh160_arm_plugin_callback()!=0) return 2;
    if(vh160_arm_plugin_callback()==0) return 3;
    if(GPU_writeData==real_gpu) return 4;
    GPU_writeData(0xe3000000u);
    if(real_calls!=1u || last_word!=0xe3000000u ||
       vh160_callback_enters()!=1u || vh160_callback_returns()!=1u ||
       vh160_callback_faults()!=0u) return 5;
    if(vh160_disarm_plugin_callback()!=0 || GPU_writeData!=real_gpu)
        return 6;
    if(vh160_disarm_plugin_callback()==0) return 7;

    /* Second matching packet saturates at 2: cannot falsely equal 1. */
    if(vh160_arm_plugin_callback()!=0) return 8;
    GPU_writeData(0xe3000000u);
    GPU_writeData(0xe3000000u);
    GPU_writeData(0xe3000000u);
    if(vh160_callback_enters()!=2u ||
       vh160_callback_returns()!=2u || real_calls!=4u) return 9;
    if(vh160_disarm_plugin_callback()!=0) return 10;

    /* Unmodified callback receives the wrong word, evidence refuses. */
    if(vh160_arm_plugin_callback()!=0) return 11;
    GPU_writeData(0xe3000001u);
    if(last_word!=0xe3000001u || vh160_callback_enters()!=0u ||
       vh160_callback_returns()!=0u || vh160_callback_faults()!=1u)
        return 12;
    if(vh160_disarm_plugin_callback()!=0) return 13;

    /* Mutated fifth MIPS opcode must never invoke this callback. */
    if(vh160_arm_plugin_callback()!=0) return 14;
    if(vh160_callback_enters()!=0u || vh160_callback_returns()!=0u ||
       vh160_callback_faults()!=0u) return 15;
    if(vh160_disarm_plugin_callback()!=0 ||
       GPU_writeData!=real_gpu) return 16;

    /* Changed pointer is never overwritten, and is fail-closed. */
    if(vh160_arm_plugin_callback()!=0) return 17;
    GPU_writeData=foreign_gpu;
    if(vh160_disarm_plugin_callback()==0 ||
       GPU_writeData!=foreign_gpu ||
       vh160_callback_faults()!=1u) return 18;
    GPU_writeData=real_gpu;

    /* If the old v69 wrapper was already active, v160 must wrap it,
     * invoke it once and restore that EXACT pointer on disarm. */
    GPU_writeData=existing_wrapper;
    if(vh160_arm_plugin_callback()!=0) return 19;
    GPU_writeData(0xe3000000u);
    if(existing_wrapper_calls!=1u || last_word!=0xe3000000u ||
       vh160_callback_enters()!=1u || vh160_callback_returns()!=1u ||
       vh160_callback_faults()!=0u) return 20;
    if(vh160_disarm_plugin_callback()!=0 ||
       GPU_writeData!=existing_wrapper) return 21;

    /* A missing callback must not be replaced with a dangling probe. */
    GPU_writeData=0;
    if(vh160_arm_plugin_callback()==0 || GPU_writeData) return 22;
    GPU_writeData=real_gpu;
    puts("VH160_COMPILED_PLUGIN_CALLBACK_PASS enter_return=1 duplicate_refused=1 wrong_data_refused=1 mutated_zero=1 pointer_tamper_refused=1 chain_preserved=1 null_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh160-plugin-test-") as td:
            p=Path(td)
            (p/"fixture.c").write_text(program)
            exe=p/"fixture"
            built=subprocess.run([cc,"-std=c99","-Wall","-Wextra","-Werror",
                "-pedantic",str(p/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(built.returncode,0,built.stderr)
            test=subprocess.run([str(exe)],capture_output=True,text=True,
                timeout=10)
            self.assertEqual(test.returncode,0,test.stderr)
            self.assertIn("VH160_COMPILED_PLUGIN_CALLBACK_PASS",test.stdout)

    def test_ci_wiring_positive_and_corrupted_fifth(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v160-native-plugin-callback.yml").read_text()
        for marker in (
            "apply_map02_v160_plugin_callback",
            "test_map02_v160_plugin_callback.py",
            "VH160_NATIVE_PLUGIN_CALLBACK_PASS",
            "VH160_NATIVE_FIFTH_CALLBACK_REFUSED",
            "vh160_arm_plugin_callback",
        ):
            self.assertIn(marker,workflow)
        self.assertIn("test_map02_v159_native_gpu_sink.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
