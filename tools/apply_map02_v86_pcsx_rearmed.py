#!/usr/bin/env python3
"""Bounded gpulib A0-upload and 80-copy native VRAM write path audit.

v78 synthetic MIPS GP0(A0) uploads are genuine emulator execution; the
GP0(80) exercise is explicitly HOST-SUBMITTED *after* the v78 GPU oracle,
never mislabeled original MIPS/retail game traffic.
"""
from pathlib import Path
from .apply_map02_v85_pcsx_rearmed import apply as apply_v85
from .apply_map02_v69_pcsx_rearmed import once

HEADER=r'''#ifdef VH_MAP02_V66_PCSX_PROBE
#include "../../libpcsxcore/vh80_native_timeline.h"
/* Observe synchronous gpulib destination assignments before calling
 * original do_vram_line(), which has no early-out for A0 writes.
 * r6 follows exactly the native cpy_mask() unconditional assignment. */
static void vh86_observe_upload(uint16_t *vram,int x,int y,
    const uint16_t *src,int n,uint32_t r6)
{
    if(!vh84_sampling_enabled())return;
    uint16_t *dst=VRAM_MEM_XY(vram,x,y);
    for(int i=0;i<n;i++){
        uint16_t old=dst[i],next=src[i];
        if(r6==1)next|=0x8000;
        else if(r6){
            uint16_t mask=(uint16_t)((int16_t)old>>15);
            next=(old&mask)|((uint16_t)(src[i]|(uint16_t)(r6<<15))&~mask);
        }
        vh86_note_store(VH86_A0_UPLOAD,old,next);
    }
}
static void vh86_copy_store(uint16_t *dst,uint16_t value){
    if(vh84_sampling_enabled())
        vh86_note_store(VH86_VRAM_COPY,*dst,value);
    *dst=value;
}
#define VH86_COPY_STORE(D,V) vh86_copy_store((D),(V))
#else
#define VH86_COPY_STORE(D,V) (*(D)=(V))
#endif

'''

