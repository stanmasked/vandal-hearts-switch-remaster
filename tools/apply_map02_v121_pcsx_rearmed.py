#!/usr/bin/env python3
"""v121: opt-in *interpreted-MIPS-authored* GP0 return in pinned PCSX Unai.

Adds a separate synthetic-EXE smoke mode. Does not modify the original
v78/v120 scene, published v82 private journal, renderer or GPU timing.
"""
from pathlib import Path
from .apply_map02_v120_pcsx_rearmed import apply as apply_v120
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v121_mips_gp0_return_exe import (
    build, MARKERS, EXPECTED_PIXELS
)


def oracle_source(stops):
    stop="{"+",".join(f"0x{word:08x}u" for word in stops)+"}"
    marks="{"+",".join(f"0x{word:08x}u" for word in MARKERS)+"}"
    pixels="{"+",".join(f"0x{word:04x}u" for word in EXPECTED_PIXELS)+"}"
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh121_mips_return_smoke) {
        /* Completely separate *interpreted MIPS* fixture, never the
         * legacy host-submitted v120 rectangles or retail MAP02. */
        static const uint32_t vh121_stops[6]=VH121_STOPS;
        static const uint32_t vh121_marks[6]=VH121_MARKS;
        static const uint16_t vh121_colors[5]=VH121_COLORS;
        unsigned char tag[8]={0};
        FILE *exe=file[0] ? fopen(file,"rb") : NULL;
        int signed_fixture=0;
        if(exe) {
            if(fseek(exe,0x4c,SEEK_SET)==0 &&
               fread(tag,1,sizeof(tag),exe)==sizeof(tag) &&
               memcmp(tag,"VH121SY!",sizeof(tag))==0)
                signed_fixture=1;
            fclose(exe);
        }
        if(!signed_fixture || !ready_to_go || Config.Cpu!=1 ||
           psxRegs.pc!=0x80010000u || !GPU_freeze ||
           !psxRegs.ptrs.psxM){
            SysPrintf("VH121_EXE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
        }
        /* Stage zero is GPU draw-area/mask setup *from CPU SW*, not a
         * host GPU API. It is deliberately outside the 5-value witness. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
        unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
        uint32_t stage0=((uint32_t)ram[0x11100]) |
            ((uint32_t)ram[0x11101]<<8) |
            ((uint32_t)ram[0x11102]<<16) |
            ((uint32_t)ram[0x11103]<<24);
        if(psxRegs.pc!=vh121_stops[0] || stage0!=vh121_marks[0]){
            SysPrintf("VH121_MIPS_SETUP_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
        }
        /* GPUwriteData() buffers MIPS MMIO words. Drain only already
         * CPU-authored SETUP commands before enabling sample observer;
         * otherwise their delayed execution contaminates the A-B-C-D-A
         * window. This host does not submit any new GPU draw commands. */
        GPUFreeze_t setup_freeze={0};
        uint16_t *setup_pixels=NULL;
        if(GPU_freeze(1,&setup_freeze,&setup_pixels)!=1 || !setup_pixels){
            SysPrintf("VH121_SETUP_DRAIN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
        }
        /* Reset only the private diagnostic timeline, not GPU/CPU.
         * The original v82 journal exists only in the other run. */
        vh80_reset();
        vh84_set_sampling(1);
        vh115_enable(1);
        unsigned int readbacks=0;
        for(unsigned int phase=0;phase<5u;phase++){
            /* The EXE's actual MIPS SW instructions push three GP0
             * words to 0x1f801810, followed by a CPU RAM marker.
             * This host does not submit any of the five GP0 draws. */
            psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
            unsigned int at=0x11100u+4u*(phase+1u);
            uint32_t marker=((uint32_t)ram[at]) |
                ((uint32_t)ram[at+1u]<<8) |
                ((uint32_t)ram[at+2u]<<16) |
                ((uint32_t)ram[at+3u]<<24);
            if(psxRegs.pc!=vh121_stops[phase+1u] ||
               marker!=vh121_marks[phase+1u]){
                SysPrintf("VH121_MIPS_PHASE_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
            }
            GPUFreeze_t freeze_state={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&freeze_state,&vram)!=1 || !vram){
                SysPrintf("VH121_GPU_READBACK_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
            }
            for(unsigned int y=160u;y<164u;y++)
                for(unsigned int x=40u;x<44u;x++)
                    if(vram[y*1024u+x]!=vh121_colors[phase]){
                        SysPrintf("VH121_VRAM_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
                    }
            vh115_metrics metrics={0};
            int metric_status=vh115_get_metrics(&metrics);
            if(metric_status!=0 ||
               metrics.handlers!=phase+1u || metrics.vblank_edges!=0u){
                SysPrintf("VH121_UNAI_COUNT_REFUSED phase=%u status=%d handlers=%u vblanks=%u sampling=%d timeline_entries=%u\n",
                    phase,metric_status,metrics.handlers,
                    metrics.vblank_edges,vh84_sampling_enabled(),vh80_count());
                ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
            }
            readbacks++;
        }
        vh119_quintuplet_metrics five;
        if(vh119_get_quintuplet_metrics(&five)!=0 ||
           five.consecutive_quintuplets!=1u ||
           five.returned_to_four_back[0]!=1u || readbacks!=5u){
            SysPrintf("VH121_RETURN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
        }
        for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++){
            if(five.same_as_previous[gap] ||
               five.returned_to_two_back[gap] ||
               five.returned_to_three_back[gap] ||
               five.different_from_all_four[gap] ||
               (gap>0u && five.returned_to_four_back[gap])){
                SysPrintf("VH121_RETURN_BINS_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
            }
        }
        vh115_reset();
        if(!vh115_sample_cache_erased()){
            SysPrintf("VH121_ERASE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 37;
        }
        SysPrintf("VH121_MIPS_GP0_RETURN_PASS stages=6 mips_rectangles=5 native_unai=5 readbacks=5 four_back=1 vblanks=0 erased=1\n");
        ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
    }
#endif

""".replace("VH121_STOPS",stop).replace("VH121_MARKS",marks).replace("VH121_COLORS",pixels)


def apply(root: Path):
    proof=apply_v120(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,
        '\tint vh104_content_smoke = 0;\n',
        '\tint vh104_content_smoke = 0;\n'
        '\tint vh121_mips_return_smoke = 0;\n',
        "v121 independent MIPS return smoke opt-in")
    old='\t\telse if (!strcmp(argv[i], "--vh104-double-readback-smoke")) {\n'
    new=('\t\telse if (!strcmp(argv[i], "--vh121-mips-gp0-return-smoke"))\n'
         '\t\t\tvh121_mips_return_smoke=1;\n'+old)
    src=once(src,old,new,"v121 separate independent MIPS EXE CLI")
    _,stops,_,_=build()
    src=once(src,'\tif (loadst_f) {\n',
        oracle_source(stops)+'\tif (loadst_f) {\n',
        "six real interpreted MIPS phase readbacks in own PCSX process")
    frontend.write_text(src)
    return dict(proof,
        new_synthetic_psx_exe_interpreted_mips_gp0_sw=True,
        original_v120_host_fixture_unchanged=True,
        original_v82_private_jsonl_unchanged=True,
        gp0_draw_data_submitted_by_host_in_v121=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
