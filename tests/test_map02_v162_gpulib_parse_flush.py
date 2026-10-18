#!/usr/bin/env python3
"""v162: actual gpulib opcode decode and completed command-buffer flush."""
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
from tools.apply_map02_v161_gpulib_queue import patch_frontend as patch_v161
from tools.apply_map02_v162_gpulib_parse_flush import (
    PARSE_ANCHOR, FLUSH_ANCHOR, patch_gpu, patch_frontend
)


def gpu_fixture():
    return r"""
struct psx_gpu gpu;
static int do_cmd_buffer(struct psx_gpu *gpu, uint32_t *data, int count,
    int *cycles_sum, int *cycles_last)
{
    int cmd, pos;
    (void)cycles_sum; (void)cycles_last;
    for(pos=0; pos<count; ) {
    cmd = LE32TOH(data[pos]) >> 24;
    switch(cmd & 0xe0) {
      case 0xe0:
        if(cmd < 0xe8) {
          if(gpu->ex_regs[cmd & 7]==LE32TOH(data[pos])) {
            pos++;
            continue;
          }
          /* The genuine gpulib forwards changed E3 state to its
           * renderer, which consumes the word. The tiny compiled
           * fixture models that state transition without pixels. */
          gpu->ex_regs[cmd & 7]=LE32TOH(data[pos]);
          pos++;
          continue;
        }
        return count-pos;
      default:
        return count-pos;
    }
    }
    return count-pos;
}
static void flush_cmd_buffer(struct psx_gpu *gpu)
{
  int dummy=0, cycles_last=0, left;
  left = do_cmd_buffer(gpu, gpu->cmd_buffer, gpu->cmd_len, &dummy, &cycles_last);
  gpu->cmd_len=left;
}
static void GPUwriteData(uint32_t data) {
  gpu.cmd_buffer[gpu.cmd_len++] = HTOLE32(data);
}
static uint32_t GPUreadStatus(void) {
  if(gpu.cmd_len>0) flush_cmd_buffer(&gpu);
  return 0;
}
"""


