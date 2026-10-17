#!/usr/bin/env python3
"""v100 pinned PCSX: verify actual directory fsyncs of private marker exports."""
from pathlib import Path
from .apply_map02_v99_pcsx_rearmed import apply as apply_v99
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh100_durability_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char marker_a[4096],marker_b[4096],read_a[48]={0},read_b[48]={0};
            static const char a[]="VH100 durable private A\n";
            static const char b[]="VH100 durable private B\n";
            const unsigned int events_before=vh80_count();
            const unsigned int sync_before=vh100_directory_syncs();
            /* v99 just appended its own private metrics: refresh the
             * invalidated merged view before integrity verification. */
            (void)vh80_events();
            if(!private_path || strlen(private_path)>3970u ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH100_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 26;
            }
            if(snprintf(marker_a,sizeof(marker_a),"%s.v100-sync-a",private_path)<0 ||
               snprintf(marker_b,sizeof(marker_b),"%s.v100-sync-b",private_path)<0){
                SysPrintf("VH100_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 26;
            }
            if(vh82_publish_private(marker_a,a,sizeof(a)-1)!=0 ||
               vh100_directory_syncs()!=sync_before+2u ||
               vh82_publish_private(marker_b,b,sizeof(b)-1)!=0 ||
               vh100_directory_syncs()!=sync_before+4u ||
               vh82_publish_private(marker_a,b,sizeof(b)-1)==0 ||
               vh100_directory_syncs()!=sync_before+4u){
                SysPrintf("VH100_DIRECTORY_FSYNC_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 26;
            }
            FILE *f1=fopen(marker_a,"rb"),*f2=fopen(marker_b,"rb");
            int matched=0;
            if(f1 && f2){
                size_t x=fread(read_a,1,sizeof(read_a),f1);
                size_t y=fread(read_b,1,sizeof(read_b),f2);
                matched=(x==sizeof(a)-1 && y==sizeof(b)-1 &&
                    memcmp(read_a,a,x)==0 && memcmp(read_b,b,y)==0);
            }
            if(f1)fclose(f1);
            if(f2)fclose(f2);
            if(!matched || remove(marker_a)!=0 || remove(marker_b)!=0 ||
               vh80_dropped()!=0){
                SysPrintf("VH100_IMMUTABLE_MARKERS_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 26;
            }
            vh80_record(VH100_FIRST_DIR_SYNC,2u,0,0);
            vh80_record(VH100_FINAL_DIR_SYNC,2u,0,0);
            vh80_record(VH100_FAILURE_REFUSED,1u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=events_before+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH100_FINAL_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 26;
            }
            SysPrintf("VH100_DURABILITY_PASS post_link_dirsync=2 post_unlink_dirsync=2 duplicate_refused=1 previous_events=%u final_events=%u drops=0\n",
                events_before,vh80_count());
        }
'''

def apply(root:Path):
    result=apply_v99(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,
        '\tint vh99_interruption_smoke = 0;\n',
        '\tint vh99_interruption_smoke = 0;\n'
        '\tint vh100_durability_smoke = 0;\n',
        "v100 pinned native private fsync probe flag")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh99-interrupted-export-smoke")) {\n'
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
        '\t\t}\n'
    )
    src=once(src,old,old+
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
        '\t\t}\n',
        "v100 opt-in retains all pinned emulator VBlank and GPU probes")
    src=once(src,
        '            SysPrintf("VH99_INTERRUPTION_PASS abandoned_stage_refused=1 fresh_published=1 duplicate_refused=1 stage_unchanged=1 stage_cleaned=1 previous_events=%u final_events=%u drops=0\\n",\n'
        '                before,vh80_count());\n'
        '        }\n',
        '            SysPrintf("VH99_INTERRUPTION_PASS abandoned_stage_refused=1 fresh_published=1 duplicate_refused=1 stage_unchanged=1 stage_cleaned=1 previous_events=%u final_events=%u drops=0\\n",\n'
        '                before,vh80_count());\n'
        '        }\n'+PROBE,
        "v100 fsync probe after bounded interrupted private stage diagnostics")
    frontend.write_text(src)
    return dict(result,
        native_parent_directory_fsync_post_link=True,
        native_parent_directory_fsync_post_unlink=True,
        original_private_final_publisher_no_clobber=True,
        isolated_faults_only_never_production=True,
        runtime_v100_verified=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
