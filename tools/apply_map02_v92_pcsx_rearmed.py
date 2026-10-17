#!/usr/bin/env python3
"""True pinned gpulib async GPU DMA ring pressure vs synchronized fallback.

The test commands are HOST controls after genuine four emulated VBlank
callbacks, never interpreted retail MAP02 or physical PlayStation activity.
No raw GPU command/pixel traces leave private CI files.
"""
from pathlib import Path
from .apply_map02_v91_pcsx_rearmed import apply as apply_v91
from .apply_map02_v69_pcsx_rearmed import once

STATS=r'''
/* Producer-side bounded counters: avoid event-ring writes from GPU worker.
 * The peak tracks genuinely occupied 32-bit words, NOT queue capacity.
 * Idle and insufficient-space are native fallback paths, not failures.
 */
static unsigned int vh92_enabled,vh92_tried,vh92_accepted;
static unsigned int vh92_idle,vh92_full,vh92_peak;
void vh92_pressure_reset(void){
    __atomic_store_n(&vh92_tried,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh92_accepted,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh92_idle,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh92_full,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh92_peak,0,__ATOMIC_SEQ_CST);
    __atomic_store_n(&vh92_enabled,1,__ATOMIC_SEQ_CST);
}
static void vh92_track_depth(unsigned int depth){
    if(!__atomic_load_n(&vh92_enabled,__ATOMIC_RELAXED))return;
    unsigned int prev=__atomic_load_n(&vh92_peak,__ATOMIC_RELAXED);
    while(depth>prev &&
      !__atomic_compare_exchange_n(&vh92_peak,&prev,depth,0,
                                    __ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
}
unsigned int vh92_pressure_metric(unsigned int kind){
    switch(kind){
    case 0:return __atomic_load_n(&vh92_tried,__ATOMIC_SEQ_CST);
    case 1:return __atomic_load_n(&vh92_accepted,__ATOMIC_SEQ_CST);
    case 2:return __atomic_load_n(&vh92_idle,__ATOMIC_SEQ_CST);
    case 3:return __atomic_load_n(&vh92_full,__ATOMIC_SEQ_CST);
    case 4:return __atomic_load_n(&vh92_peak,__ATOMIC_SEQ_CST);
    default:return 0;
    }
}
'''
PENDING=r'''
#ifdef VH_MAP02_V66_PCSX_PROBE
unsigned int vh92_pending_words(void){
    struct psx_gpu_async *agpu=gpu.async;
    if(!agpu)return 0xffffffffu; /* thread must still exist at snapshot */
    return agpu->pos_added-RDPOS(agpu->pos_used);
}
#endif
'''

