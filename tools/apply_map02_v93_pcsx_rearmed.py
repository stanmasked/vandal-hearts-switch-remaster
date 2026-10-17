#!/usr/bin/env python3
"""v93 genuine two-lane bounded native GPU observer; original events preserved.

Retains all v80-v92 real pinned emulator callsites. A tiny post-pressure
synthetic raster scene deliberately pushes COMBINED event count past the
old 4096-event limit without exceeding either protected physical lane.
"""
from pathlib import Path
from .apply_map02_v92_pcsx_rearmed import apply as apply_v92
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh93_split_smoke) {
            /* Only after genuine signed 4-emulator-VBlank MIPS oracle
             * and all v86-v92 host GPU control assertions. No raw game
             * commands or pixel samples get published publicly. */
            GPUFreeze_t state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&state,&vram)!=1 || !vram ||
               vh80_dropped()!=0){
                SysPrintf("VH93_BASELINE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 19;
            }
            /* Fixed 12 synthetic, untextured 16x16 GP0 sprites.
             * Genuine Unai renderer handlers produce detailed v83-v85
             * observations; previous aggregate v86-v92 counters are
             * physically protected in a separate 256-event lane. */
            uint32_t warm[12*3];
            for(unsigned int i=0;i<12;i++){
                warm[3*i]=0x600000ffu;
                warm[3*i+1]=(320u<<16)|520u;
                warm[3*i+2]=(16u<<16)|16u;
            }
            GPU_writeDataMem(warm,12*3);
            if(GPU_freeze(1,&state,&vram)!=1 || !vram){
                SysPrintf("VH93_FINAL_GPUFREEZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 19;
            }
            const unsigned int detail=vh80_detailed_count();
            const unsigned int aggregate=vh80_aggregate_count()+3u;
            const unsigned int total=detail+aggregate;
            if(detail==0 || detail>VH80_CAPACITY_DETAIL ||
               aggregate<3u || aggregate>VH80_CAPACITY_AGGREGATE ||
               total<=VH80_CAPACITY_DETAIL ||
               total>VH80_TOTAL_CAPACITY || vh80_dropped()!=0){
                SysPrintf("VH93_SEGMENT_CAPACITY_REFUSED detail=%u aggregate=%u total=%u drops=%u\n",
                    detail,aggregate,total,vh80_dropped());
                ClosePlugins();SysClose();menu_finish();plat_finish();return 19;
            }
            vh80_record(VH93_DETAIL_COUNT,detail,0,0);
            vh80_record(VH93_AGG_COUNT,aggregate,0,0);
            vh80_record(VH93_TOTAL_COUNT,total,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=total ||
               vh80_detailed_count()!=detail ||
               vh80_aggregate_count()!=aggregate){
                SysPrintf("VH93_SEGMENT_POST_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 19;
            }
            /* Legacy private exporter gets one byte-exact globally
             * ordered contiguous view, despite physical lane separation. */
            const vh80_event *joined=vh80_events();
            for(unsigned int i=0;i<total;i++)
                if(joined[i].sequence!=i+1u) {
                    SysPrintf("VH93_MERGE_SEQUENCE_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 19;
                }
            SysPrintf("VH93_DUAL_LANE_PASS detailed=%u aggregate=%u total=%u detail_capacity=%u aggregate_capacity=%u drops=0\n",
                detail,aggregate,total,
                (unsigned int)VH80_CAPACITY_DETAIL,
                (unsigned int)VH80_CAPACITY_AGGREGATE);
        }
'''

def apply(root:Path):
    proof=apply_v92(root)
    frontend=root.resolve()/"frontend/main.c"
    fs=frontend.read_text()
    fs=once(fs,
        '\tint vh92_pressure_smoke = 0;\n',
        '\tint vh92_pressure_smoke = 0;\n'
        '\tint vh93_split_smoke = 0;\n',
        "v93 opt-in, do not affect production GPU")
    old=(
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
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh93-dual-lane-smoke")) {\n'
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
        '\t\t\tvh93_split_smoke = 1;\n'
        '\t\t}\n',
        "v93 full real emulator chain strict opt-in")
    fs=once(fs,
        '                worker_stores,sync_stores,worker_same,sync_same);\n'
        '        }\n',
        '                worker_stores,sync_stores,worker_same,sync_same);\n'
        '        }\n'+PROBE,
        "v93 native dual-lane experiment runs only after v92 pressure and before private export")
    frontend.write_text(fs)
    return dict(proof,
        private_detailed_renderer_ring_capacity=4096,
        private_gpu_aggregate_ring_capacity=256,
        original_global_sequence_byte_order_preserved=True,
        v93_runtime_verified=False,
        original_retail_MAP02_verified=False,
        physical_ps1_vblank_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
