#!/usr/bin/env python3
"""Pinned PCSX opt-in genuine async gpulib DMA queue/worker store observation.

Unlike earlier synchronous A0 observers, counts of QUEUED submissions are
distinct from actually executed worker do_vram_line destination stores.
No concurrent mutation of the v80 event ring from a worker thread: atomic
aggregate metrics are appended on the main thread after GPUfreeze sync.
"""
from pathlib import Path
from .apply_map02_v87_pcsx_rearmed import apply as apply_v87
from .apply_map02_v69_pcsx_rearmed import once

ASYNC_DECL=r'''#ifdef VH_MAP02_V66_PCSX_PROBE
/* Genuine worker-to-main aggregate handoff; no ring-buffer worker writes. */
static unsigned int vh88_queue, vh88_started, vh88_finished;
static unsigned int vh88_pixel_stores, vh88_same_stores;
void vh88_async_reset(void) {
    __atomic_store_n(&vh88_queue,0,__ATOMIC_RELAXED);
    __atomic_store_n(&vh88_started,0,__ATOMIC_RELAXED);
    __atomic_store_n(&vh88_finished,0,__ATOMIC_RELAXED);
    __atomic_store_n(&vh88_pixel_stores,0,__ATOMIC_RELAXED);
    __atomic_store_n(&vh88_same_stores,0,__ATOMIC_RELAXED);
}
unsigned int vh88_async_counter(int which) {
    switch(which) {
    case 0:return __atomic_load_n(&vh88_queue,__ATOMIC_SEQ_CST);
    case 1:return __atomic_load_n(&vh88_started,__ATOMIC_SEQ_CST);
    case 2:return __atomic_load_n(&vh88_finished,__ATOMIC_SEQ_CST);
    case 3:return __atomic_load_n(&vh88_pixel_stores,__ATOMIC_SEQ_CST);
    case 4:return __atomic_load_n(&vh88_same_stores,__ATOMIC_SEQ_CST);
    default:return 0;
    }
}
static void vh88_worker_line(uint16_t *vram,int x,int y,
    const uint16_t *src,int n,uint32_t r6) {
    if(!vh84_sampling_enabled())return;
    const uint16_t *dst=VRAM_MEM_XY(vram,x,y);
    unsigned int same=0;
    for(int i=0;i<n;i++) {
        uint16_t old=dst[i],next=src[i];
        if(r6==1)next|=0x8000;
        else if(r6){
            uint16_t mask=(uint16_t)((int16_t)old>>15);
            next=(old&mask)|((uint16_t)(src[i]|(uint16_t)(r6<<15))&~mask);
        }
        same+=(old==next);
    }
    __atomic_fetch_add(&vh88_pixel_stores,(unsigned int)n,__ATOMIC_SEQ_CST);
    __atomic_fetch_add(&vh88_same_stores,same,__ATOMIC_SEQ_CST);
}
#endif
'''

PROBE=r'''
        if(vh88_async_smoke) {
            /* This stage starts AFTER v78 original interpreted MIPS and
             * AFTER all v86/v87 host synchronous controls have passed.
             * All v88 commands are explicit host diagnostic controls.
             * GPUfreeze waits for all actual worker writes to finish. */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH88_BASELINE_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 14;
            }
            for(unsigned int x=0;x<8;x++)
                if(vram[360*1024+700+x]!=0) {
                    SysPrintf("VH88_DEST_NOT_EMPTY_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 14;
                }
            vh88_async_reset();
            pl_rearmed_cbs.thread_rendering=1;
            plugin_call_rearmed_cbs();
            /* Queue enough renderer work that synchronous do_vram_io's
             * idle-and-empty bypass is unlikely to take every A0 upload.
             * 384 tiles = 1536 observer events, below the 4096 cap. */
            uint32_t tiles[384*3];
            for(unsigned int i=0;i<384;i++) {
                tiles[3*i]=0x600000ffu;
                tiles[3*i+1]=(320u<<16)|520u;
                tiles[3*i+2]=(4u<<16)|4u;
            }
            GPU_writeDataMem(tiles,384*3);
            uint32_t upload[7]={
                0xa0000000u,(360u<<16)|700u,(1u<<16)|8u,
                0x001f001fu,0x001f001fu,0x001f001fu,0x001f001fu
            };
            for(unsigned int i=0;i<32;i++)
                GPU_writeDataMem(upload,7);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
                SysPrintf("VH88_ASYNC_FREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 14;
            }
            for(unsigned int x=0;x<8;x++)
                if(vram[360*1024+700+x]!=0x001fu) {
                    SysPrintf("VH88_ASYNC_PIXEL_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 14;
                }
            const unsigned int accepted=vh88_async_counter(0);
            const unsigned int started=vh88_async_counter(1);
            const unsigned int completed=vh88_async_counter(2);
            const unsigned int stores=vh88_async_counter(3);
            const unsigned int same=vh88_async_counter(4);
            if(accepted==0 || accepted>32 || started!=accepted ||
               completed!=accepted || stores!=accepted*8 ||
               same>=stores || same==0 || vh80_dropped()!=0) {
                SysPrintf("VH88_ASYNC_COUNTER_REFUSED queued=%u started=%u finished=%u stores=%u same=%u\n",
                    accepted,started,completed,stores,same);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 14;
            }
            pl_rearmed_cbs.thread_rendering=0;
            plugin_call_rearmed_cbs();
            /* Shutdown can flush residual renderer commands. Record the
             * synchronized aggregates only after that flush, otherwise
             * Unai GP0 handler events could trail the audit suffix. */
            vh80_record(VH88_ASYNC_QUEUED,accepted,0,0);
            vh80_record(VH88_ASYNC_COMPLETED,completed,0,0);
            vh80_record(VH88_ASYNC_STORES,stores,0,0);
            vh80_record(VH88_ASYNC_SAME,same,0,0);
            if(vh80_dropped()!=0){
                SysPrintf("VH88_ASYNC_EVENT_OVERFLOW_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 14;
            }
            SysPrintf("VH88_ASYNC_PASS queued=%u completed=%u stores=%u same=%u changed=%u\n",
                accepted,completed,stores,same,stores-same);
        }
'''

