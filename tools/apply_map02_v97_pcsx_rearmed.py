#!/usr/bin/env python3
"""v97 native GPU observer reset epoch and stale JSONL memory protection.

The live PCSX probe NEVER resets the original four-VBlank oracle journal.
Destructive resets are proven separately with actual native C code (GCC/Clang).
"""
from pathlib import Path
from .apply_map02_v96_pcsx_rearmed import apply as apply_v96
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh97_scrub_smoke){
            /* v96 full original native observer/GPUfreeze chain is intact.
             * Reset would destroy that evidence, so only inspect its
             * current lifetime and reusable serialization buffers here.
             * Isolated native C tests perform destructive reset cycles. */
            static char serialized[524288],replayed[524288];
            const unsigned int before=vh80_count();
            const unsigned int epoch=vh97_reset_epoch();
            if(!epoch || vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH97_BASELINE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 23;
            }
            memset(serialized,0xa5,sizeof(serialized));
            memset(replayed,0x5a,sizeof(replayed));
            const int len=vh81_format_jsonl(serialized,sizeof(serialized));
            const int second=vh81_format_jsonl(replayed,sizeof(replayed));
            if(len<=0 || second!=len ||
               memcmp(serialized,replayed,(size_t)len)!=0 ||
               vh97_reset_epoch()!=epoch){
                SysPrintf("VH97_REUSE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 23;
            }
            for(unsigned int i=(unsigned int)len;i<sizeof(serialized);i++)
                if(serialized[i]!=0 || replayed[i]!=0){
                    SysPrintf("VH97_STALE_SERIALIZER_TAIL_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 23;
                }
            /* The old v96 journal is still a byte-exact prefix.
             * The committed private exporter remains a single exclusive
             * file publish with no raw trace outside its private dir. */
            vh80_record(VH97_EPOCH,epoch,0,0);
            vh80_record(VH97_SCRUBBED,(unsigned int)sizeof(serialized),0,0);
            vh80_record(VH97_REPLAY,2u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=before+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH97_APPEND_INVALIDATION_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 23;
            }
            const int grown=vh81_format_jsonl(replayed,sizeof(replayed));
            if(grown<=len || memcmp(replayed,serialized,(size_t)len)!=0 ||
               vh94_snapshot_check()!=0 ||
               vh97_reset_epoch()!=epoch){
                SysPrintf("VH97_PREFIX_OR_EPOCH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 23;
            }
            SysPrintf("VH97_REUSE_PASS epoch=%u initial_serializations=2 scrubbed_bytes=%u old_events=%u final_events=%u drops=0\n",
                epoch,(unsigned int)sizeof(serialized),before,vh80_count());
        }
'''

def apply(root:Path):
    proof=apply_v96(root)
    front=root.resolve()/"frontend/main.c"
    fs=front.read_text()
    fs=once(fs,
        '\tint vh96_boundary_smoke = 0;\n',
        '\tint vh96_boundary_smoke = 0;\n'
        '\tint vh97_scrub_smoke = 0;\n',
        "v97 opt-in host-only cache epoch/serialization hygiene probe")
    old=(
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
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh97-reset-scrub-smoke")) {\n'
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
        '\t\t\tvh97_scrub_smoke = 1;\n'
        '\t\t}\n',
        "require all earlier four-emulator-VBlank and actual GP0 controls")
    fs=once(fs,
        '                detail_remaining,agg_remaining,before_count,vh80_count());\n'
        '        }\n',
        '                detail_remaining,agg_remaining,before_count,vh80_count());\n'
        '        }\n'+PROBE,
        "v97 must follow v96 private checkpoint before exclusive v82 publication")
    front.write_text(fs)
    return dict(proof,
        actual_native_reset_erasures_in_isolated_C_tests=True,
        v97_live_emulator_does_not_clear_predecessor_provenance=True,
        reusable_private_JSONL_buffers_zeroed=True,
        raw_previous_game_or_event_bytes_exposed=False,
        runtime_v97_verified=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
