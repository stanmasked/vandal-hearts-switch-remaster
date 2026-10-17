#!/usr/bin/env python3
"""Observe real PCSX async GP0(80) copy execution and sync-mode transition.

The v78 four-VBlank scene remains untouched. v89 host controls run strictly
after successful v88 A0 worker observability and are not retail/MIPS traffic.
"""
from pathlib import Path
from .apply_map02_v88_pcsx_rearmed import apply as apply_v88
from .apply_map02_v69_pcsx_rearmed import once

ASYNC_STATS=r'''
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Async worker owns vh89_copy_active; only bounded aggregate atomics cross
 * to main after GPUfreeze+callback shutdown. No worker v80 ring writes. */
static unsigned int vh89_copy_enabled, vh89_copy_queued, vh89_copy_started;
static unsigned int vh89_copy_finished, vh89_copy_masked;
static unsigned int vh89_copy_stores, vh89_copy_same;
static __thread int vh89_copy_active;
void vh89_copy_reset(void) {
    __atomic_store_n(&vh89_copy_enabled,1,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh89_copy_queued,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh89_copy_started,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh89_copy_finished,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh89_copy_masked,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh89_copy_stores,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh89_copy_same,0,__ATOMIC_SEQ_CST);
}
unsigned int vh89_copy_metric(unsigned int n) {
    switch(n) {
    case 0:return __atomic_load_n(&vh89_copy_queued,__ATOMIC_SEQ_CST);
    case 1:return __atomic_load_n(&vh89_copy_started,__ATOMIC_SEQ_CST);
    case 2:return __atomic_load_n(&vh89_copy_finished,__ATOMIC_SEQ_CST);
    case 3:return __atomic_load_n(&vh89_copy_stores,__ATOMIC_SEQ_CST);
    case 4:return __atomic_load_n(&vh89_copy_same,__ATOMIC_SEQ_CST);
    case 5:return __atomic_load_n(&vh89_copy_masked,__ATOMIC_SEQ_CST);
    default:return 0;
    }
}
void vh89_copy_note_store(uint16_t old, uint16_t next) {
    if(!vh89_copy_active)return;
    __atomic_fetch_add(&vh89_copy_stores,1,__ATOMIC_SEQ_CST);
    if(old==next)__atomic_fetch_add(&vh89_copy_same,1,__ATOMIC_SEQ_CST);
}
#endif
'''

