#!/usr/bin/env python3
"""v95: actual pinned PCSX repeated native append/merge/private serialization.

Only host-only diagnostic events AFTER v94 and native GPUfreeze, never
retail MAP02 words or original PlayStation image evidence.
"""
from pathlib import Path
from .apply_map02_v94_pcsx_rearmed import apply as apply_v94
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh95_roundtrip_smoke){
            /* All 4 authentic emulator VBlank and earlier host oracle,
             * native renderer / copy worker controls have already passed.
             * These two buffers contain PRIVATE bytes in process memory
             * only, and are never uploaded as CI artifacts. */
            static char previous_json[524288];
            static char next_json[524288];
            unsigned int start=vh80_count();
            const vh80_event *stable=vh80_events();
            if(start<=VH80_CAPACITY_DETAIL || vh80_dropped() ||
               vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+13u>VH80_CAPACITY_AGGREGATE ||
               start+13u>VH80_TOTAL_CAPACITY){
                SysPrintf("VH95_BASELINE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
            }
            int old_bytes=vh81_format_jsonl(previous_json,sizeof(previous_json));
            if(old_bytes<=0){
                SysPrintf("VH95_INITIAL_SERIALIZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
            }
            const unsigned int merges_base=vh94_merge_runs();
            for(unsigned int round=0;round<8;round++){
                const unsigned int count=vh80_count();
                const unsigned int merges=vh94_merge_runs();
                vh80_record(VH95_ROUND_1+round,round+1u,0,0);
                if(vh80_dropped()!=0 || vh80_count()!=count+1u ||
                   vh94_snapshot_check()==0){
                    SysPrintf("VH95_INVALIDATION_REFUSED round=%u\n",round+1);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
                }
                const vh80_event *joined=vh80_events();
                if(joined!=stable || vh94_snapshot_check()!=0 ||
                   vh94_merge_runs()!=merges+1u ||
                   joined[count].sequence!=count+1u ||
                   joined[count].kind!=VH95_ROUND_1+round ||
                   joined[count].value!=round+1u ||
                   vh80_events()!=stable ||
                   vh94_merge_runs()!=merges+1u){
                    SysPrintf("VH95_REMERGE_REFUSED round=%u\n",round+1);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
                }
                int new_bytes=vh81_format_jsonl(next_json,sizeof(next_json));
                if(new_bytes<=old_bytes ||
                   memcmp(next_json,previous_json,(size_t)old_bytes)!=0){
                    SysPrintf("VH95_PRIVATE_PREFIX_REFUSED round=%u\n",round+1);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
                }
                /* Independent reserialization cannot change a byte; the
                 * first old_bytes were previously verified privately. */
                int repeated=vh81_format_jsonl(previous_json,sizeof(previous_json));
                if(repeated!=new_bytes ||
                   memcmp(previous_json,next_json,(size_t)new_bytes)!=0){
                    SysPrintf("VH95_PRIVATE_REPLAY_REFUSED round=%u\n",round+1);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
                }
                old_bytes=new_bytes;
            }
            if(vh94_merge_runs()!=merges_base+8u || vh80_count()!=start+8u ||
               vh80_dropped()!=0){
                SysPrintf("VH95_REBUILD_TOTAL_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
            }
            vh80_record(VH95_PREFIXES,8u,0,0);
            vh80_record(VH95_EXPORTS,16u,0,0);
            vh80_record(VH95_MERGES,8u,0,0);
            vh80_record(VH95_STALE_REFUSALS,8u,0,0);
            vh80_record(VH95_STABLE_READS,8u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=start+13u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH95_FINAL_INVALIDATION_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
            }
            const vh80_event *final_view=vh80_events();
            if(final_view!=stable || vh94_snapshot_check()!=0){
                SysPrintf("VH95_FINAL_REBUILD_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
            }
            for(unsigned int i=0;i<vh80_count();i++)
                if(final_view[i].sequence!=i+1u){
                    SysPrintf("VH95_FINAL_ORDER_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 21;
                }
            /* v82 will perform the *single* exclusive real private file
             * publish after this readback, with 0600 and byte verification. */
            SysPrintf("VH95_ROUNDTRIP_PASS rounds=8 stable_reads=8 checked_prefixes=8 memory_exports=16 rebuilds=8 stale_refused=8 previous_events=%u final_events=%u drops=0\n",
                start,vh80_count());
        }
'''

def apply(root:Path):
    proof=apply_v94(root)
    front=root.resolve()/"frontend/main.c"
    fs=front.read_text()
    fs=once(fs,
        '\tint vh94_cached_snapshot_smoke = 0;\n',
        '\tint vh94_cached_snapshot_smoke = 0;\n'
        '\tint vh95_roundtrip_smoke = 0;\n',
        "v95 explicit snapshot append/replay opt-in")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh94-cached-journal-smoke")) {\n'
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
        '\t\t\tvh94_cached_snapshot_smoke = 1;\n'
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh95-snapshot-roundtrip-smoke")) {\n'
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
        '\t\t\tvh94_cached_snapshot_smoke = 1;\n'
        '\t\t\tvh95_roundtrip_smoke = 1;\n'
        '\t\t}\n',
        "v95 CLI requires all earlier original and host GPU controls")
    fs=once(fs,
        '                before,vh80_count());\n'
        '        }\n',
        '                before,vh80_count());\n'
        '        }\n'+PROBE,
        "run repeated private memory serializations after v94 and before exclusive v82 publication")
    front.write_text(fs)
    return dict(proof,
        v95_repeated_native_snapshots=8,
        v95_byte_exact_in_memory_jsonl_exports=16,
        v95_file_publish_single_and_exclusive=True,
        native_worker_drained_before_snapshots=True,
        pinned_runtime_v95_verified=False,
        original_retail_MAP02_verified=False,
        physical_ps1_vblank_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
