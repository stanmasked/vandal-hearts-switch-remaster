#!/usr/bin/env python3
"""Pinned v96 GPU journal: two-lane capacity readback and fail-closed C tests.

Host-only opt-in AFTER the native four-emulator-VBlank MIPS oracle,
v86-v95 Unai/GPU-worker tests and GPUfreeze. No real retail MAP02.
"""
from pathlib import Path
from .apply_map02_v95_pcsx_rearmed import apply as apply_v95
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh96_boundary_smoke){
            /* v95 has finished the whole native worker/Unai run. The
             * detailed evidence is nearly full; this probe does not
             * deliberately overflow the LIVE private journal because
             * doing so would correctly make its publication impossible.
             * Exact-capacity rejection lives in native isolated tests. */
            static char before_json[524288],after_json[524288];
            const unsigned int before_count=vh80_count();
            const unsigned int details=vh80_detailed_count();
            const unsigned int aggregates=vh80_aggregate_count();
            if(before_count<=VH80_CAPACITY_DETAIL ||
               !details || details>=VH80_CAPACITY_DETAIL ||
               aggregates+3u>=VH80_CAPACITY_AGGREGATE ||
               vh80_dropped()!=0 ||
               vh94_snapshot_check()!=0){
                SysPrintf("VH96_BASELINE_CAPACITY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            const unsigned int detail_remaining=VH80_CAPACITY_DETAIL-details;
            const unsigned int agg_remaining=VH80_CAPACITY_AGGREGATE-aggregates-3u;
            if(detail_remaining>256u || !agg_remaining){
                SysPrintf("VH96_NOT_NEAR_BOUNDARY_REFUSED detail=%u aggregate=%u\n",
                    detail_remaining,agg_remaining);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            const int initial_bytes=vh81_format_jsonl(before_json,sizeof(before_json));
            if(initial_bytes<=0){
                SysPrintf("VH96_BASE_SERIALIZE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            const unsigned int merged_before=vh94_merge_runs();
            vh80_record(VH96_DETAIL_REMAINING,detail_remaining,0,0);
            vh80_record(VH96_AGG_REMAINING,agg_remaining,0,0);
            vh80_record(VH96_SERIALIZED_TWICE,2u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=before_count+3u ||
               vh80_detailed_count()!=details ||
               vh80_aggregate_count()!=aggregates+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH96_APPEND_INVALIDATION_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            const vh80_event *joined=vh80_events();
            if(vh94_merge_runs()!=merged_before+1u ||
               vh94_snapshot_check()!=0 ||
               joined[before_count].sequence!=before_count+1u ||
               joined[before_count].kind!=VH96_DETAIL_REMAINING ||
               joined[before_count].value!=detail_remaining ||
               joined[before_count+1u].kind!=VH96_AGG_REMAINING ||
               joined[before_count+1u].value!=agg_remaining ||
               joined[before_count+2u].kind!=VH96_SERIALIZED_TWICE ||
               joined[before_count+2u].value!=2u){
                SysPrintf("VH96_REBUILD_CAPACITY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            const int new_bytes=vh81_format_jsonl(after_json,sizeof(after_json));
            if(new_bytes<=initial_bytes ||
               memcmp(after_json,before_json,(size_t)initial_bytes)!=0){
                SysPrintf("VH96_OLD_BYTES_MUTATED_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            const int replay=vh81_format_jsonl(before_json,sizeof(before_json));
            if(replay!=new_bytes ||
               memcmp(after_json,before_json,(size_t)new_bytes)!=0 ||
               vh94_merge_runs()!=merged_before+1u ||
               vh94_snapshot_check()!=0){
                SysPrintf("VH96_SERIALIZATION_REPLAY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 22;
            }
            SysPrintf("VH96_BOUNDARY_PASS detail_remaining=%u aggregate_remaining=%u serializations=2 prior_events=%u final_events=%u drops=0\n",
                detail_remaining,agg_remaining,before_count,vh80_count());
        }
'''

def apply(root:Path):
    proof=apply_v95(root)
    frontend=root.resolve()/"frontend/main.c"
    fs=frontend.read_text()
    fs=once(fs,
        '\tint vh95_roundtrip_smoke = 0;\n',
        '\tint vh95_roundtrip_smoke = 0;\n'
        '\tint vh96_boundary_smoke = 0;\n',
        "v96 host-only lane-boundary capacity flag")
    old=(
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
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh96-boundary-smoke")) {\n'
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
        '\t\t\tvh96_boundary_smoke = 1;\n'
        '\t\t}\n',
        "v96 explicitly retains every original MIPS and native GPU predecessor")
    fs=once(fs,
        '                start,vh80_count());\n'
        '        }\n',
        '                start,vh80_count());\n'
        '        }\n'+PROBE,
        "v96 capacity checkpoint must precede single final v82 exclusive publish")
    frontend.write_text(fs)
    return dict(proof,
        v96_near_boundary_live_pinned_GPU_journal=True,
        v96_byte_identical_native_serializer_replays=2,
        both_exact_capacity_overflow_refusals_in_isolated_C_tests=True,
        runtime_v96_verified=False,
        retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
