#!/usr/bin/env python3
"""v102: directory-fd-anchored native private journals, only after pinned GPU."""
from pathlib import Path
from .apply_map02_v101_pcsx_rearmed import apply as apply_v101
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh102_anchored_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char first_path[4096],second_path[4096];
            static const char a[]="VH102 anchored private A\n";
            static const char b[]="VH102 anchored private B\n";
            const unsigned int earlier=vh80_count();
            const unsigned int commits=vh102_anchored_publishes();
            const unsigned int parent_checks=vh102_parent_identity_checks();
            /* v101 just appended proof; refresh its snapshot before checking. */
            (void)vh80_events();
            if(!private_path || strlen(private_path)>3960u ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH102_BASE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 28;
            }
            if(snprintf(first_path,sizeof(first_path),"%s.v102-anchored-a",private_path)<0 ||
               snprintf(second_path,sizeof(second_path),"%s.v102-anchored-b",private_path)<0){
                SysPrintf("VH102_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 28;
            }
            /* openat/linkat/unlinkat use the ORIGINAL dirfd, never a
             * pathname redirected between stage creation and final link.
             * Independent identity reopens and bytes/fsync still required. */
            if(vh82_publish_private(first_path,a,sizeof(a)-1)!=0 ||
               vh82_publish_private(second_path,b,sizeof(b)-1)!=0 ||
               vh102_anchored_publishes()!=commits+2u ||
               vh102_parent_identity_checks()<parent_checks+12u ||
               vh101_verify_private_commit(first_path,a,sizeof(a)-1)!=0 ||
               vh101_verify_private_commit(second_path,b,sizeof(b)-1)!=0 ||
               vh82_publish_private(first_path,b,sizeof(b)-1)==0 ||
               vh102_anchored_publishes()!=commits+2u ||
               vh99_private_state(first_path)!=1 ||
               vh99_private_state(second_path)!=1){
                SysPrintf("VH102_IDENTITY_OR_COMMIT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 28;
            }
            /* Leave original v82 final full private event path untouched. */
            if(remove(first_path)!=0 || remove(second_path)!=0 ||
               vh80_dropped()!=0){
                SysPrintf("VH102_PRIVATE_MARKER_CLEANUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 28;
            }
            vh80_record(VH102_ANCHORED_COMMITS,2u,0,0);
            vh80_record(VH102_PARENT_MATCHES,12u,0,0);
            vh80_record(VH102_REDIRECT_REFUSED,1u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=earlier+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH102_FINAL_SEQUENCE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 28;
            }
            SysPrintf("VH102_ANCHORED_PASS commits=2 parent_checks_min=12 duplicate_refused=1 prior_events=%u final_events=%u drops=0\n",
                earlier,vh80_count());
        }
'''

def apply(root:Path):
    previous=apply_v101(root)
    target=root.resolve()/"frontend/main.c"
    fs=target.read_text()
    fs=once(fs,
        '\tint vh101_reopened_smoke = 0;\n',
        '\tint vh101_reopened_smoke = 0;\n'
        '\tint vh102_anchored_smoke = 0;\n',
        "v102 opt-in directory anchored callback")
    old=(
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
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh102-anchored-directory-smoke")) {\n'
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
        '\t\t\tvh102_anchored_smoke = 1;\n'
        '\t\t}\n',
        "v102 requires every preceding original pinned renderer diagnostic")
    fs=once(fs,
        '            SysPrintf("VH101_REOPEN_PASS verified=4 parent_resync=4 wrong_bytes_refused=1 previous_events=%u final_events=%u drops=0\\n",\n'
        '                old_events,vh80_count());\n'
        '        }\n',
        '            SysPrintf("VH101_REOPEN_PASS verified=4 parent_resync=4 wrong_bytes_refused=1 previous_events=%u final_events=%u drops=0\\n",\n'
        '                old_events,vh80_count());\n'
        '        }\n'+PROBE,
        "native v102 anchored host controls after v101 and before final private export")
    target.write_text(fs)
    return dict(previous,
        native_private_stage_openat_anchored=True,
        native_private_linkat_same_dirfd=True,
        native_private_cleanup_unlinkat_anchored=True,
        parent_directory_identity_revalidated=True,
        native_parent_redirect_faults_isolated_C_only=True,
        v102_runtime_verified=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
