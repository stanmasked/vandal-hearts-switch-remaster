#!/usr/bin/env python3
"""v104: two full private-file reads straddling fsync, preserving pinned oracle."""
from pathlib import Path
from .apply_map02_v103_pcsx_rearmed import apply as apply_v103
from .apply_map02_v69_pcsx_rearmed import once

PROBE=r'''
        if(vh104_content_smoke){
            const char *private_path=getenv("VH_MAP02_V82_PRIVATE_PATH");
            char p1[4096],p2[4096];
            static const char first[]="VH104 complete private content A\n";
            static const char second[]="VH104 complete private content B\n";
            const unsigned int before=vh80_count();
            const unsigned int rechecks=vh104_second_pass_reads();
            const unsigned int publishes=vh102_anchored_publishes();
            (void)vh80_events(); /* v103's bounded suffix invalidates cache */
            if(!private_path || strlen(private_path)>3940u ||
               vh80_dropped()!=0 || vh94_snapshot_check()!=0 ||
               vh80_aggregate_count()+3u>VH80_CAPACITY_AGGREGATE){
                SysPrintf("VH104_BASE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            if(snprintf(p1,sizeof(p1),"%s.v104-write-a",private_path)<0 ||
               snprintf(p2,sizeof(p2),"%s.v104-write-b",private_path)<0){
                SysPrintf("VH104_PATH_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            if(vh82_publish_private(p1,first,sizeof(first)-1)!=0 ||
               vh82_publish_private(p2,second,sizeof(second)-1)!=0 ||
               vh101_verify_private_commit(p1,first,sizeof(first)-1)!=0 ||
               vh101_verify_private_commit(p2,second,sizeof(second)-1)!=0 ||
               vh104_second_pass_reads()!=rechecks+4u ||
               vh102_anchored_publishes()!=publishes+2u){
                SysPrintf("VH104_DOUBLE_READ_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            /* Deliberately change one byte IN PLACE without replacing inode
             * or file length, using our owned synthetic private marker. */
            FILE *writer=fopen(p1,"r+b");
            if(!writer){
                SysPrintf("VH104_MUTATION_OPEN_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            int altered=(fputc('X',writer)!=EOF && fflush(writer)==0 &&
                fsync(fileno(writer))==0);
            if(fclose(writer)!=0)altered=0;
            if(!altered ||
               vh101_verify_private_commit(p1,first,sizeof(first)-1)==0 ||
               vh104_second_pass_reads()!=rechecks+4u ||
               vh99_private_state(p1)!=1){
                SysPrintf("VH104_SAME_INODE_TAMPER_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            writer=fopen(p1,"r+b");
            if(!writer){
                SysPrintf("VH104_RESTORE_OPEN_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            int restored=(fwrite(first,1,sizeof(first)-1,writer)==sizeof(first)-1 &&
                          fflush(writer)==0 && fsync(fileno(writer))==0);
            if(fclose(writer)!=0)restored=0;
            FILE *reader=fopen(p1,"rb");
            char check[sizeof(first)]={0};
            if(!reader || !restored ||
               fread(check,1,sizeof(first)-1,reader)!=sizeof(first)-1 ||
               memcmp(check,first,sizeof(first)-1)!=0){
                if(reader)fclose(reader);
                SysPrintf("VH104_PRIVATE_RESTORATION_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            fclose(reader);
            if(remove(p1)!=0 || remove(p2)!=0 || vh80_dropped()!=0){
                SysPrintf("VH104_PRIVATE_FIXTURE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            vh80_record(VH104_DOUBLE_READS,4u,0,0);
            vh80_record(VH104_MODIFIED_REFUSED,1u,0,0);
            vh80_record(VH104_PUBLISHES,2u,0,0);
            if(vh80_dropped()!=0 || vh80_count()!=before+3u ||
               vh94_snapshot_check()==0){
                SysPrintf("VH104_SEQUENCE_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 30;
            }
            SysPrintf("VH104_CONTENT_PASS second_reads=4 same_inode_refused=1 published=2 prior_events=%u final_events=%u drops=0\n",
                before,vh80_count());
        }
'''

FLAGS=("vh78_vblank_smoke","vh82_export_smoke","vh83_renderer_smoke",
       "vh84_sample_smoke","vh85_native_store_smoke","vh86_gpulib_copy_smoke",
       "vh87_extended_smoke","vh88_async_smoke","vh89_async_copy_smoke",
       "vh90_mixed_smoke","vh91_cycles_smoke","vh92_pressure_smoke",
       "vh93_split_smoke","vh94_cached_snapshot_smoke","vh95_roundtrip_smoke",
       "vh96_boundary_smoke","vh97_scrub_smoke","vh98_recovery_smoke",
       "vh99_interruption_smoke","vh100_durability_smoke",
       "vh101_reopened_smoke","vh102_anchored_smoke","vh103_inode_smoke")

def apply(root:Path):
    previous=apply_v103(root)
    path=root.resolve()/"frontend/main.c"
    src=path.read_text()
    src=once(src,'\tint vh103_inode_smoke = 0;\n',
             '\tint vh103_inode_smoke = 0;\n'
             '\tint vh104_content_smoke = 0;\n',
             "explicit private double-readback host diagnostic")
    def flag_block(name,flags):
        return ('\t\telse if (!strcmp(argv[i], "'+name+'")) {\n'+
                ''.join('\t\t\t'+f+' = 1;\n' for f in flags)+
                '\t\t}\n')
    old=flag_block("--vh103-inode-path-smoke",FLAGS)
    new=flag_block("--vh104-double-readback-smoke",FLAGS+("vh104_content_smoke",))
    src=once(src,old,old+new,"v104 invokes all previous pinned MIPS/GP0 checks")
    old_log=(
        '            SysPrintf("VH103_PATH_GUARD_PASS parent_walks_min=12 inode_checks=4 intermediate_symlink_refused=1 prior_events=%u final_events=%u drops=0\\n",\n'
        '                old_events,vh80_count());\n'
        '        }\n'
    )
    src=once(src,old_log,old_log+PROBE,
             "v104 readback after v103, before protected canonical v82 journal export")
    path.write_text(src)
    return dict(previous,
        committed_second_full_read_after_fsync=True,
        same_inode_mutations_refused=True,
        pre_and_post_commit_timestamps_checked=True,
        fault_injection_only_isolated_C=True,
        actual_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False,
        v104_runtime_verified=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