def apply(root:Path):
    proof=apply_v87(root)
    base=root.resolve()
    async_c=base/"plugins/gpulib/gpu_async.c"
    frontend=base/"frontend/main.c"
    code=async_c.read_text()
    fs=frontend.read_text()
    code=once(code, '#include "gpu_async.h"\n',
        '#include "gpu_async.h"\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '#include "../../libpcsxcore/vh80_native_timeline.h"\n'
        '#endif\n',
        "async worker can see opt-in sampling gate")
    code=once(code, 'struct psx_gpu_async\n{\n',
        ASYNC_DECL+'\nstruct psx_gpu_async\n{\n',
        "atomic queued/started/completed/store counters on actual worker thread")
    code=once(code,
        '  slock_unlock(agpu->lock);\n\n  return 1;\n}',
        '  slock_unlock(agpu->lock);\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '  if(vh84_sampling_enabled())__atomic_fetch_add(&vh88_queue,1,__ATOMIC_SEQ_CST);\n'
        '#endif\n'
        '\n  return 1;\n}',
        "only count successfully enqueued async GP0(A0) DMA")
    code=once(code,
        '  renderer_flush_queues();\n\n  pos += sizeof(*cmd) / 4u;\n',
        '  renderer_flush_queues();\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '  if(vh84_sampling_enabled())__atomic_fetch_add(&vh88_started,1,__ATOMIC_SEQ_CST);\n'
        '#endif\n'
        '\n  pos += sizeof(*cmd) / 4u;\n',
        "record worker execution start")
    code=once(code,
        '    do_vram_line(vram, x, y, (uint16_t *)&agpu->cmd_buffer[pos], w, 0, r6);\n',
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '    vh88_worker_line(vram,x,y,(uint16_t *)&agpu->cmd_buffer[pos],w,r6);\n'
        '#endif\n'
        '    do_vram_line(vram, x, y, (uint16_t *)&agpu->cmd_buffer[pos], w, 0, r6);\n',
        "count real worker 16-bit pending stores before native write")
    code=once(code,
        '  renderer_update_caches(x, cmd->y, w, cmd->h, 0);\n  return done;\n}',
        '  renderer_update_caches(x, cmd->y, w, cmd->h, 0);\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '  if(vh84_sampling_enabled())__atomic_fetch_add(&vh88_finished,1,__ATOMIC_SEQ_CST);\n'
        '#endif\n'
        '  return done;\n}',
        "count async DMA completion after original worker writes")
    fs=once(fs, '#include "plugin_lib.h"\n',
        '#include "plugin_lib.h"\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        'extern void vh88_async_reset(void);\n'
        'extern unsigned int vh88_async_counter(int which);\n'
        '#endif\n',
        "frontend only consumes synchronized aggregate snapshot")
    fs=once(fs, '\tint vh87_extended_smoke = 0;\n',
        '\tint vh87_extended_smoke = 0;\n'
        '\tint vh88_async_smoke = 0;\n',
        "v88 signed host-only switch")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh87-gpulib-edge-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t}\n')
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh88-async-vram-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t\tvh86_gpulib_copy_smoke = 1;\n'
        '\t\t\tvh87_extended_smoke = 1;\n'
        '\t\t\tvh88_async_smoke = 1;\n'
        '\t\t}\n',
        "explicit opt-in v88 host async queue")
    fs=once(fs, '                os,oss,ms,mss,ws,wss);\n        }\n',
        '                os,oss,ms,mss,ws,wss);\n        }\n'+PROBE,
        "execute host async probe strictly after v87 controls and VBlank oracle")
    async_c.write_text(code)
    frontend.write_text(fs)
    return dict(proof,observed_async_A0_worker_queued_and_completed_instrumented=True,
        async_worker_counter_snapshot_thread_safe=True,
        runtime_v88_verified=False,
        asynchronous_gpu_vram_copy_proven=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
