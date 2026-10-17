#!/usr/bin/env python3
"""Pinned PCSX opt-in real worker command-order proof for A0/80/E6.

The host submits ONLY synthetic controls after v78's four genuine emulator
VBlank transitions; never claims retail MAP02 or physical PS1 parity.
"""
from pathlib import Path
from .apply_map02_v89_pcsx_rearmed import apply as apply_v89
from .apply_map02_v69_pcsx_rearmed import once

OBSERVER=r'''
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Producer runs only on the real GPU worker. Main reads after GPUfreeze +
 * shutdown; atomics keep the handoff defined without v80 worker ring writes.
 * Tokens are fixed synthetic *semantic phase labels*, not raw VRAM data.
 * Expected worker stream: A0-red, 80-red, A0-masked-green, 80-green,
 * A0-blue, A0-blue-again, 80-blue => (1,2,3,4,5,5,6).
 */
static unsigned int vh90_enabled,vh90_steps,vh90_order,vh90_bad;
void vh90_reset(void){
    __atomic_store_n(&vh90_steps,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh90_order,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh90_bad,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh90_enabled,1,__ATOMIC_SEQ_CST);
}
unsigned int vh90_stat(unsigned int n){
    if(n==0)return __atomic_load_n(&vh90_steps,__ATOMIC_SEQ_CST);
    if(n==1)return __atomic_load_n(&vh90_order,__ATOMIC_SEQ_CST);
    return __atomic_load_n(&vh90_bad,__ATOMIC_SEQ_CST);
}
static void vh90_worker_token(unsigned int label) {
    if(!__atomic_load_n(&vh90_enabled,__ATOMIC_SEQ_CST))return;
    unsigned int n=__atomic_fetch_add(&vh90_steps,1,__ATOMIC_SEQ_CST);
    if(n>=7u || !label){
        __atomic_fetch_add(&vh90_bad,1,__ATOMIC_SEQ_CST);
        return;
    }
    unsigned int old=__atomic_load_n(&vh90_order,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh90_order,old*17u+label,__ATOMIC_SEQ_CST);
}
#endif
'''

