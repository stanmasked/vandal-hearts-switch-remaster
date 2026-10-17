#!/usr/bin/env python3
"""v98: actual pinned PCSX private-publisher restart may ONLY use fresh path.

All controls are host-synthetic AFTER signed four-emulator-VBlank MIPS
oracle and every v86-v97 pinned GPU worker/VRAM journal checkpoint.
"""
from pathlib import Path
from .apply_map02_v97_pcsx_rearmed import apply as apply_v97
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh98_recovery_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char oldfile[4096],nextfile[4096],old_read[48]={0},next_read[48]={0};
            static const char old_data[]="VH98 old generation private marker\n";
            static const char next_data[]="VH98 recovered new generation\n";
            const unsigned int before=vh80_count();
            if(!private_path || private_path[0]!='/' ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               strlen(private_path)>4000u ||
               vh80_aggregate_count()+3u>=VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH98_SETUP_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 24;
            }
            if(snprintf(oldfile,sizeof(oldfile),"%s.v98-old",private_path)<0 ||
               snprintf(nextfile,sizeof(nextfile),"%s.v98-next",private_path)<0){
                SysPrintf("VH98_BAD_RECOVERY_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 24;
            }
            /* Both temporary fixture files stay inside the same mode-0700
             * private CI directory as the real eventual v82 file. Neither
             * is a public artifact. The canonical v82 final target remains
             * unused until the original protected publisher runs. */
            if(vh82_publish_private(oldfile,old_data,sizeof(old_data)-1)!=0 ||
               vh82_publish_private(oldfile,next_data,sizeof(next_data)-1)==0 ||
               vh98_publish_recovery(oldfile,oldfile,next_data,sizeof(next_data)-1)==0 ||
               vh98_publish_recovery(oldfile,nextfile,next_data,sizeof(next_data)-1)!=0 ||
               vh98_publish_recovery(oldfile,nextfile,next_data,sizeof(next_data)-1)==0){
                SysPrintf("VH98_EXCLUSIVE_RECOVERY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 24;
            }
            FILE *of=fopen(oldfile,"rb");
            FILE *nf=fopen(nextfile,"rb");
            int valid=0;
            if(of && nf){
                size_t oldlen=fread(old_read,1,sizeof(old_read),of);
                size_t newlen=fread(next_read,1,sizeof(next_read),nf);
                valid=(oldlen==sizeof(old_data)-1 &&
                       newlen==sizeof(next_data)-1 &&
                       memcmp(old_read,old_data,oldlen)==0 &&
                       memcmp(next_read,next_data,newlen)==0);
            }
            if(of)fclose(of);
            if(nf)fclose(nf);
            if(!valid || remove(oldfile)!=0 || remove(nextfile)!=0 ||
               vh80_dropped()!=0 || vh97_reset_epoch()==0){
                SysPrintf("VH98_IMMUTABILITY_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 24;
            }
            vh80_record(VH98_OLD_REFUSED,1u,0,0);
            vh80_record(VH98_NEW_PUBLISHED,1u,0,0);
            vh80_record(VH98_REPLAY_REFUSED,1u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=before+3u ||
               vh94_snapshot_check()==0 || vh81_format_jsonl(old_read,sizeof(old_read))!=-1){
                /* A 48-byte destination cannot fit the real full journal;
                 * serializer must refuse without touching the old file. */
                SysPrintf("VH98_FINAL_SNAPSHOT_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 24;
            }
            SysPrintf("VH98_RECOVERY_PASS old_refused=1 fresh_published=1 duplicate_refused=1 old_unchanged=1 temp_cleaned=1 prior_events=%u final_events=%u drops=0\n",
                before,vh80_count());
        }
'''

def apply(root:Path):
    result=apply_v97(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,
        '\tint vh97_scrub_smoke = 0;\n',
        '\tint vh97_scrub_smoke = 0;\n'
        '\tint vh98_recovery_smoke = 0;\n',
        "opt-in distinct private recovery scenario")
    old=(
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
        '\t\t}\n'
    )
    src=once(src,old,old+
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
        '\t\t}\n',
        "preserve complete opt-in pinned GPU oracle chain")
    src=once(src,
        '                epoch,(unsigned int)sizeof(serialized),before,vh80_count());\n'
        '        }\n',
        '                epoch,(unsigned int)sizeof(serialized),before,vh80_count());\n'
        '        }\n'+PROBE,
        "recover private sibling marker files before final v82 exclusive publisher")
    frontend.write_text(src)
    return dict(result,
        original_pinned_4_vblank_and_GPU_workers_preserved=True,
        unique_no_overwrite_private_recovery_probed=True,
        old_private_marker_byte_exact_readback=True,
        original_final_v82_private_destination_untouched=True,
        runtime_v98_verified=False,
        retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