PROBE=r'''
        if(vh92_pressure_smoke){
            /* This only executes after the v78 MIPS oracle, v86 through
             * v91 host-control gates, and four emulator VBlank edges.
             * A0 size=256x32 => exactly 4096 32-bit DMA payload words.
             * 16 host submissions => 131072 logical 16-bit assignments.
             */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                SysPrintf("VH92_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 18;
            }
            for(unsigned int y=400;y<432;y++)
                for(unsigned int x=384;x<640;x++)
                    if(vram[y*1024+x]){
                        SysPrintf("VH92_VRAM_NOT_EMPTY_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 18;
                    }
            pl_rearmed_cbs.thread_rendering=1;
            plugin_call_rearmed_cbs();
            GPU_writeData(0xe6000000u);
            /* Tiny fixed raster warmup, no unbounded per-command journal:
             * the previous v91 baseline is around 3940/4096 events.
             * 8 primitives retain headroom in the bounded native ring.
             */
            uint32_t warm[8*3];
            for(unsigned int i=0;i<8;i++){
                warm[3*i]=0x600000ffu;
                warm[3*i+1]=(320u<<16)|520u;
                warm[3*i+2]=(16u<<16)|16u;
            }
            GPU_writeDataMem(warm,8*3);
            vh88_async_reset();
            vh86_reset();
            vh92_pressure_reset();
            uint32_t upload[4099];
            upload[0]=0xa0000000u;
            upload[1]=(400u<<16)|384u;
            upload[2]=(32u<<16)|256u;
            for(unsigned int i=3;i<4099;i++)
                upload[i]=0x03e003e0u;
            for(unsigned int i=0;i<16;i++)
                GPU_writeDataMem(upload,4099);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                SysPrintf("VH92_PRESSURE_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 18;
            }
            for(unsigned int y=400;y<432;y++)
                for(unsigned int x=384;x<640;x++)
                    if(vram[y*1024+x]!=0x03e0u){
                        SysPrintf("VH92_POST_SYNC_VRAM_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 18;
                    }
            const unsigned int tried=vh92_pressure_metric(0);
            const unsigned int accepted=vh92_pressure_metric(1);
            const unsigned int idle=vh92_pressure_metric(2);
            const unsigned int full=vh92_pressure_metric(3);
            const unsigned int peak=vh92_pressure_metric(4);
            const unsigned int pending=vh92_pending_words();
            const unsigned int completed=vh88_async_counter(2);
            const unsigned int worker_stores=vh88_async_counter(3);
            const unsigned int worker_same=vh88_async_counter(4);
            const unsigned int sync_stores=vh86_store_count(VH86_A0_UPLOAD);
            const unsigned int sync_same=vh86_same_store_count(VH86_A0_UPLOAD);
            if(tried!=16 || !accepted || accepted>16 ||
               idle+full+accepted!=tried ||
               peak<4099 || peak>32768 ||
               pending!=0 || completed!=accepted ||
               worker_stores!=8192u*accepted ||
               sync_stores!=8192u*(16u-accepted) ||
               worker_same>worker_stores || sync_same>sync_stores ||
               worker_same+sync_same!=8192u*15u ||
               vh86_write_overflow() || vh80_dropped()!=0){
                SysPrintf("VH92_PRESSURE_REFUSED tried=%u accepted=%u idle=%u full=%u peak=%u pending=%u completed=%u worker=%u sync=%u same=%u+%u\n",
                    tried,accepted,idle,full,peak,pending,completed,
                    worker_stores,sync_stores,worker_same,sync_same);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 18;
            }
            pl_rearmed_cbs.thread_rendering=0;
            plugin_call_rearmed_cbs();
            /* Metrics are now an immutable post-sync snapshot; the
             * GPU worker has stopped before ANY bounded journal writes. */
            vh80_record(VH92_TRIED,tried,0,0);
            vh80_record(VH92_ACCEPTED,accepted,0,0);
            vh80_record(VH92_IDLE_FALLBACK,idle,0,0);
            vh80_record(VH92_FULL_FALLBACK,full,0,0);
            vh80_record(VH92_PEAK_WORDS,peak,0,0);
            vh80_record(VH92_WORKER_DONE,completed,0,0);
            vh80_record(VH92_WORKER_STORES,worker_stores,0,0);
            vh80_record(VH92_SYNC_STORES,sync_stores,0,0);
            vh80_record(VH92_PENDING,pending,0,0);
            vh80_record(VH92_WORKER_SAME,worker_same,0,0);
            vh80_record(VH92_SYNC_SAME,sync_same,0,0);
            if(vh80_dropped()!=0){
                SysPrintf("VH92_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 18;
            }
            SysPrintf("VH92_PRESSURE_PASS attempts=%u accepted=%u idle=%u full=%u peak_words=%u pending=%u worker_done=%u worker_stores=%u sync_stores=%u worker_same=%u sync_same=%u\n",
                tried,accepted,idle,full,peak,pending,completed,
                worker_stores,sync_stores,worker_same,sync_same);
        }
'''

