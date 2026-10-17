#!/usr/bin/env python3
"""Run two independent async->sync GPU transfer cycles in the pinned emulator.

Only HOST-SUBMITTED controls after original synthetic MIPS/VBlank oracle.
The renderer, gpulib and DMA worker remain the authentic pinned PCSX paths.
"""
from pathlib import Path
from .apply_map02_v90_pcsx_rearmed import apply as apply_v90
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh91_cycles_smoke) {
            /* v78 4 VBlanks and 2380 original VRAM samples and all
             * v86-v90 host controls have passed before these two rounds.
             * Max 64 extra warmed GP0 sprite handlers keeps v80
             * ring within 4096 events, including v90's 3502 baseline. */
            unsigned int rounds[2][11]={{0}};
            for(unsigned int phase=0;phase<2;phase++) {
                const unsigned int y=380u+phase;
                GPUFreeze_t state={0};
                uint16_t *vram=NULL;
                if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                    SysPrintf("VH91_PRE_FREEZE_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                }
                for(unsigned int x=0;x<8;x++)
                    if(vram[y*1024+560+x] ||
                       vram[y*1024+600+x] ||
                       vram[y*1024+620+x] ||
                       vram[y*1024+640+x]){
                        SysPrintf("VH91_INITIAL_VRAM_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                    }
                pl_rearmed_cbs.thread_rendering=1;
                plugin_call_rearmed_cbs();
                vh88_async_reset();
                vh89_copy_reset();
                /* The worker stays active long enough to encourage
                 * real asynchronous A0 queuing. Original gpulib may
                 * still take its synchronous fallback: never claim
                 * such an A0 was queued or executed in the worker. */
                uint32_t warm[32*3];
                for(unsigned int i=0;i<32;i++){
                    warm[3*i]=0x600000ffu;
                    warm[3*i+1]=(320u<<16)|520u;
                    warm[3*i+2]=(4u<<16)|4u;
                }
                GPU_writeDataMem(warm,32*3);
                uint32_t upload[7]={0xa0000000u,(y<<16)|560u,
                    (1u<<16)|8u,0,0,0,0};
                uint32_t copy_red[4]={0x80000000u,(y<<16)|560u,
                    (y<<16)|600u,(1u<<16)|8u};
                uint32_t copy_green[4]={0x80000000u,(y<<16)|560u,
                    (y<<16)|620u,(1u<<16)|8u};
                GPU_writeData(0xe6000000u);
                for(unsigned int i=3;i<7;i++)upload[i]=0x001f001fu;
                GPU_writeDataMem(upload,7);
                GPU_writeDataMem(copy_red,4);
                GPU_writeData(0xe6000001u);
                for(unsigned int i=3;i<7;i++)upload[i]=0x03e003e0u;
                GPU_writeDataMem(upload,7);
                GPU_writeDataMem(copy_green,4);
                if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                    SysPrintf("VH91_ASYNC_FREEZE_REFUSED phase=%u\n",phase);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                }
                for(unsigned int x=0;x<8;x++)
                    if(vram[y*1024+560+x]!=0x83e0u ||
                       vram[y*1024+600+x]!=0x001fu ||
                       vram[y*1024+620+x]!=0x83e0u){
                        SysPrintf("VH91_ASYNC_READBACK_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                    }
                unsigned int *s=rounds[phase];
                s[0]=vh88_async_counter(0); /* queued A0 */
                s[1]=vh88_async_counter(2); /* worker completed A0 */
                s[2]=vh88_async_counter(3); /* worker 16bit writes */
                s[3]=vh89_copy_metric(0);   /* queued copy */
                s[4]=vh89_copy_metric(2);   /* completed copy */
                s[5]=vh89_copy_metric(3);   /* worker copy stores */
                s[6]=vh89_copy_metric(4);   /* same-valued copy */
                s[7]=vh89_copy_metric(5);   /* masked copies */
                if(s[0]>2 || s[1]!=s[0] || s[2]!=s[0]*8 ||
                   vh88_async_counter(4)!=0 ||
                   s[3]!=2 || s[4]!=2 || s[5]!=16 ||
                   s[6]!=0 || s[7]!=1 || vh80_dropped()){
                    SysPrintf("VH91_ASYNC_COUNTER_REFUSED phase=%u queued_a0=%u done=%u stores=%u copies=%u/%u stores=%u same=%u mask=%u\n",
                        phase,s[0],s[1],s[2],s[3],s[4],s[5],s[6],s[7]);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                }
                GPU_writeData(0xe6000000u);
                if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                    SysPrintf("VH91_MASK_RESET_REFUSED phase=%u\n",phase);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                }
                pl_rearmed_cbs.thread_rendering=0;
                plugin_call_rearmed_cbs();
                vh86_reset();
                uint32_t sync_a0[7]={0xa0000000u,(y<<16)|560u,
                    (1u<<16)|8u,0x7c007c00u,0x7c007c00u,
                    0x7c007c00u,0x7c007c00u};
                uint32_t sync_copy[4]={0x80000000u,(y<<16)|560u,
                    (y<<16)|640u,(1u<<16)|8u};
                GPU_writeDataMem(sync_a0,7);
                GPU_writeDataMem(sync_copy,4);
                GPU_writeDataMem(sync_copy,4);
                if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                    SysPrintf("VH91_SYNC_FREEZE_REFUSED phase=%u\n",phase);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                }
                for(unsigned int x=0;x<8;x++)
                    if(vram[y*1024+560+x]!=0x7c00u ||
                       vram[y*1024+600+x]!=0x001fu ||
                       vram[y*1024+620+x]!=0x83e0u ||
                       vram[y*1024+640+x]!=0x7c00u){
                        SysPrintf("VH91_SYNC_READBACK_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                    }
                s[8]=vh86_store_count(VH86_A0_UPLOAD);
                s[9]=vh86_store_count(VH86_VRAM_COPY);
                s[10]=vh86_same_store_count(VH86_VRAM_COPY);
                if(s[8]!=8 || s[9]!=16 || s[10]!=8 ||
                   vh86_write_overflow() || vh80_dropped()!=0){
                    SysPrintf("VH91_SYNC_COUNTER_REFUSED phase=%u a0=%u copy=%u same=%u\n",
                        phase,s[8],s[9],s[10]);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                }
                SysPrintf("VH91_CYCLE_PASS round=%u a0_queue=%u a0_done=%u a0_stores=%u copies=%u/%u copy_stores=%u copy_same=%u mask=%u sync_a0=%u sync_copy=%u sync_same=%u\n",
                    phase+1,s[0],s[1],s[2],s[3],s[4],s[5],s[6],
                    s[7],s[8],s[9],s[10]);
            }
            /* Ensure second callback transition preserved first round
             * contents as well as the second round's new destinations. */
            GPUFreeze_t final_state={0};
            uint16_t *final_vram=NULL;
            if(GPU_freeze(1,&final_state,&final_vram)!=1 || !final_vram) {
                SysPrintf("VH91_FINAL_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
            }
            for(unsigned int phase=0;phase<2;phase++){
                unsigned int y=380+phase;
                for(unsigned int x=0;x<8;x++)
                    if(final_vram[y*1024+560+x]!=0x7c00u ||
                       final_vram[y*1024+600+x]!=0x001fu ||
                       final_vram[y*1024+620+x]!=0x83e0u ||
                       final_vram[y*1024+640+x]!=0x7c00u){
                        SysPrintf("VH91_CROSS_ROUND_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
                    }
            }
            const unsigned int first_kind=VH91_R1_A0_QUEUED;
            for(unsigned int phase=0;phase<2;phase++)
                for(unsigned int i=0;i<11;i++)
                    vh80_record(first_kind+phase*11+i,rounds[phase][i],0,0);
            if(vh80_dropped()!=0){
                SysPrintf("VH91_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 17;
            }
            SysPrintf("VH91_CYCLES_PASS rounds=2 async_copies=4 sync_copies=4 cross_round_retained=1\n");
        }
'''

def apply(root:Path):
    proof=apply_v90(root)
    frontend=root.resolve()/"frontend/main.c"
    fs=frontend.read_text()
    fs=once(fs,
        '\tint vh90_mixed_smoke = 0;\n',
        '\tint vh90_mixed_smoke = 0;\n'
        '\tint vh91_cycles_smoke = 0;\n',
        "v91 two additional modes with all predecessors")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh90-mixed-gpu-order-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t\tvh88_async_smoke = 1;\n'
        '\t\t\tvh89_async_copy_smoke = 1;\n'
        '\t\t\tvh90_mixed_smoke = 1;\n'
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh91-repeat-mode-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t\tvh88_async_smoke = 1;\n'
        '\t\t\tvh89_async_copy_smoke = 1;\n'
        '\t\t\tvh90_mixed_smoke = 1;\n'
        '\t\t\tvh91_cycles_smoke = 1;\n'
        '\t\t}\n',
        "v91 explicit opt-in after every previous GPU stage")
    fs=once(fs,
        '                copysame,copymasked,steps,order,synca0,synccopy,syncsame);\n'
        '        }\n',
        '                copysame,copymasked,steps,order,synca0,synccopy,syncsame);\n'
        '        }\n'+PROBE,
        "v91 repeat worker controls only after v90 order and pre-v82 export")
    frontend.write_text(fs)
    return dict(proof,
        two_full_gpu_async_sync_transition_cycles_installed=True,
        original_four_vblank_oracle_preserved=True,
        host_test_A0_sync_fallback_explicit=True,
        runtime_v91_verified=False,
        original_retail_MAP02_verified=False,
        physical_ps1_vblank_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
