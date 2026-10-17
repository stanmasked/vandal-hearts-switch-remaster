#!/usr/bin/env python3
"""v94 pin: O(1) repeat reads of native dual-lane GPU journal, strict seal.

No retail MAP02 data, no HD replacement. Runs only after all v78, v80-v93
emulator/MIPS and host control probes and all 4 native emulator VBlanks.
"""
from pathlib import Path
from .apply_map02_v93_pcsx_rearmed import apply as apply_v93
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh94_cached_snapshot_smoke) {
            /* v93 already synchronized real GPU and verified the original
             * global sequence across both bounded lanes. No worker writes
             * happen while testing this cache. */
            const unsigned int before=vh80_count();
            if(before<=VH80_CAPACITY_DETAIL || vh80_dropped()!=0 ||
               vh94_snapshot_check()!=0){
                SysPrintf("VH94_BASE_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
            }
            const vh80_event *stable=vh80_events();
            const unsigned int first_merges=vh94_merge_runs();
            const unsigned int first_hits=vh94_cache_hits();
            const unsigned int first_verified=vh94_verify_runs();
            for(unsigned int i=0;i<128;i++){
                if(vh80_events()!=stable || vh94_snapshot_check()!=0 ||
                   vh80_count()!=before){
                    SysPrintf("VH94_REPEATED_READ_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
                }
            }
            if(vh94_merge_runs()!=first_merges ||
               vh94_cache_hits()-first_hits!=128u ||
               vh94_verify_runs()-first_verified!=128u){
                SysPrintf("VH94_CACHE_COUNTS_REFUSED merges=%u hits=%u verifications=%u\n",
                    vh94_merge_runs()-first_merges,
                    vh94_cache_hits()-first_hits,
                    vh94_verify_runs()-first_verified);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
            }
            /* Successful v80 append invalidates the sealed view.
             * Next read must do exactly one fresh O(n) merge. */
            vh80_record(VH94_CACHED_READS,128u,0,0);
            if(vh80_dropped()!=0 || vh94_snapshot_check()==0){
                SysPrintf("VH94_STALE_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
            }
            const vh80_event *rebuilt=vh80_events();
            if(rebuilt!=stable || vh94_merge_runs()!=first_merges+1u ||
               vh94_snapshot_check()!=0 ||
               rebuilt[before].sequence!=before+1u ||
               rebuilt[before].kind!=VH94_CACHED_READS ||
               rebuilt[before].value!=128u){
                SysPrintf("VH94_REBUILD_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
            }
            vh80_record(VH94_INVALIDATED,1u,0,0);
            vh80_record(VH94_VERIFIED_READS,128u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=before+3u ||
               vh80_events()!=stable || vh94_snapshot_check()!=0){
                SysPrintf("VH94_FINAL_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
            }
            const vh80_event *final=vh80_events();
            for(unsigned int i=0;i<vh80_count();i++)
                if(final[i].sequence!=i+1u){
                    SysPrintf("VH94_FINAL_SEQUENCE_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 20;
                }
            SysPrintf("VH94_SNAPSHOT_PASS cached_reads=128 verified_reads=128 invalidated=1 old_events=%u final_events=%u drops=0\n",
                before,vh80_count());
        }
'''

def apply(root:Path):
    proof=apply_v93(root)
    front=root.resolve()/"frontend/main.c"
    fs=front.read_text()
    fs=once(fs,
        '\tint vh93_split_smoke = 0;\n',
        '\tint vh93_split_smoke = 0;\n'
        '\tint vh94_cached_snapshot_smoke = 0;\n',
        "explicit opt-in v94 snapshot cache")
    old=(
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
        '\t\t}\n'
    )
    fs=once(fs,old,old+
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
        '\t\t}\n',
        "v94 only after all authentic pinned predecessor paths")
    fs=once(fs,
        '                (unsigned int)VH80_CAPACITY_AGGREGATE);\n'
        '        }\n',
        '                (unsigned int)VH80_CAPACITY_AGGREGATE);\n'
        '        }\n'+PROBE,
        "native cached-merge proof strictly after v93 and before private export")
    front.write_text(fs)
    return dict(proof,
        v94_snapshot_cache_and_integrity_probe_installed=True,
        repeated_reads_without_event_append_constant_time=True,
        original_emulator_four_vblank_oracle_preserved=True,
        pinned_runtime_v94_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