PROBE=r'''
        if(vh90_mixed_smoke) {
            /* All original interpreted MIPS oracle work and prior host
             * v86-v89 controls have passed. These are NEW HOST commands. */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                SysPrintf("VH90_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
            }
            for(unsigned int x=0;x<8;x++)
                if(vram[370*1024+640+x] ||
                   vram[370*1024+680+x] ||
                   vram[370*1024+700+x] ||
                   vram[370*1024+720+x] ||
                   vram[370*1024+750+x]){
                    SysPrintf("VH90_DEST_NOT_EMPTY_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
                }
            pl_rearmed_cbs.thread_rendering=1;
            plugin_call_rearmed_cbs();
            vh88_async_reset();
            vh89_copy_reset();
            vh90_reset();

            /* Real asynchronously submitted GPU raster work makes the
             * native gpu_async_try_dma idle-path bypass unavailable
             * before the following CPU-to-VRAM transfers. */
            uint32_t warm[384*3];
            for(unsigned int i=0;i<384;i++){
                warm[3*i]=0x600000ffu;
                warm[3*i+1]=(320u<<16)|520u;
                warm[3*i+2]=(4u<<16)|4u;
            }
            GPU_writeDataMem(warm,384*3);
            uint32_t a0[7]={0xa0000000u,(370u<<16)|640u,
                (1u<<16)|8u,0,0,0,0};
            uint32_t copy_red[4]={0x80000000u,(370u<<16)|640u,
                (370u<<16)|680u,(1u<<16)|8u};
            uint32_t copy_green[4]={0x80000000u,(370u<<16)|640u,
                (370u<<16)|700u,(1u<<16)|8u};
            uint32_t copy_blue[4]={0x80000000u,(370u<<16)|640u,
                (370u<<16)|720u,(1u<<16)|8u};
            GPU_writeData(0xe6000000u);
            for(unsigned int i=3;i<7;i++)a0[i]=0x001f001fu;
            GPU_writeDataMem(a0,7);                 /* worker label 1 */
            GPU_writeDataMem(copy_red,4);           /* worker label 2 */
            GPU_writeData(0xe6000001u);
            for(unsigned int i=3;i<7;i++)a0[i]=0x03e003e0u;
            GPU_writeDataMem(a0,7);                 /* worker label 3 */
            GPU_writeDataMem(copy_green,4);         /* worker label 4 */
            GPU_writeData(0xe6000000u);
            for(unsigned int i=3;i<7;i++)a0[i]=0x7c007c00u;
            GPU_writeDataMem(a0,7);                 /* worker label 5 */
            GPU_writeDataMem(a0,7);                 /* worker label 5 */
            GPU_writeDataMem(copy_blue,4);          /* worker label 6 */
            if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                SysPrintf("VH90_ASYNC_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
            }
            for(unsigned int x=0;x<8;x++)
                if(vram[370*1024+640+x]!=0x7c00u ||
                   vram[370*1024+680+x]!=0x001fu ||
                   vram[370*1024+700+x]!=0x83e0u ||
                   vram[370*1024+720+x]!=0x7c00u){
                    SysPrintf("VH90_ORDERED_VRAM_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
                }
            const unsigned int a0queued=vh88_async_counter(0);
            const unsigned int a0done=vh88_async_counter(2);
            const unsigned int a0stores=vh88_async_counter(3);
            const unsigned int a0same=vh88_async_counter(4);
            const unsigned int copyqueued=vh89_copy_metric(0);
            const unsigned int copydone=vh89_copy_metric(2);
            const unsigned int copystores=vh89_copy_metric(3);
            const unsigned int copysame=vh89_copy_metric(4);
            const unsigned int copymasked=vh89_copy_metric(5);
            const unsigned int steps=vh90_stat(0);
            const unsigned int order=vh90_stat(1);
            if(a0queued!=4 || a0done!=4 || a0stores!=32 || a0same!=8 ||
               copyqueued!=3 || copydone!=3 ||
               copystores!=24 || copysame!=0 || copymasked!=1 ||
               steps!=7 || order!=27249034u || vh90_stat(2) ||
               vh80_dropped()!=0){
                SysPrintf("VH90_ASYNC_ORDER_REFUSED a0=%u/%u pixels=%u same=%u copies=%u/%u pixels=%u same=%u mask=%u steps=%u order=%u\n",
                    a0queued,a0done,a0stores,a0same,
                    copyqueued,copydone,copystores,copysame,copymasked,steps,order);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
            }
            /* The original GPUfreeze drain happened before turning off
             * the worker; disable now before counting sync assignments. */
            pl_rearmed_cbs.thread_rendering=0;
            plugin_call_rearmed_cbs();
            vh86_reset();
            uint32_t sync_a0[7]={0xa0000000u,(370u<<16)|640u,
                (1u<<16)|8u,0x001f001fu,0x001f001fu,
                0x001f001fu,0x001f001fu};
            uint32_t sync_copy[4]={0x80000000u,(370u<<16)|640u,
                (370u<<16)|750u,(1u<<16)|8u};
            GPU_writeData(0xe6000000u);
            GPU_writeDataMem(sync_a0,7);
            GPU_writeDataMem(sync_copy,4);
            GPU_writeDataMem(sync_copy,4);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                SysPrintf("VH90_SYNC_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
            }
            for(unsigned int x=0;x<8;x++)
                if(vram[370*1024+640+x]!=0x001fu ||
                   vram[370*1024+750+x]!=0x001fu ||
                   vram[370*1024+680+x]!=0x001fu ||
                   vram[370*1024+700+x]!=0x83e0u ||
                   vram[370*1024+720+x]!=0x7c00u){
                    SysPrintf("VH90_SYNC_READBACK_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
                }
            const unsigned int synca0=vh86_store_count(VH86_A0_UPLOAD);
            const unsigned int synccopy=vh86_store_count(VH86_VRAM_COPY);
            const unsigned int syncsame=vh86_same_store_count(VH86_VRAM_COPY);
            if(synca0!=8 || synccopy!=16 || syncsame!=8 ||
               vh86_write_overflow() || vh80_dropped()!=0){
                SysPrintf("VH90_SYNC_COUNTER_REFUSED a0=%u copy=%u same=%u\n",
                    synca0,synccopy,syncsame);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
            }
            /* Nothing ever writes to this v80 ring from the GPU worker.
             * Emit all bounded aggregate events only after GPU shutdown. */
            vh80_record(VH90_A0_QUEUED,a0queued,0,0);
            vh80_record(VH90_A0_DONE,a0done,0,0);
            vh80_record(VH90_A0_STORES,a0stores,0,0);
            vh80_record(VH90_A0_SAME,a0same,0,0);
            vh80_record(VH90_COPY_QUEUED,copyqueued,0,0);
            vh80_record(VH90_COPY_DONE,copydone,0,0);
            vh80_record(VH90_COPY_STORES,copystores,0,0);
            vh80_record(VH90_COPY_SAME,copysame,0,0);
            vh80_record(VH90_MASKED_COPIES,copymasked,0,0);
            vh80_record(VH90_WORKER_STEPS,steps,0,0);
            vh80_record(VH90_WORKER_ORDER,order,0,0);
            vh80_record(VH90_SYNC_A0,synca0,0,0);
            vh80_record(VH90_SYNC_COPY,synccopy,0,0);
            vh80_record(VH90_SYNC_SAME,syncsame,0,0);
            if(vh80_dropped()!=0){
                SysPrintf("VH90_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 16;
            }
            SysPrintf("VH90_MIXED_PASS a0_queued=%u a0_done=%u a0_stores=%u a0_same=%u copy_queued=%u copy_done=%u copy_stores=%u copy_same=%u masked=%u steps=%u order=%u sync_a0=%u sync_copy=%u sync_same=%u\n",
                a0queued,a0done,a0stores,a0same,copyqueued,copydone,copystores,
                copysame,copymasked,steps,order,synca0,synccopy,syncsame);
        }
'''

