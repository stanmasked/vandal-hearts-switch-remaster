#!/usr/bin/env python3
"""v101 pinned software-GPU private file post-commit reopen and fsync check.

All MIPS/VBlank and GPU worker samples remain unchanged. Only native
post-GPUfreeze synthetic private marker files are inspected here.
"""
from pathlib import Path
from .apply_map02_v100_pcsx_rearmed import apply as apply_v100
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh101_reopened_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char p1[4096],p2[4096];
            static const char first[]="VH101 committed private generation A\n";
            static const char second[]="VH101 committed private generation B\n";
            static const char mismatched[]="VH101 unrelated data and provenance\n";
            const unsigned int old_events=vh80_count();
            const unsigned int old_commits=vh101_verified_commits();
            const unsigned int old_syncs=vh101_reopened_directory_syncs();
            /* The last v100 metrics were appended after its snapshot. */
            (void)vh80_events();
            if(!private_path || strlen(private_path)>3970u ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH101_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 27;
            }
            if(snprintf(p1,sizeof(p1),"%s.v101-reopen-a",private_path)<0 ||
               snprintf(p2,sizeof(p2),"%s.v101-reopen-b",private_path)<0){
                SysPrintf("VH101_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 27;
            }
            /* The original publisher verifies final contents and both
             * successfully returned file+parent fsyncs AFTER reopening. */
            if(vh82_publish_private(p1,first,sizeof(first)-1)!=0 ||
               vh82_publish_private(p2,second,sizeof(second)-1)!=0 ||
               vh101_verified_commits()!=old_commits+2u ||
               vh101_reopened_directory_syncs()!=old_syncs+2u ||
               vh101_verify_private_commit(p1,first,sizeof(first)-1)!=0 ||
               vh101_verify_private_commit(p2,second,sizeof(second)-1)!=0 ||
               vh101_verified_commits()!=old_commits+4u ||
               vh101_reopened_directory_syncs()!=old_syncs+4u ||
               vh101_verify_private_commit(p1,mismatched,sizeof(mismatched)-1)==0 ||
               vh101_verified_commits()!=old_commits+4u ||
               vh101_reopened_directory_syncs()!=old_syncs+4u ||
               vh82_publish_private(p1,second,sizeof(second)-1)==0){
                SysPrintf("VH101_REOPEN_VERIFY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 27;
            }
            /* The verifier is purely read-only; no modified old bytes,
             * no unsafe temporary stages and no reused final pathname. */
            if(vh99_private_state(p1)!=1 || vh99_private_state(p2)!=1 ||
               remove(p1)!=0 || remove(p2)!=0 || vh80_dropped()!=0){
                SysPrintf("VH101_READ_ONLY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 27;
            }
            vh80_record(VH101_REOPEN_VERIFIED,4u,0,0);
            vh80_record(VH101_PARENT_RESYNC,4u,0,0);
            vh80_record(VH101_BAD_REOPEN_REFUSED,1u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=old_events+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH101_FINAL_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 27;
            }
            SysPrintf("VH101_REOPEN_PASS verified=4 parent_resync=4 wrong_bytes_refused=1 previous_events=%u final_events=%u drops=0\n",
                old_events,vh80_count());
        }
'''

def apply(root:Path):
    proof=apply_v100(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,
        '\tint vh100_durability_smoke = 0;\n',
        '\tint vh100_durability_smoke = 0;\n'
        '\tint vh101_reopened_smoke = 0;\n',
        "new explicit pinned reopen verification probe")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh100-directory-fsync-smoke")) {\n'
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
        '\t\t\tvh98_recovery_smoke = 1;\n'
        '\t\t\tvh99_interruption_smoke = 1;\n'
        '\t\t\tvh100_durability_smoke = 1;\n'
        '\t\t}\n'
    )
    src=once(src,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh101-reopened-verify-smoke")) {\n'
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
        '\t\t\tvh98_recovery_smoke = 1;\n'
        '\t\t\tvh99_interruption_smoke = 1;\n'
        '\t\t\tvh100_durability_smoke = 1;\n'
        '\t\t\tvh101_reopened_smoke = 1;\n'
        '\t\t}\n',
        "retain complete original emulator and native Unai chain")
    src=once(src,
        '            SysPrintf("VH100_DURABILITY_PASS post_link_dirsync=2 post_unlink_dirsync=2 duplicate_refused=1 previous_events=%u final_events=%u drops=0\\n",\n'
        '                events_before,vh80_count());\n'
        '        }\n',
        '            SysPrintf("VH100_DURABILITY_PASS post_link_dirsync=2 post_unlink_dirsync=2 duplicate_refused=1 previous_events=%u final_events=%u drops=0\\n",\n'
        '                events_before,vh80_count());\n'
        '        }\n'+PROBE,
        "place v101 native read-only postcommit checks after v100 before final private export")
    frontend.write_text(src)
    return dict(proof,
        original_vblank_oracle_preserved=True,
        every_native_private_commit_reopened=True,
        file_and_parent_resync_on_verified_final=True,
        never_auto_reuse_ambiguous_filename=True,
        real_power_loss_simulated=False,
        runtime_v101_verified=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
