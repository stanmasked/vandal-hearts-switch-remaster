#!/usr/bin/env python3
"""v99: interrupted private .tmp cannot be treated as a completed journal.

Host synthetic state markers are exercised only after all v80-v98 pinned
PCSX GPU and MIPS oracle proofs, and before the normal exclusive v82 export.
"""
from pathlib import Path
from .apply_map02_v98_pcsx_rearmed import apply as apply_v98
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh99_interruption_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char abandoned[4096],stage[4096],fresh[4096];
            char stage_read[64]={0},fresh_read[64]={0};
            static const char truncated[]="VH99 PARTIAL UNCOMMITTED STAGE";
            static const char recovered[]="VH99 RECOVERED COMPLETE GENERATION\n";
            const unsigned int before=vh80_count();
            if(!private_path || private_path[0]!='/' ||
               strlen(private_path)>3970u ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH99_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 25;
            }
            if(snprintf(abandoned,sizeof(abandoned),"%s.v99-lost",private_path)<0 ||
               snprintf(stage,sizeof(stage),"%s.v99-lost.tmp",private_path)<0 ||
               snprintf(fresh,sizeof(fresh),"%s.v99-fresh",private_path)<0){
                SysPrintf("VH99_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 25;
            }
            /* Populate a 0600 partial stage without creating abandoned
             * final. Real v82 publisher creates it under O_EXCL, fsyncs,
             * and the resulting staged marker stays private. */
            if(vh82_publish_private(stage,truncated,sizeof(truncated)-1)!=0 ||
               vh99_private_state(abandoned)!=2 ||
               vh99_private_state(fresh)!=0 ||
               vh82_publish_private(abandoned,recovered,sizeof(recovered)-1)==0 ||
               vh99_publish_after_interruption(abandoned,abandoned,
                                               recovered,sizeof(recovered)-1)==0 ||
               vh99_publish_after_interruption(abandoned,fresh,
                                               recovered,sizeof(recovered)-1)!=0 ||
               vh99_private_state(abandoned)!=2 ||
               vh99_private_state(fresh)!=1 ||
               vh99_publish_after_interruption(abandoned,fresh,
                                               recovered,sizeof(recovered)-1)==0){
                SysPrintf("VH99_INCOMPLETE_STAGE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 25;
            }
            FILE *sf=fopen(stage,"rb"),*ff=fopen(fresh,"rb");
            int valid=0;
            if(sf && ff){
                size_t sl=fread(stage_read,1,sizeof(stage_read),sf);
                size_t fl=fread(fresh_read,1,sizeof(fresh_read),ff);
                valid=(sl==sizeof(truncated)-1 && fl==sizeof(recovered)-1 &&
                    memcmp(stage_read,truncated,sl)==0 &&
                    memcmp(fresh_read,recovered,fl)==0);
            }
            if(sf)fclose(sf);
            if(ff)fclose(ff);
            if(!valid || remove(stage)!=0 || remove(fresh)!=0 ||
               vh99_private_state(abandoned)!=0 ||
               vh80_dropped()!=0){
                SysPrintf("VH99_STAGE_PRESERVATION_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 25;
            }
            vh80_record(VH99_STAGE_REFUSED,1u,0,0);
            vh80_record(VH99_FRESH_RECOVERED,1u,0,0);
            vh80_record(VH99_OLD_UNMODIFIED,1u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=before+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH99_FINAL_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 25;
            }
            SysPrintf("VH99_INTERRUPTION_PASS abandoned_stage_refused=1 fresh_published=1 duplicate_refused=1 stage_unchanged=1 stage_cleaned=1 previous_events=%u final_events=%u drops=0\n",
                before,vh80_count());
        }
'''

def apply(root:Path):
    result=apply_v98(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,
        '\tint vh98_recovery_smoke = 0;\n',
        '\tint vh98_recovery_smoke = 0;\n'
        '\tint vh99_interruption_smoke = 0;\n',
        "opt-in interrupted private stage proof")
    old=(
        '\t\telse if (!strcmp(argv[i], "--vh98-private-recovery-smoke")) {\n'
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
        '\t\t}\n'
    )
    src=once(src,old,old+
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
        '\t\t}\n',
        "retain every earlier native GPU and four-emulator-VBlank oracle")
    src=once(src,
        '            SysPrintf("VH98_RECOVERY_PASS old_refused=1 fresh_published=1 duplicate_refused=1 old_unchanged=1 temp_cleaned=1 prior_events=%u final_events=%u drops=0\\n",\n'
        '                before,vh80_count());\n'
        '        }\n',
        '            SysPrintf("VH98_RECOVERY_PASS old_refused=1 fresh_published=1 duplicate_refused=1 old_unchanged=1 temp_cleaned=1 prior_events=%u final_events=%u drops=0\\n",\n'
        '                before,vh80_count());\n'
        '        }\n'+PROBE,
        "append host-only interrupted private stage proof after v98 before protected final export")
    frontend.write_text(src)
    return dict(result,
        v99_actual_interrupted_stage_classification=True,
        v99_distinct_private_target_required=True,
        original_v82_final_destination_untouched=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False,
        v99_runtime_verified=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