def apply(root:Path):
    proof=apply_v89(root)
    base=root.resolve()
    ac=base/"plugins/gpulib/gpu_async.c"
    front=base/"frontend/main.c"
    src=ac.read_text()
    fs=front.read_text()
    src=once(src,
        "static unsigned int vh89_copy_enabled, vh89_copy_queued, vh89_copy_started;",
        OBSERVER+"\nstatic unsigned int vh89_copy_enabled, vh89_copy_queued, vh89_copy_started;",
        "install bounded worker-command ordering observer")
    src=once(src,
        '  if(vh84_sampling_enabled())__atomic_fetch_add(&vh88_finished,1,__ATOMIC_SEQ_CST);\n',
        '  if(vh84_sampling_enabled())__atomic_fetch_add(&vh88_finished,1,__ATOMIC_SEQ_CST);\n'
        '  if(cmd->x==640 && cmd->y==370 && w==8 && cmd->h==1 &&\n'
        '     __atomic_load_n(&vh90_enabled,__ATOMIC_SEQ_CST)){\n'
        '    unsigned int color=gpu->vram[370*1024+640];\n'
        '    vh90_worker_token(color==0x001fu?1u:color==0x83e0u?3u:\n'
        '                      color==0x7c00u?5u:0u);\n'
        '  }\n',
        "observe actual completed A0 worker and verify semantically tagged fixture color")
    src=once(src,
        '          done += do_vram_copy(gpup->vram, agpu->ex_regs, list);\n',
        '          done += do_vram_copy(gpup->vram, agpu->ex_regs, list);\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '          if(__atomic_load_n(&vh90_enabled,__ATOMIC_SEQ_CST)) {\n'
        '            unsigned int dest=LE32TOH(((const uint32_t*)list)[2]);\n'
        '            unsigned int dx=dest&1023u,dy=(dest>>16)&511u;\n'
        '            if(dy==370 && (dx==680 || dx==700 || dx==720))\n'
        '              vh90_worker_token(dx==680?2u:dx==700?4u:6u);\n'
        '          }\n'
        '#endif\n',
        "worker GP0(80) writes must complete before test-order token")
    fs=once(fs,'extern unsigned int vh89_copy_metric(unsigned int which);\n',
        'extern unsigned int vh89_copy_metric(unsigned int which);\n'
        'extern void vh90_reset(void);\n'
        'extern unsigned int vh90_stat(unsigned int which);\n',
        "safe main-thread v90 command-order counter APIs")
    fs=once(fs,'\tint vh89_async_copy_smoke = 0;\n',
        '\tint vh89_async_copy_smoke = 0;\n'
        '\tint vh90_mixed_smoke = 0;\n',
        "explicit host-only v90 mode flag")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh89-async-copy-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t\tvh88_async_smoke = 1;\n'
        '\t\t\tvh89_async_copy_smoke = 1;\n'
        '\t\t}\n'
    )
    fs=once(fs,old,old+
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
        '\t\t}\n',
        "v90 CLI requires all original native gates")
    fs=once(fs,
        '                queued,finished,stores,same,masked,sync_stores,sync_same);\n'
        '        }\n',
        '                queued,finished,stores,same,masked,sync_stores,sync_same);\n'
        '        }\n'+PROBE,
        "run v90 only after signed v89 GPU controls before exclusive export")
    ac.write_text(src)
    front.write_text(fs)
    return dict(proof,
        v90_worker_completed_order_observation_installed=True,
        v90_sync_after_async_drain_installed=True,
        runtime_v90_verified=False,original_retail_MAP02_verified=False,
        physical_ps1_vblank_verified=False,HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