class NativeGpulibParseFlush162(unittest.TestCase):
    def test_exact_parser_and_flush_anchors(self):
        src=gpu_fixture()
        patched=patch_gpu(src)
        self.assertIn("vh162_note_gpu_parse(gpu, data, pos, count, cmd);",patched)
        self.assertIn("vh162_note_gpu_flush(gpu, left);",patched)
        self.assertLess(patched.index(PARSE_ANCHOR),patched.index(
            "vh162_note_gpu_parse(gpu, data, pos, count, cmd);"))
        self.assertLess(patched.index(FLUSH_ANCHOR),patched.index(
            "vh162_note_gpu_flush(gpu, left);"))
        with self.assertRaises(ValueError):
            patch_gpu(patched)
        with self.assertRaises(ValueError):
            patch_gpu(src.replace(PARSE_ANCHOR,
                "    cmd = data[pos] >> 24;"))
        with self.assertRaises(ValueError):
            patch_gpu(src.replace(FLUSH_ANCHOR,
                "  left = 0;"))

    def test_frontend_explicit_read_status_only_in_synthetic_mode(self):
        prior=patch_v161(patch_v160(patch_v159(sample_frontend())))
        front=patch_frontend(prior)
        for marker in (
            "if(vh162_arm_gpu_parser()!=0){",
            "VH162_PARSER_ARM_REFUSED",
            "VH162_GPU_STATUS_CALLBACK_REFUSED",
            "(void)GPU_readStatus();",
            "parsed!=1u || flushed!=1u ||",
            "parsed!=0u || flushed!=0u ||",
            "VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS",
            "VH162_NATIVE_FIFTH_PARSE_REFUSED",
            "VH161_NATIVE_GPULIB_QUEUE_PASS",
            "VH160_NATIVE_PLUGIN_CALLBACK_PASS",
        ):
            self.assertIn(marker,front)
        self.assertLess(front.index("VH162_GPU_PREFLIGHT_REFUSED"),
                        front.index("if(vh161_arm_gpu_queue()!=0){"))
        self.assertLess(front.index("(void)GPU_readStatus();"),
                        front.index("if(vh161_arm_gpu_queue()!=0){"))
        self.assertLess(front.index("if(vh161_arm_gpu_queue()!=0){"),
                        front.index("if(vh162_arm_gpu_parser()!=0){"))
        self.assertEqual(front.count("(void)GPU_readStatus();"),2)
        with self.assertRaises(ValueError):
            patch_frontend(front)

    def test_compiled_real_parser_and_flush_refusals(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("no C compiler")
        fixture=gpu_fixture()
        c=r"""
#include <stdint.h>
#include <stdio.h>
#define VH_MAP02_V66_PCSX_PROBE 1
#define HTOLE32(x) (x)
#define LE32TOH(x) (x)
#define CMD_BUFFER_LEN 16
struct psx_gpu {uint32_t cmd_buffer[CMD_BUFFER_LEN];int cmd_len;uint32_t ex_regs[8];};
""" + patch_gpu(fixture) + r"""
int main(void) {
    gpu.ex_regs[3]=0xe3000000u;
    /* Inactive observer must leave the original parser functional. */
    GPUwriteData(0xe3000000u);
    GPUreadStatus();
    if(gpu.cmd_len || vh162_gpu_parse_visits() ||
       vh162_gpu_flushes() || vh162_gpu_parse_faults())return 1;

    if(vh162_arm_gpu_parser()!=0 || vh162_arm_gpu_parser()==0) return 2;
    GPUwriteData(0xe3000000u);
    GPUreadStatus();
    if(gpu.cmd_len || vh162_gpu_parse_visits()!=1u ||
       vh162_gpu_flushes()!=1u || vh162_gpu_parse_faults()) return 3;
    if(vh162_disarm_gpu_parser()!=0 ||
       vh162_disarm_gpu_parser()==0) return 4;

    /* Two E3 words cannot be mistaken for one proven queue flush. */
    if(vh162_arm_gpu_parser()!=0) return 5;
    GPUwriteData(0xe3000000u);
    GPUwriteData(0xe3000000u);
    GPUreadStatus();
    if(vh162_gpu_parse_visits()!=0u ||
       vh162_gpu_flushes()!=0u ||
       vh162_gpu_parse_faults()==0u) return 6;
    if(vh162_disarm_gpu_parser()!=0) return 7;

    /* Mutated fifth never emits GP0, so read status cannot prove parse. */
    if(vh162_arm_gpu_parser()!=0) return 8;
    GPUreadStatus();
    if(vh162_gpu_parse_visits() || vh162_gpu_flushes() ||
       vh162_gpu_parse_faults()) return 9;
    if(vh162_disarm_gpu_parser()!=0) return 10;

    /* Wrong word: no false exact-word witness. */
    if(vh162_arm_gpu_parser()!=0) return 11;
    GPUwriteData(0xe3000001u);
    GPUreadStatus();
    if(vh162_gpu_parse_visits() ||
       vh162_gpu_flushes() ||
       vh162_gpu_parse_faults()==0) return 12;
    if(vh162_disarm_gpu_parser()!=0) return 13;
    /* The changed E3 was consumed as GPU state, despite correctly
     * failing the EXACT-word proof: no stale word for the next case. */
    if(gpu.cmd_len!=0 || gpu.ex_regs[3]!=0xe3000001u) return 18;

    /* Refuse stale GPU queue; an actual status preflight clears it.
     * Only THEN may the v162 observer arm, without credit for preflight. */
    GPUwriteData(0xe3000000u);
    if(vh162_arm_gpu_parser()==0) return 14;
    GPUreadStatus();
    if(gpu.cmd_len!=0 || vh162_arm_gpu_parser()!=0) return 15;
    if(vh162_gpu_parse_visits() || vh162_gpu_flushes() ||
       vh162_gpu_parse_faults()) return 16;
    if(vh162_disarm_gpu_parser()!=0) return 17;
    puts("VH162_COMPILED_GPULIB_PARSE_FLUSH_PASS parsed=1 flushed=1 duplicate_refused=1 wrong_word_refused=1 mutated_zero=1 stale_queue_preflight=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh162-gpulib-") as td:
            p=Path(td)
            (p/"fixture.c").write_text(c)
            exe=p/"fixture"
            built=subprocess.run([cc,"-std=c99","-Wall","-Wextra",
                "-Werror","-pedantic",str(p/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(built.returncode,0,built.stderr)
            out=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(out.returncode,0,out.stderr)
            self.assertIn("VH162_COMPILED_GPULIB_PARSE_FLUSH_PASS",out.stdout)

    def test_full_pinned_native_wiring(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        independent=(ROOT/".github/workflows/map02-v162-native-parse-flush.yml").read_text()
        for marker in (
            "apply_map02_v162_gpulib_parse_flush",
            "test_map02_v162_gpulib_parse_flush.py",
            "VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS",
            "VH162_NATIVE_FIFTH_PARSE_REFUSED",
            "vh162_note_gpu_parse(gpu, data, pos, count, cmd)",
            "vh162_note_gpu_flush(gpu, left)",
        ):
            self.assertIn(marker,workflow)
        self.assertIn("test_map02_v161_gpulib_queue.py",independent)
        self.assertIn("original_retail_executed=0",independent)


if __name__=="__main__":
    unittest.main()