PROBE=r'''
        if(vh89_async_copy_smoke) {
            /* All new commands are HOST-SUBMITTED after v78 + v86-v88
             * passed. Distinguish actual asynchronous worker execution
             * from successful queue admission and from synchronous copy. */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH89_START_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[160*1024+400+x]!=0x03e0u ||
                   vram[360*1024+720+x] ||
                   vram[360*1024+730+x] ||
                   vram[360*1024+740+x]) {
                    SysPrintf("VH89_SOURCE_OR_DEST_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
                }
            pl_rearmed_cbs.thread_rendering=1;
            plugin_call_rearmed_cbs();
            vh89_copy_reset();
            uint32_t fast_copy[4]={0x80000000u,(160u<<16)|400u,
                                   (360u<<16)|720u,(1u<<16)|4u};
            uint32_t masked_copy[4]={0x80000000u,(160u<<16)|400u,
                                     (360u<<16)|730u,(1u<<16)|4u};
            GPU_writeDataMem(fast_copy,4);
            GPU_writeDataMem(fast_copy,4);
            GPU_writeData(0xe6000001u); /* GP0 E6 forces destination STP */
            GPU_writeDataMem(masked_copy,4);
            GPU_writeDataMem(masked_copy,4);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH89_ASYNC_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[360*1024+720+x]!=0x03e0u ||
                   vram[360*1024+730+x]!=0x83e0u) {
                    SysPrintf("VH89_ASYNC_VRAM_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
                }
            const unsigned int queued=vh89_copy_metric(0);
            const unsigned int started=vh89_copy_metric(1);
            const unsigned int finished=vh89_copy_metric(2);
            const unsigned int stores=vh89_copy_metric(3);
            const unsigned int same=vh89_copy_metric(4);
            const unsigned int masked=vh89_copy_metric(5);
            if(queued!=4 || started!=4 || finished!=4 ||
               stores!=16 || same!=8 || masked!=2 || vh80_dropped()!=0) {
                SysPrintf("VH89_ASYNC_COPY_REFUSED queued=%u started=%u finished=%u stores=%u same=%u masked=%u\n",
                    queued,started,finished,stores,same,masked);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
            }
            /* Force a proven mode switch after all worker activity ends.
             * Restore E6 mask=0 before the synchronous destination copies. */
            GPU_writeData(0xe6000000u);
            GPU_freeze(1,&state,&vram);
            pl_rearmed_cbs.thread_rendering=0;
            plugin_call_rearmed_cbs();
            vh86_reset();
            uint32_t sync_copy[4]={0x80000000u,(360u<<16)|720u,
                                   (360u<<16)|740u,(1u<<16)|4u};
            GPU_writeDataMem(sync_copy,4);
            GPU_writeDataMem(sync_copy,4);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH89_SYNC_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
            }
            for(unsigned int x=0;x<4;x++)
                if(vram[360*1024+740+x]!=0x03e0u) {
                    SysPrintf("VH89_SYNC_COPY_VRAM_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
                }
            const unsigned int sync_stores=vh86_store_count(VH86_VRAM_COPY);
            const unsigned int sync_same=vh86_same_store_count(VH86_VRAM_COPY);
            if(sync_stores!=8 || sync_same!=4 || vh86_write_overflow() ||
               vh80_dropped()!=0) {
                SysPrintf("VH89_SYNC_COUNT_REFUSED attempts=%u same=%u\n",
                    sync_stores,sync_same);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
            }
            vh80_record(VH89_COPY_QUEUED,queued,0,0);
            vh80_record(VH89_COPY_COMPLETED,finished,0,0);
            vh80_record(VH89_COPY_STORES,stores,0,0);
            vh80_record(VH89_COPY_SAME,same,0,0);
            vh80_record(VH89_MASKED_COMPLETED,masked,0,0);
            vh80_record(VH89_SYNC_STORES,sync_stores,0,0);
            vh80_record(VH89_SYNC_SAME,sync_same,0,0);
            if(vh80_dropped()!=0) {
                SysPrintf("VH89_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 15;
            }
            SysPrintf("VH89_ASYNC_COPY_PASS queued=%u completed=%u stores=%u same=%u masked=%u sync_stores=%u sync_same=%u\n",
                queued,finished,stores,same,masked,sync_stores,sync_same);
        }
'''