def apply(root:Path):
    proof=apply_v91(root)
    base=root.resolve()
    async_c=base/"plugins/gpulib/gpu_async.c"
    front=base/"frontend/main.c"
    src=async_c.read_text()
    fs=front.read_text()
    src=once(src,
        'static unsigned int vh88_queue, vh88_started, vh88_finished;',
        STATS+'\nstatic unsigned int vh88_queue, vh88_started, vh88_finished;',
        "install bounded producer-side actual DMA ring diagnostics")
    src=once(src,
        '// cmd_* must be at least 3 words long\n',
        PENDING+'\n// cmd_* must be at least 3 words long\n',
        "read genuine pinned GPU queue residual after freeze")
    src=once(src,
        '  used = agpu->pos_added - RDPOS(agpu->pos_used);\n',
        '  used = agpu->pos_added - RDPOS(agpu->pos_used);\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '  if(__atomic_load_n(&vh92_enabled,__ATOMIC_SEQ_CST)){\n'
        '    __atomic_fetch_add(&vh92_tried,1,__ATOMIC_SEQ_CST);\n'
        '    vh92_track_depth(used);\n'
        '  }\n'
        '#endif\n',
        "measure each genuine A0 asynchronous admission attempt")
    src=once(src,
        '  if (RDPOS(agpu->idle) && used == 0)\n'
        '    return 0;\n',
        '  if (RDPOS(agpu->idle) && used == 0){\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '    if(__atomic_load_n(&vh92_enabled,__ATOMIC_SEQ_CST))\n'
        '      __atomic_fetch_add(&vh92_idle,1,__ATOMIC_SEQ_CST);\n'
        '#endif\n'
        '    return 0;\n'
        '  }\n',
        "distinguish ordinary idle bypass to synchronous A0")
    src=once(src,
        '    agpu_log(gpu, "agpu: dma: used %d\\n", used);\n'
        '    return 0;\n',
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '    if(__atomic_load_n(&vh92_enabled,__ATOMIC_SEQ_CST))\n'
        '      __atomic_fetch_add(&vh92_full,1,__ATOMIC_SEQ_CST);\n'
        '#endif\n'
        '    agpu_log(gpu, "agpu: dma: used %d\\n", used);\n'
        '    return 0;\n',
        "distinguish actual queue-space synchronous bypass")
    src=once(src,
        '  agpu->pos_added = pos_added;\n'
        '  run_thread_nolock(agpu);\n',
        '  agpu->pos_added = pos_added;\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '  if(__atomic_load_n(&vh92_enabled,__ATOMIC_SEQ_CST)){\n'
        '    __atomic_fetch_add(&vh92_accepted,1,__ATOMIC_SEQ_CST);\n'
        '    vh92_track_depth(pos_added-RDPOS(agpu->pos_used));\n'
        '  }\n'
        '#endif\n'
        '  run_thread_nolock(agpu);\n',
        "record actual successful worker queue commit/peak occupancy")
    fs=once(fs,
        'extern unsigned int vh90_stat(unsigned int which);\n',
        'extern unsigned int vh90_stat(unsigned int which);\n'
        'extern void vh92_pressure_reset(void);\n'
        'extern unsigned int vh92_pressure_metric(unsigned int which);\n'
        'extern unsigned int vh92_pending_words(void);\n',
        "frontend accesses only bounded native queue aggregates")
    fs=once(fs,
        '\tint vh91_cycles_smoke = 0;\n',
        '\tint vh91_cycles_smoke = 0;\n'
        '\tint vh92_pressure_smoke = 0;\n',
        "v92 opt-in host queue diagnostic switch")
    old=(
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
        '\t\t}\n')
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh92-async-queue-pressure")) {\n'
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
        '\t\t\tvh92_pressure_smoke = 1;\n'
        '\t\t}\n',
        "v92 CLI explicitly retains all earlier verification gates")
    fs=once(fs,
        '            SysPrintf("VH91_CYCLES_PASS rounds=2 async_copies=4 sync_copies=4 cross_round_retained=1\\n");\n'
        '        }\n',
        '            SysPrintf("VH91_CYCLES_PASS rounds=2 async_copies=4 sync_copies=4 cross_round_retained=1\\n");\n'
        '        }\n'+PROBE,
        "run bounded producer queue pressure after both v91 complete handoffs")
    async_c.write_text(src)
    front.write_text(fs)
    return dict(proof,
        measured_actual_gpu_async_try_dma_queue_occupancy=True,
        measured_native_idle_vs_full_synchronous_fallback=True,
        verified_all_worker_and_sync_a0_destination_assignments=True,
        queue_overflow_or_hardware_timing_inferred=False,
        v92_runtime_verified=False,
        original_retail_MAP02_verified=False,
        physical_ps1_vblank_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
