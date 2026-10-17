#!/usr/bin/env python3
"""Opt-in bounded GP0 native VRAM overlap, E6 mask and x-wrap probes.

All three controls are HOST-SUBMITTED *after* successful four-VBlank
synthetic MIPS oracle and v86 copy diagnostics. They are NOT retail gameplay.
"""
from pathlib import Path
from .apply_map02_v86_pcsx_rearmed import apply as apply_v86
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh87_extended_smoke) {
            /* Exactly three new bounded host-control probes, after the
             * original four VBlank edges, 2380 VRAM oracle readbacks,
             * native v85 raster writes and v86 gpulib source/copy tests.
             * No new events are misattributed to original interpreted MIPS.
             */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH87_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            /* The first 4x4 v86 host copy filled x=256..259 with
             * identical nonzero values; destination x260..261 is clear. */
            uint16_t expected[4][4];
            for(unsigned int y=0;y<4;y++){
                for(unsigned int x=0;x<4;x++){
                    expected[y][x]=vram[(160+y)*1024+256+x];
                    if(!expected[y][x] ||
                        expected[y][x]!=expected[y][0] ||
                        (x<2 && vram[(160+y)*1024+260+x]!=0)){
                        SysPrintf("VH87_OVERLAP_PRE_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                    }
                }
            }
            vh86_reset();
            uint32_t overlap_words[4]={
                0x80000000u,(160u<<16)|256u,
                (160u<<16)|258u,(4u<<16)|4u};
            GPU_writeDataMem(overlap_words,4);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH87_OVERLAP_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            for(unsigned int y=0;y<4;y++)
                for(unsigned int x=0;x<4;x++)
                    if(vram[(160+y)*1024+258+x]!=expected[y][x]){
                        SysPrintf("VH87_OVERLAP_PIXEL_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                    }
            const unsigned int os=vh86_store_count(VH86_VRAM_COPY);
            const unsigned int oss=vh86_same_store_count(VH86_VRAM_COPY);
            if(os!=16 || oss!=8 || vh86_write_overflow()){
                SysPrintf("VH87_OVERLAP_COUNT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }

            /* A0 MASK semantic: r6=1 sets STP bit; r6=2 preserves
             * already masked destination even if the C implementation
             * still performs an assignment of the old value; r6=0
             * genuinely replaces it. All 4 destination pixels initially 0.
             */
            for(unsigned int x=0;x<4;x++)
                if(vram[160*1024+400+x]!=0){
                    SysPrintf("VH87_MASK_DEST_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                }
            vh86_reset();
            uint32_t upload_red[5]={0xa0000000u,(160u<<16)|400u,
                (1u<<16)|4u,0x001f001fu,0x001f001fu};
            uint32_t upload_green[5]={0xa0000000u,(160u<<16)|400u,
                (1u<<16)|4u,0x03e003e0u,0x03e003e0u};
            GPU_writeData(0xe6000001u);
            GPU_writeDataMem(upload_red,5);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH87_MASK_FIRST_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[160*1024+400+x]!=0x801fu){
                    SysPrintf("VH87_MASK_SET_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                }
            GPU_writeData(0xe6000002u);
            GPU_writeDataMem(upload_green,5);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH87_MASK_SECOND_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[160*1024+400+x]!=0x801fu){
                    SysPrintf("VH87_MASK_PRESERVE_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                }
            GPU_writeData(0xe6000000u);
            GPU_writeDataMem(upload_green,5);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH87_MASK_FINAL_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[160*1024+400+x]!=0x03e0u){
                    SysPrintf("VH87_MASK_CLEAR_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                }
            const unsigned int ms=vh86_store_count(VH86_A0_UPLOAD);
            const unsigned int mss=vh86_same_store_count(VH86_A0_UPLOAD);
            if(ms!=12 || mss!=4 || vh86_write_overflow()){
                SysPrintf("VH87_MASK_COUNTER_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }

            /* Force gpulib slow copy path x=1022..1023,0..1 with
             * modulo-1024 wrapping and verify two repeated 4x1 copies. */
            for(unsigned int x=0;x<4;x++){
                unsigned int dest=(1022u+x)&1023u;
                if(vram[160*1024+dest]!=0 ||
                   vram[160*1024+256+x]!=expected[0][x]){
                    SysPrintf("VH87_WRAP_DEST_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                }
            }
            vh86_reset();
            uint32_t wrap_words[4]={0x80000000u,(160u<<16)|256u,
                (160u<<16)|1022u,(1u<<16)|4u};
            GPU_writeDataMem(wrap_words,4);
            GPU_writeDataMem(wrap_words,4);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH87_WRAP_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[160*1024+((1022u+x)&1023u)]!=expected[0][x]){
                    SysPrintf("VH87_WRAP_PIXEL_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
                }
            const unsigned int ws=vh86_store_count(VH86_VRAM_COPY);
            const unsigned int wss=vh86_same_store_count(VH86_VRAM_COPY);
            if(ws!=8 || wss!=4 || vh86_write_overflow()){
                SysPrintf("VH87_WRAP_COUNT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }

            vh80_record(VH87_OVERLAP_STORES,os,0,0);
            vh80_record(VH87_OVERLAP_SAME,oss,0,0);
            vh80_record(VH87_MASK_UPLOAD_STORES,ms,0,0);
            vh80_record(VH87_MASK_UPLOAD_SAME,mss,0,0);
            vh80_record(VH87_WRAP_STORES,ws,0,0);
            vh80_record(VH87_WRAP_SAME,wss,0,0);
            if(vh80_dropped()!=0) {
                SysPrintf("VH87_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 13;
            }
            SysPrintf("VH87_GPULIB_PASS overlap_stores=%u overlap_same=%u mask_stores=%u mask_same=%u wrap_stores=%u wrap_same=%u\n",
                os,oss,ms,mss,ws,wss);
        }
'''

def apply(root:Path):
    proof=apply_v86(root)
    frontend=root.resolve()/"frontend/main.c"
    fs=frontend.read_text()
    fs=once(fs,
        '\tint vh86_gpulib_copy_smoke = 0;\n',
        '\tint vh86_gpulib_copy_smoke = 0;\n'
        '\tint vh87_extended_smoke = 0;\n',
        "v87 explicit host-control mode flag")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh86-gpulib-vram-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh87-gpulib-edge-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t}\n',
        "v87 explicit host-control opt-in parser")
    anchor='              u,us,c,cs);\n        }\n'
    fs=once(fs,anchor,anchor+PROBE,
        "append v87 post-v86, post-oracle VRAM controls before v82 private export")
    frontend.write_text(fs)
    return dict(proof,installed_host_control_gp0_overlap_mask_xwrap=True,
        native_v87_runtime_verified=False,
        v87_controls_origin="host_after_v86_and_four_interpreted_mips_vblanks",
        hardware_gpu_mask_equivalence_verified=False,
        asynchronous_GPU_paths_covered=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