def apply(root:Path):
    proof=apply_v88(root)
    base=root.resolve()
    gpu=base/"plugins/gpulib/gpu.c"
    async_c=base/"plugins/gpulib/gpu_async.c"
    frontend=base/"frontend/main.c"
    ac=async_c.read_text()
    g=gpu.read_text()
    fs=frontend.read_text()
    ac=once(ac,"static unsigned int vh88_queue, vh88_started, vh88_finished;",
        ASYNC_STATS+"\nstatic unsigned int vh88_queue, vh88_started, vh88_finished;",
        "main-thread to async-worker counters for copy acceptance and stores")
    ac=once(ac,
        '        int added = dst_can_add = do_add_pos(agpu, list, len, &pos_added);\n',
        '        int added = dst_can_add = do_add_pos(agpu, list, len, &pos_added);\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '        if(added && cmd>=0x80 && cmd<=0x9f &&\n'
        '           __atomic_load_n(&vh89_copy_enabled,__ATOMIC_SEQ_CST))\n'
        '          __atomic_fetch_add(&vh89_copy_queued,1,__ATOMIC_SEQ_CST);\n'
        '#endif\n',
        "only count accepted async GP0(80) queue submissions")
    ac=once(ac,
        '        case 0x80 ... 0x9f:\n'
        '          done += do_vram_copy(gpup->vram, agpu->ex_regs, list);\n'
        '          break;\n',
        '        case 0x80 ... 0x9f:\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '          if(__atomic_load_n(&vh89_copy_enabled,__ATOMIC_SEQ_CST)) {\n'
        '            vh89_copy_active=1;\n'
        '            __atomic_fetch_add(&vh89_copy_started,1,__ATOMIC_SEQ_CST);\n'
        '          }\n'
        '#endif\n'
        '          done += do_vram_copy(gpup->vram, agpu->ex_regs, list);\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '          if(vh89_copy_active) {\n'
        '            vh89_copy_active=0;\n'
        '            __atomic_fetch_add(&vh89_copy_finished,1,__ATOMIC_SEQ_CST);\n'
        '            if(agpu->ex_regs[6]&1u)\n'
        '              __atomic_fetch_add(&vh89_copy_masked,1,__ATOMIC_SEQ_CST);\n'
        '          }\n'
        '#endif\n'
        '          break;\n',
        "track real gpu_async_thread GP0(80) worker start and finish")
    g=once(g,
        'static void vh86_copy_store(uint16_t *dst,uint16_t value){',
        '#if defined(VH_MAP02_V66_PCSX_PROBE) && defined(USE_ASYNC_GPU)\n'
        'extern void vh89_copy_note_store(uint16_t old,uint16_t next);\n'
        '#define VH89_NOTE_COPY(OLD,NEW) vh89_copy_note_store((OLD),(NEW))\n'
        '#else\n'
        '#define VH89_NOTE_COPY(OLD,NEW) ((void)0)\n'
        '#endif\n'
        'static void vh86_copy_store(uint16_t *dst,uint16_t value){',
        "enable per-destination observation only if async GPU built")
    g=once(g,
        '    if(vh84_sampling_enabled())\n'
        '        vh86_note_store(VH86_VRAM_COPY,*dst,value);\n',
        '    if(vh84_sampling_enabled()) {\n'
        '        VH89_NOTE_COPY(*dst,value);\n'
        '        vh86_note_store(VH86_VRAM_COPY,*dst,value);\n'
        '    }\n',
        "observe slow-path destination in native copy assignment")
    g=once(g,
        '        for(uint32_t k=0;k<w;k++)\n'
        '          vh86_note_store(VH86_VRAM_COPY,copy_dest[k],copy_source[k]);\n',
        '        for(uint32_t k=0;k<w;k++) {\n'
        '          VH89_NOTE_COPY(copy_dest[k],copy_source[k]);\n'
        '          vh86_note_store(VH86_VRAM_COPY,copy_dest[k],copy_source[k]);\n'
        '        }\n',
        "observe native gpulib memcpy fast copy immediately before assignment")
    fs=once(fs,
        'extern unsigned int vh88_async_counter(int which);\n',
        'extern unsigned int vh88_async_counter(int which);\n'
        'extern void vh89_copy_reset(void);\n'
        'extern unsigned int vh89_copy_metric(unsigned int which);\n',
        "v89 main-thread copy worker aggregate API")
    fs=once(fs,
        '\tint vh88_async_smoke = 0;\n',
        '\tint vh88_async_smoke = 0;\n'
        '\tint vh89_async_copy_smoke = 0;\n',
        "extra host-only GP0(80) test flag")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh88-async-vram-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t\tvh88_async_smoke = 1;\n'
        '\t\t}\n')
    fs=once(fs,old,old+
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
        '\t\t}\n',
        "v89 opt-in CLI, all earlier gates remain active")
    fs=once(fs,
        '                accepted,completed,stores,same,stores-same);\n'
        '        }\n',
        '                accepted,completed,stores,same,stores-same);\n'
        '        }\n'+PROBE,
        "run v89 post-v88, post-VBlank host async and transition probe")
    for path,s in ((gpu,g),(async_c,ac),(frontend,fs)):
        path.write_text(s)
    return dict(proof,async_copy_GP0_80_worker_write_observer_installed=True,
        post_async_sync_mode_copy_control_installed=True,
        runtime_v89_verified=False,original_retail_MAP02_verified=False,
        physical_ps1_vblank_verified=False,HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
