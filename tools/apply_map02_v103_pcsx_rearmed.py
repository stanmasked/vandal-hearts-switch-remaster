#!/usr/bin/env python3
"""v103: original pinned PCSX private file path safety and inode verification."""
from pathlib import Path
from .apply_map02_v102_pcsx_rearmed import apply as apply_v102
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh103_inode_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char a_path[4096],b_path[4096],link_path[4096],redirected[4096];
            static const char first[]="VH103 safe parent and inode A\n";
            static const char second[]="VH103 safe parent and inode B\n";
            const unsigned int old_events=vh80_count();
            const unsigned int walked=vh103_safe_parent_walks();
            const unsigned int verified=vh101_verified_commits();
            (void)vh80_events();
            if(!private_path || strlen(private_path)>3940u ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH103_BASE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 29;
            }
            if(snprintf(a_path,sizeof(a_path),"%s.v103-a",private_path)<0 ||
               snprintf(b_path,sizeof(b_path),"%s.v103-b",private_path)<0 ||
               snprintf(link_path,sizeof(link_path),"%s.v103-parent-link",private_path)<0 ||
               snprintf(redirected,sizeof(redirected),"%s.v103-parent-link/forbidden",private_path)<0){
                SysPrintf("VH103_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 29;
            }
            if(vh82_publish_private(a_path,first,sizeof(first)-1)!=0 ||
               vh82_publish_private(b_path,second,sizeof(second)-1)!=0 ||
               vh101_verify_private_commit(a_path,first,sizeof(first)-1)!=0 ||
               vh101_verify_private_commit(b_path,second,sizeof(second)-1)!=0 ||
               vh101_verified_commits()!=verified+4u ||
               vh103_safe_parent_walks()<walked+12u){
                SysPrintf("VH103_INODE_OR_COMPONENT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 29;
            }
            /* A symlinked INTERMEDIATE component points right back to the
             * same private parent, yet must still be rejected by openat. */
            if(symlink(".",link_path)!=0 ||
               vh82_publish_private(redirected,first,sizeof(first)-1)==0 ||
               unlink(link_path)!=0 ||
               vh82_publish_private(a_path,second,sizeof(second)-1)==0 ||
               vh99_private_state(a_path)!=1 ||
               vh99_private_state(b_path)!=1 ||
               remove(a_path)!=0 || remove(b_path)!=0 ||
               vh80_dropped()!=0){
                SysPrintf("VH103_INTERMEDIATE_LINK_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 29;
            }
            vh80_record(VH103_SAFE_WALKS,12u,0,0);
            vh80_record(VH103_VERIFIED_FILES,4u,0,0);
            vh80_record(VH103_SYMLINK_REFUSED,1u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=old_events+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH103_FINAL_CHECKPOINT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 29;
            }
            SysPrintf("VH103_PATH_GUARD_PASS parent_walks_min=12 inode_checks=4 intermediate_symlink_refused=1 prior_events=%u final_events=%u drops=0\n",
                old_events,vh80_count());
        }
'''

def apply(root:Path):
    proof=apply_v102(root)
    target=root.resolve()/"frontend/main.c"
    fs=target.read_text()
    fs=once(fs,'\tint vh102_anchored_smoke = 0;\n',
            '\tint vh102_anchored_smoke = 0;\n'
            '\tint vh103_inode_smoke = 0;\n',
            "v103 opt-in path component and inode verification")
    old=(
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
        '\t\t}\n'
    )
    fs=once(fs,old,old+
        '\t\telse if (!strcmp(argv[i], "--vh103-inode-path-smoke")) {\n'
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
        '\t\t\tvh103_inode_smoke = 1;\n'
        '\t\t}\n',
        "v103 retains all predecessor native GPU and VBlank controls")
    fs=once(fs,
        '            SysPrintf("VH102_ANCHORED_PASS commits=2 parent_checks_min=12 duplicate_refused=1 prior_events=%u final_events=%u drops=0\\n",\n'
        '                earlier,vh80_count());\n'
        '        }\n',
        '            SysPrintf("VH102_ANCHORED_PASS commits=2 parent_checks_min=12 duplicate_refused=1 prior_events=%u final_events=%u drops=0\\n",\n'
        '                earlier,vh80_count());\n'
        '        }\n'+PROBE,
        "post-v102 native host path guard before original final protected publish")
    target.write_text(fs)
    return dict(proof,
        full_parent_components_openat_nofollow=True,
        initial_final_inode_recorded_before_openat=True,
        inode_swap_faults_isolated_native_only=True,
        live_intermediate_symlink_rejected=True,
        v103_runtime_verified=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
