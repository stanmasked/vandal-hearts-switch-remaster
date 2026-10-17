#!/usr/bin/env python3
"""v122: observe actual MIPS-started DMA2 mem->GPU on pinned PCSX Unai.

One separate opt-in synthetic EXE; canonical v82 private JSONL, v120
host-GP0 and v121 MIPS MMIO GP0 controls are left unchanged.
"""
from pathlib import Path
from .apply_map02_v121_pcsx_rearmed import apply as apply_v121
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v122_mips_dma2_gp0_exe import build,MARKERS,EXPECTED_PIXELS

DMA_DECL= r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Integer-only, test-only observation at the original psxDma2
 * memory->GPU call site, no packet values/pointers ever exported. */
unsigned int vh122_dma2_enabled;
unsigned int vh122_dma2_blocks;
unsigned int vh122_dma2_rejected;
#endif

"""
DMA_OBSERVE = r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
            if(vh122_dma2_enabled) {
                if(madr==0x00012000u && bcr==0x00010003u &&
                   chcr==0x01000201u && vh122_dma2_blocks<5u)
                    vh122_dma2_blocks++;
                else
                    vh122_dma2_rejected++;
            }
#endif
"""


def oracle_source(stops):
    stop="{"+",".join(f"0x{word:08x}u" for word in stops)+"}"
    marks="{"+",".join(f"0x{word:08x}u" for word in MARKERS)+"}"
    pixels="{"+",".join(f"0x{word:04x}u" for word in EXPECTED_PIXELS)+"}"
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh122_mips_dma2_smoke) {
        extern unsigned int vh122_dma2_enabled;
        extern unsigned int vh122_dma2_blocks;
        extern unsigned int vh122_dma2_rejected;
        static const uint32_t vh122_stops[6]=VH122_STOPS;
        static const uint32_t vh122_marks[6]=VH122_MARKS;
        static const uint16_t vh122_colors[5]=VH122_COLORS;
        unsigned char tag[8]={0};
        FILE *exe=file[0] ? fopen(file,"rb") : NULL;
        int verified_exe=0;
        if(exe) {
            if(fseek(exe,0x4c,SEEK_SET)==0 &&
               fread(tag,1,sizeof(tag),exe)==sizeof(tag) &&
               memcmp(tag,"VH122SY!",sizeof(tag))==0)
                verified_exe=1;
            fclose(exe);
        }
        if(!verified_exe || !ready_to_go || Config.Cpu!=1 ||
           psxRegs.pc!=0x80010000u || !GPU_freeze ||
           !psxRegs.ptrs.psxM) {
            SysPrintf("VH122_MIPS_EXE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
        /* Actual interpreted CPU stage zero: GPU setup GP0 SW plus
         * DPCR channel-2 enable. No host-submitted GPU commands. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
        unsigned int off=0x11140u;
        uint32_t first=((uint32_t)ram[off]) |
            ((uint32_t)ram[off+1]<<8) |
            ((uint32_t)ram[off+2]<<16) |
            ((uint32_t)ram[off+3]<<24);
        if(psxRegs.pc!=vh122_stops[0] || first!=vh122_marks[0]){
            SysPrintf("VH122_MIPS_SETUP_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        /* GPUwriteData buffers MIPS setup GP0 words: flush ONLY those
         * already CPU-authored commands before starting the 5-stage
         * equality witness. This is not a host-authored GPU packet. */
        GPUFreeze_t setup_freeze={0};
        uint16_t *setup_ptr=NULL;
        if(GPU_freeze(1,&setup_freeze,&setup_ptr)!=1 || !setup_ptr){
            SysPrintf("VH122_MIPS_SETUP_DRAIN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        vh80_reset();
        vh84_set_sampling(1);
        vh115_enable(1);
        vh122_dma2_blocks=0;
        vh122_dma2_rejected=0;
        vh122_dma2_enabled=1;
        unsigned int verified_readbacks=0;
        for(unsigned int phase=0;phase<5u;phase++){
            /* The MIPS CPU writes a 3-word packet to its own RAM and
             * starts block DMA2 via HW MADR/BCR/CHCR. The native
             * psxDma2() instrumentation must see exactly one
             * properly configured real mem->GPU transfer per phase. */
            psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
            unsigned int at=0x11140u+4u*(phase+1u);
            uint32_t marker=((uint32_t)ram[at]) |
                ((uint32_t)ram[at+1]<<8) |
                ((uint32_t)ram[at+2]<<16) |
                ((uint32_t)ram[at+3]<<24);
            if(psxRegs.pc!=vh122_stops[phase+1u] ||
               marker!=vh122_marks[phase+1u]){
                SysPrintf("VH122_MIPS_CPU_PHASE_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            if(vh122_dma2_blocks!=phase+1u || vh122_dma2_rejected!=0u){
                SysPrintf("VH122_DMA2_COUNT_REFUSED phase=%u blocks=%u invalid=%u\n",
                          phase,vh122_dma2_blocks,vh122_dma2_rejected);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            GPUFreeze_t native={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&native,&vram)!=1 || !vram){
                SysPrintf("VH122_GPU_READBACK_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            for(unsigned int y=160u;y<164u;y++)
                for(unsigned int x=40u;x<44u;x++)
                    if(vram[y*1024u+x]!=vh122_colors[phase]){
                        SysPrintf("VH122_VRAM_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
                    }
            vh115_metrics metrics={0};
            int ok=vh115_get_metrics(&metrics);
            if(ok!=0 || metrics.handlers!=phase+1u ||
               metrics.vblank_edges!=0u){
                SysPrintf("VH122_UNAI_REFUSED phase=%u valid=%d handlers=%u vblank=%u\n",
                          phase,ok,metrics.handlers,metrics.vblank_edges);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            verified_readbacks++;
        }
        vh122_dma2_enabled=0;
        vh119_quintuplet_metrics five;
        if(vh119_get_quintuplet_metrics(&five)!=0 ||
           five.consecutive_quintuplets!=1u ||
           five.returned_to_four_back[0]!=1u ||
           vh122_dma2_blocks!=5u || vh122_dma2_rejected ||
           verified_readbacks!=5u){
            SysPrintf("VH122_RETURN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++){
            if(five.same_as_previous[gap] ||
               five.returned_to_two_back[gap] ||
               five.returned_to_three_back[gap] ||
               five.different_from_all_four[gap] ||
               (gap>0 && five.returned_to_four_back[gap])){
                SysPrintf("VH122_RETURN_BINS_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
        }
        vh115_reset();
        if(!vh115_sample_cache_erased()){
            SysPrintf("VH122_ERASE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        SysPrintf("VH122_MIPS_DMA2_RETURN_PASS stages=6 dma2_blocks=5 words=15 native_unai=5 readbacks=5 four_back=1 vblanks=0 erased=1\n");
        ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
    }
#endif

""".replace("VH122_STOPS",stop).replace("VH122_MARKS",marks).replace("VH122_COLORS",pixels)


def apply(root:Path):
    proof=apply_v121(root)
    base=root.resolve()
    psxdma=base/"libpcsxcore/psxdma.c"
    frontend=base/"frontend/main.c"
    dma=psxdma.read_text()
    dma=once(dma,"void psxDma2(u32 madr, u32 bcr, u32 chcr) { // GPU",
             DMA_DECL+"void psxDma2(u32 madr, u32 bcr, u32 chcr) { // GPU",
             "actual PS1 DMA2 read-only counter scope")
    dma=once(dma,'\t\tcase 0x01000201: // mem2vram\n',
             '\t\tcase 0x01000201: // mem2vram\n'+DMA_OBSERVE,
             "real psxDma2 mem-to-GPU path bounded counter")
    psxdma.write_text(dma)
    src=frontend.read_text()
    src=once(src,'\tint vh121_mips_return_smoke = 0;\n',
             '\tint vh121_mips_return_smoke = 0;\n'
             '\tint vh122_mips_dma2_smoke = 0;\n',
             "separate MIPS DMA2 mode")
    old='\t\telse if (!strcmp(argv[i], "--vh121-mips-gp0-return-smoke"))\n'
    src=once(src,old,
             '\t\telse if (!strcmp(argv[i], "--vh122-mips-dma2-return-smoke"))\n'
             '\t\t\tvh122_mips_dma2_smoke=1;\n'+old,
             "separate DMA2 smoke opt-in")
    _,stops,_,_=build()
    src=once(src,'\tif (loadst_f) {\n',
             oracle_source(stops)+'\tif (loadst_f) {\n',
             "six interpreted MIPS DMA2 stages with native pixel return")
    frontend.write_text(src)
    return dict(proof,
        interpreted_mips_authored_ram_gp0_commands=True,
        hardware_dma2_chcr_start_observed=True,
        native_psxdma2_ram_to_gpu_path_instrumented=True,
        no_host_gpu_draw_submissions_in_v122=True,
        original_v82_private_journal_untouched=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
