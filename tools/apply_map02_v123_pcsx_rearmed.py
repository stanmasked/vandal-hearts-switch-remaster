#!/usr/bin/env python3
"""v123: observe actual MIPS-started DMA2 mem->GPU on pinned PCSX Unai.

One separate opt-in synthetic EXE; canonical v82 private JSONL, v120
host-GP0 and v121 MIPS MMIO GP0 controls are left unchanged.
"""
from pathlib import Path
from .apply_map02_v122_pcsx_rearmed import apply as apply_v122
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v123_mips_dma2_linkedlist_exe import build,MARKERS,EXPECTED_PIXELS

DMA_DECL=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Linked-list transport-only aggregates: never packet words or pixels. */
unsigned int vh123_dma2_enabled;
unsigned int vh123_dma2_blocks;
unsigned int vh123_dma2_rejected;
unsigned int vh123_nodes_seen;
unsigned int vh123_words_seen;
#endif
"""
DMA_OBSERVE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
            if(vh123_dma2_enabled) {
                if(madr==0x00012000u && bcr==0u &&
                   chcr==0x01000401u && vh123_dma2_blocks<5u)
                    vh123_dma2_blocks++;
                else
                    vh123_dma2_rejected++;
            }
#endif
"""
GPU_EXTERN=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
extern unsigned int vh123_dma2_enabled;
extern unsigned int vh123_nodes_seen;
extern unsigned int vh123_words_seen;
extern unsigned int vh123_dma2_rejected;
#endif
"""
GPU_NODE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh123_dma2_enabled) {
      const unsigned slot=vh123_nodes_seen%3u;
      const unsigned where=(unsigned)((list-rambase)*4);
      const unsigned expected_addr[3]={0x12000u,0x12100u,0x12200u};
      const unsigned expected_len[3]={0u,3u,0u};
      const unsigned expected_next[3]={0x12100u,0x12200u,0x800000u};
      if(vh123_nodes_seen>=15u ||
         where!=expected_addr[slot] || (unsigned)len!=expected_len[slot] ||
         addr!=expected_next[slot])
        vh123_dma2_rejected++;
      else {
        vh123_nodes_seen++;
        vh123_words_seen+=(unsigned)len;
      }
    }
#endif
"""