def apply(root:Path):
    proof=apply_v85(root)
    base=root.resolve()
    gpu=base/"plugins/gpulib/gpu.c"
    frontend=base/"frontend/main.c"
    source=gpu.read_text()
    fs=frontend.read_text()
    source=once(source,
        '#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))\n#endif\n',
        '#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))\n#endif\n\n'+HEADER,
        "gpulib C helper immediately after VRAM macros and headers")
    for old in (
        "do_vram_line(vram, x + o, y, sdata, l, is_read, r6);",
        "do_vram_line(vram, x, y, sdata, w, is_read, r6);",
        "do_vram_line(vram, x, y, sdata, count, is_read, r6);",
    ):
        args=old[len("do_vram_line("):-2]
        source=once(source,old,
            '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
            '    if(!is_read)vh86_observe_upload('+args.replace("is_read, ","") +');\n'
            '#endif\n    '+old,
            "synchronous A0 write line "+old)
    source=once(source,
        '          dst[(dx + x + x1) & 0x3ff] = lbuf[x1] | msb;',
        '          VH86_COPY_STORE(&dst[(dx + x + x1) & 0x3ff],(uint16_t)(lbuf[x1] | msb));',
        "per-pixel wrapped/overlap/masked GP0(80) copy writes")
    source=once(source,
        '      memcpy(VRAM_MEM_XY(vram, dx, dy1 & 0x1ff),\n'
        '             VRAM_MEM_XY(vram, sx, sy1 & 0x1ff), w * 2);',
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '      if(vh84_sampling_enabled()){\n'
        '        const uint16_t *copy_source=VRAM_MEM_XY(vram,sx,sy1 & 0x1ff);\n'
        '        const uint16_t *copy_dest=VRAM_MEM_XY(vram,dx,dy1 & 0x1ff);\n'
        '        for(uint32_t k=0;k<w;k++)\n'
        '          vh86_note_store(VH86_VRAM_COPY,copy_dest[k],copy_source[k]);\n'
        '      }\n'
        '#endif\n'
        '      memcpy(VRAM_MEM_XY(vram, dx, dy1 & 0x1ff),\n'
        '             VRAM_MEM_XY(vram, sx, sy1 & 0x1ff), w * 2);',
        "GP0(80) fast row copy before original memcpy")
    fs=once(fs,
        '\tint vh85_native_store_smoke = 0;\n',
        '\tint vh85_native_store_smoke = 0;\n'
        '\tint vh86_gpulib_copy_smoke = 0;\n',
        "v86 private opt-in flag")
    fs=once(fs,
        '\t\telse if (!strcmp(argv[i], "--vh85-unai-pixel-store-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t}\n',
        '\t\telse if (!strcmp(argv[i], "--vh85-unai-pixel-store-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t}\n'
        '\t\telse if (!strcmp(argv[i], "--vh86-gpulib-vram-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t}\n',
        "v86 signed synthetic scene flag")
    probe=r'''
        if(vh86_gpulib_copy_smoke) {
            /* The preceding four original interpreted CPU stages and
             * 2380 pixel oracle checks have already succeeded.
             * This is a clearly HOST-SUBMITTED separate GP0(80) control;
             * it is not an original MIPS, game or retail command. */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH86_COPY_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 12;
            }
            for(unsigned int row=0;row<4;row++)
                for(unsigned int x=0;x<4;x++)
                    if(vram[(160+row)*1024+40+x]==0 ||
                       vram[(160+row)*1024+256+x]!=0) {
                        SysPrintf("VH86_COPY_SOURCE_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 12;
                    }
            uint32_t copy_words[4]={0x80000000u,(160u<<16)|40u,
                (160u<<16)|256u,(4u<<16)|4u};
            GPU_writeDataMem(copy_words,4);
            GPU_writeDataMem(copy_words,4);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH86_COPY_READBACK_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 12;
            }
            for(unsigned int row=0;row<4;row++)
                for(unsigned int x=0;x<4;x++)
                    if(vram[(160+row)*1024+256+x]!=vram[(160+row)*1024+40+x]) {
                        SysPrintf("VH86_COPY_VRAM_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 12;
                    }
            const unsigned int u=vh86_store_count(VH86_A0_UPLOAD);
            const unsigned int us=vh86_same_store_count(VH86_A0_UPLOAD);
            const unsigned int c=vh86_store_count(VH86_VRAM_COPY);
            const unsigned int cs=vh86_same_store_count(VH86_VRAM_COPY);
            if(vh86_write_overflow() || u==0 || us==0 || us>=u ||
               c!=32 || cs!=16 || vh80_dropped()!=0) {
                SysPrintf("VH86_GPULIB_COUNTER_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 12;
            }
            vh80_record(VH86_A0_STORES,u,0,0);
            vh80_record(VH86_A0_SAME,us,0,0);
            vh80_record(VH86_COPY_STORES,c,0,0);
            vh80_record(VH86_COPY_SAME,cs,0,0);
            if(vh80_dropped()!=0) {
                SysPrintf("VH86_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 12;
            }
            SysPrintf("VH86_GPULIB_PASS mips_a0_stores=%u mips_a0_same=%u host_copy_stores=%u host_copy_same=%u\n",
              u,us,c,cs);
        }
'''
    fs=once(fs,'        if(vh82_export_smoke) {\n',
        probe+'        if(vh82_export_smoke) {\n',
        "perform distinct host GP0(80) test after 4-VBlank oracle, before private export")
    gpu.write_text(source)
    frontend.write_text(fs)
    return dict(proof,native_gpulib_a0_upload_and_copy_observers_installed=True,
        v86_native_runtime_verified=False,
        copy_probe_origin="host_injected_after_four_emulator_vblanks",
        cpu_gp0_a0_origin="interpreted_signed_synthetic_mips",
        async_gpu_write_provenance_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
