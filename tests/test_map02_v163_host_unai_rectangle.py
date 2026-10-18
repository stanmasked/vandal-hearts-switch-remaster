#!/usr/bin/env python3
"""v163 synthetic host-only rectangle: provenance and pixel boundary checks."""
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
from tools.apply_map02_v162_gpulib_parse_flush import patch_frontend as patch_v162
from tools.apply_map02_v163_host_unai_rectangle import (
    patch_frontend,host_only_gpu_smoke_c
)


class HostUnaiRectangle163(unittest.TestCase):
    def test_isolated_mode_gated_after_native_fifth(self):
        prior=patch_v162(patch_v161(patch_v160(patch_v159(sample_frontend()))))
        patched=patch_frontend(prior)
        for token in (
            "--vh163-host-unai-rectangle",
            "vh163_host_rectangle=1;",
            "VH163_INVALID_HOST_MODE_REFUSED",
            "vh158_mutate_fifth",
            "VH163_HOST_ONLY_UNAI_VRAM_RECT_PASS",
            "VH163_HOST_GPU_BASELINE_REFUSED",
            "VH163_HOST_GPU_PIXEL_REFUSED",
            "pixels_changed=16 border_unchanged=20",
            "original_retail=0 mips_raster=0",
            "VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS",
        ):
            self.assertIn(token,patched)
        self.assertLess(patched.index("VH163_HOST_ONLY_UNAI_VRAM_RECT_PASS"),
                        patched.index("VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS"))
        with self.assertRaises(ValueError):
            patch_frontend(patched)

    def test_exact_host_only_packets_and_6x6_border(self):
        c=host_only_gpu_smoke_c()
        for token in (
            "uint32_t vh163_rect[7]",
            "0xe3000000u,0xe407ffffu,0xe5000000u,0xe6000000u",
            "0x600000ffu,0x01c00260u,0x00040004u",
            "GPU_writeDataMem(vh163_rect,7);",
            "(void)GPU_readStatus();",
            "GPU_freeze(1,&vh163_state,&vh163_vram)",
            "vh163_vram[(447u+y)*1024u+607u+x]",
            "actual==0x001fu && actual!=vh163_before",
            "changed!=16u || border_same!=20u",
        ):
            self.assertIn(token,c)
        self.assertNotIn("psxCpu->",c)
        self.assertNotIn("psxRegs",c)

    def test_compiled_host_only_pixel_accounting_and_negative_cases(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc): self.skipTest("compiler not present")
        head=r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define SysPrintf(...) printf(__VA_ARGS__)
typedef struct {unsigned dummy;} GPUFreeze_t;
static uint16_t framebuffer[1024*512];
static unsigned mode, calls;
static int fake_freeze(unsigned type,GPUFreeze_t *f,uint16_t **ptr){
    (void)f;
    if(type!=1u)return -1;
    *ptr=framebuffer;
    return 1;
}
static void fake_write(uint32_t *words,int count){
    if(count!=7 || words[0]!=0xe3000000u ||
       words[1]!=0xe407ffffu || words[2]!=0xe5000000u ||
       words[3]!=0xe6000000u || words[4]!=0x600000ffu ||
       words[5]!=0x01c00260u || words[6]!=0x00040004u) abort();
    calls++;
    for(unsigned y=448u;y<452u;y++)
        for(unsigned x=608u;x<612u;x++)
            if(!(mode==2u && x==609u && y==449u))
                framebuffer[y*1024u+x]=0x001fu;
    if(mode==1u)framebuffer[447u*1024u+607u]=0x001fu;
}
static uint32_t fake_status(void) {return 0u;}
static int (*GPU_freeze)(unsigned,GPUFreeze_t*,uint16_t**)=fake_freeze;
static void (*GPU_writeDataMem)(uint32_t*,int)=fake_write;
static uint32_t (*GPU_readStatus)(void)=fake_status;
static void ClosePlugins(void) {}
static void SysClose(void) {}
static void menu_finish(void) {}
static void plat_finish(void) {}
static int vh163_host_rectangle=1;
static int run_smoke(void){
""" + host_only_gpu_smoke_c() + r"""
return 0;
}
int main(int argc,char **argv){
    if(argc!=2) return 90;
    mode=(unsigned)strtoul(argv[1],NULL,10);
    if(mode==3u)framebuffer[448u*1024u+608u]=0x001fu;
    int result=run_smoke();
    if(mode==0u && (result!=0 || calls!=1u))return 91;
    if(mode!=0u && (result!=67 || (mode==3u && calls!=0u)))return 92;
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh163-rect-") as td:
            p=Path(td)
            (p/"fixture.c").write_text(head)
            exe=p/"fixture"
            built=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                                  "-Wextra","-Werror",str(p/"fixture.c"),
                                  "-o",str(exe)],capture_output=True,text=True,timeout=35)
            self.assertEqual(built.returncode,0,built.stderr)
            for n,marker in (
                (0,"VH163_HOST_ONLY_UNAI_VRAM_RECT_PASS"),
                (1,"VH163_HOST_GPU_PIXEL_REFUSED"),
                (2,"VH163_HOST_GPU_PIXEL_REFUSED"),
                (3,"VH163_HOST_GPU_BASELINE_REFUSED"),
            ):
                with self.subTest(case=n):
                    run=subprocess.run([str(exe),str(n)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    self.assertIn(marker,run.stdout)

    def test_full_native_ci_routes_explicit_host_only_flag(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v163-host-unai-rectangle.yml").read_text()
        for token in (
            "apply_map02_v163_host_unai_rectangle",
            "test_map02_v163_host_unai_rectangle.py",
            "--vh163-host-unai-rectangle",
            "VH163_HOST_ONLY_UNAI_VRAM_RECT_PASS",
            "mips_raster=0",
        ):
            self.assertIn(token,native)
        self.assertIn("test_map02_v162_gpulib_parse_flush.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