def oracle_source(stops):
    stop="{"+",".join(f"0x{word:08x}u" for word in stops)+"}"
    marks="{"+",".join(f"0x{word:08x}u" for word in MARKERS)+"}"
    pixels="{"+",".join(f"0x{word:04x}u" for word in EXPECTED_PIXELS)+"}"
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh123_mips_dma2_smoke) {
        extern unsigned int vh123_dma2_enabled;
        extern unsigned int vh123_dma2_blocks;
        extern unsigned int vh123_dma2_rejected;
        extern unsigned int vh123_nodes_seen;
        extern unsigned int vh123_words_seen;
        static const uint32_t vh123_stops[6]=VH123_STOPS;
        static const uint32_t vh123_marks[6]=VH123_MARKS;
        static const uint16_t vh123_colors[5]=VH123_COLORS;
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
            SysPrintf("VH123_MIPS_EXE_REFUSED\n");
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
        if(psxRegs.pc!=vh123_stops[0] || first!=vh123_marks[0]){
            SysPrintf("VH123_MIPS_SETUP_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        /* GPUwriteData buffers MIPS setup GP0 words: flush ONLY those
         * already CPU-authored commands before starting the 5-stage
         * equality witness. This is not a host-authored GPU packet. */
        GPUFreeze_t setup_freeze={0};
        uint16_t *setup_ptr=NULL;
        if(GPU_freeze(1,&setup_freeze,&setup_ptr)!=1 || !setup_ptr){
            SysPrintf("VH123_MIPS_SETUP_DRAIN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        vh80_reset();
        vh84_set_sampling(1);
        vh115_enable(1);
        vh123_dma2_blocks=0;
        vh123_dma2_rejected=0;
        vh123_nodes_seen=0;
        vh123_words_seen=0;
        vh123_dma2_enabled=1;
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
            if(psxRegs.pc!=vh123_stops[phase+1u] ||
               marker!=vh123_marks[phase+1u]){
                SysPrintf("VH123_MIPS_CPU_PHASE_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            if(vh123_dma2_blocks!=phase+1u ||
               vh123_nodes_seen!=3u*(phase+1u) ||
               vh123_words_seen!=3u*(phase+1u) || vh123_dma2_rejected!=0u){
                SysPrintf("VH123_DMA2_COUNT_REFUSED phase=%u blocks=%u invalid=%u\n",
                          phase,vh123_dma2_blocks,vh123_dma2_rejected);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            GPUFreeze_t native={0};
            uint16_t *vram=NULL;
            if(GPU_freeze(1,&native,&vram)!=1 || !vram){
                SysPrintf("VH123_GPU_READBACK_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            for(unsigned int y=160u;y<164u;y++)
                for(unsigned int x=40u;x<44u;x++)
                    if(vram[y*1024u+x]!=vh123_colors[phase]){
                        SysPrintf("VH123_VRAM_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
                    }
            vh115_metrics metrics={0};
            int ok=vh115_get_metrics(&metrics);
            if(ok!=0 || metrics.handlers!=phase+1u ||
               metrics.vblank_edges!=0u){
                SysPrintf("VH123_UNAI_REFUSED phase=%u valid=%d handlers=%u vblank=%u\n",
                          phase,ok,metrics.handlers,metrics.vblank_edges);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
            verified_readbacks++;
        }
        vh123_dma2_enabled=0;
        vh119_quintuplet_metrics five;
        if(vh119_get_quintuplet_metrics(&five)!=0 ||
           five.consecutive_quintuplets!=1u ||
           five.returned_to_four_back[0]!=1u ||
           vh123_dma2_blocks!=5u || vh123_nodes_seen!=15u ||
           vh123_words_seen!=15u || vh123_dma2_rejected ||
           verified_readbacks!=5u){
            SysPrintf("VH123_RETURN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++){
            if(five.same_as_previous[gap] ||
               five.returned_to_two_back[gap] ||
               five.returned_to_three_back[gap] ||
               five.different_from_all_four[gap] ||
               (gap>0 && five.returned_to_four_back[gap])){
                SysPrintf("VH123_RETURN_BINS_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
            }
        }
        vh115_reset();
        if(!vh115_sample_cache_erased()){
            SysPrintf("VH123_ERASE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 38;
        }
        SysPrintf("VH123_MIPS_GPU_LIST_RETURN_PASS stages=6 lists=5 nodes=15 words=15 native_unai=5 readbacks=5 four_back=1 vblanks=0 erased=1\n");
        ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
    }
#endif

""".replace("VH123_STOPS",stop).replace("VH123_MARKS",marks).replace("VH123_COLORS",pixels)


def apply(root:Path):
    proof=apply_v122(root)
    base=root.resolve()
    psxdma=base/"libpcsxcore/psxdma.c"
    gpulib=base/"plugins/gpulib/gpu.c"
    frontend=base/"frontend/main.c"

    dma=psxdma.read_text()
    dma=once(dma,"unsigned int vh122_dma2_rejected;\n",
             "unsigned int vh122_dma2_rejected;\n"+DMA_DECL,
             "separate native linked-list DMA2 counters")
    dma=once(dma,"\t\tcase 0x01000401: // dma chain\n",
             "\t\tcase 0x01000401: // dma chain\n"+DMA_OBSERVE,
             "native psxDma2 linked-list mode observation")
    psxdma.write_text(dma)

    gpu=gpulib.read_text()
    anchor="long GPUdmaChain(uint32_t *rambase, uint32_t start_addr,"
    gpu=once(gpu,anchor,GPU_EXTERN+anchor,
             "native Unai DMA chain traversal counters")
    anchor="    addr = LE32TOH(list[0]) & 0xffffff;\n"
    gpu=once(gpu,anchor,anchor+GPU_NODE,
             "verify each real linked-list node, terminator and payload word count")
    gpulib.write_text(gpu)

    src=frontend.read_text()
    src=once(src,"\tint vh122_mips_dma2_smoke = 0;\n",
             "\tint vh122_mips_dma2_smoke = 0;\n"
             "\tint vh123_mips_dma2_list_smoke = 0;\n",
             "separate linked-list MIPS smoke opt-in")
    old='\t\telse if (!strcmp(argv[i], "--vh122-mips-dma2-return-smoke"))\n'
    src=once(src,old,
             '\t\telse if (!strcmp(argv[i], "--vh123-mips-gpu-list-return-smoke"))\n'
             '\t\t\tvh123_mips_dma2_list_smoke=1;\n'+old,
             "separate MIPS GPU DMA2 linked-list flag")
    _,stops,_,_=build()
    # C name here must match the new v123 flag, not v122 block-mode flag.
    oracle=oracle_source(stops).replace(
        "if(vh123_mips_dma2_smoke)", "if(vh123_mips_dma2_list_smoke)")
    src=once(src,"\tif (loadst_f) {\n",oracle+"\tif (loadst_f) {\n",
             "independent linked-list GPU command traversal within MIPS fixture")
    frontend.write_text(src)
    return dict(proof,
        native_psxdma2_linked_list_mode=True,
        native_gpu_dma_chain_traverses_three_nodes_per_list=True,
        mips_cpu_authored_all_ram_chain_headers=True,
        mips_gpu_draws_submitted_by_host=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
