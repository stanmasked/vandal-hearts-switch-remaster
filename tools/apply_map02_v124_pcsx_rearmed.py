#!/usr/bin/env python3
"""One actual MIPS GPU linked-list DMA contains five ordered GP0 draws.

Exact intermediate pixel readbacks happen *inside* Unai's original
post-dispatch observer, never by host submitting commands or exposing
raw VRAM. Preserves the previous v82-v123 experiments.
"""
from pathlib import Path
from .apply_map02_v123_pcsx_rearmed import apply as apply_v123
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v124_mips_single_list_return_exe import build, MARKERS, EXPECTED_PIXELS

DMA_DECL=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
unsigned int vh124_dma_enabled;
unsigned int vh124_dma_dispatches;
unsigned int vh124_dma_rejected;
unsigned int vh124_nodes_seen;
unsigned int vh124_words_seen;
unsigned int vh124_intermediate_enabled;
unsigned int vh124_intermediate_seen;
unsigned int vh124_intermediate_rejected;
#endif
"""

DMA_OBSERVE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
            if(vh124_dma_enabled) {
                if(madr==0x00012000u && bcr==0u &&
                   chcr==0x01000401u && vh124_dma_dispatches==0u)
                    vh124_dma_dispatches++;
                else
                    vh124_dma_rejected++;
            }
#endif
"""

GPU_EXTERN=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
extern unsigned int vh124_dma_enabled;
extern unsigned int vh124_nodes_seen;
extern unsigned int vh124_words_seen;
extern unsigned int vh124_dma_rejected;
#endif
"""
GPU_NODE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh124_dma_enabled) {
        static const unsigned loc[7]={
            0x12000u,0x12100u,0x12200u,0x12300u,
            0x12400u,0x12500u,0x12600u
        };
        static const unsigned num[7]={0u,3u,3u,3u,3u,3u,0u};
        static const unsigned next[7]={
            0x12100u,0x12200u,0x12300u,0x12400u,
            0x12500u,0x12600u,0x800000u
        };
        const unsigned where=(unsigned)((list-rambase)*4);
        const unsigned slot=vh124_nodes_seen;
        if(slot>=7u || where!=loc[slot] ||
           (unsigned)len!=num[slot] || addr!=next[slot])
            vh124_dma_rejected++;
        else {
            vh124_nodes_seen++;
            vh124_words_seen+=(unsigned)len;
        }
    }
#endif
"""

UNAI_EXTERN=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
extern "C" {
extern unsigned int vh124_intermediate_enabled;
extern unsigned int vh124_intermediate_seen;
extern unsigned int vh124_intermediate_rejected;
}
#endif
"""
UNAI_INTERMEDIATE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
        if(vh124_intermediate_enabled) {
            /* This runs after each original Unai GP0 draw callback.
             * Check the actual 4x4 VRAM pixels at all five intermediate
             * states, not merely the final red state from GPU_freeze. */
            static const uint16_t colors[5]={
                0x001fu,0x03e0u,0x7c00u,0x03ffu,0x001fu
            };
            unsigned int bad=(vh124_intermediate_seen>=5u);
            if(!bad) {
                for(unsigned int y=160u;y<164u;y++)
                    for(unsigned int x=40u;x<44u;x++)
                        if((uint16_t)le16_to_u16(gpu_unai.vram[y*1024u+x])!=
                           colors[vh124_intermediate_seen])
                            bad=1u;
            }
            if(bad)vh124_intermediate_rejected++;
            else vh124_intermediate_seen++;
        }
#endif
"""


def oracle_source(stops):
    st="{"+",".join(f"0x{x:08x}u" for x in stops)+"}"
    markers="{"+",".join(f"0x{x:08x}u" for x in MARKERS)+"}"
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh124_mips_one_list_smoke) {
        extern unsigned int vh124_dma_enabled;
        extern unsigned int vh124_dma_dispatches;
        extern unsigned int vh124_dma_rejected;
        extern unsigned int vh124_nodes_seen;
        extern unsigned int vh124_words_seen;
        extern unsigned int vh124_intermediate_enabled;
        extern unsigned int vh124_intermediate_seen;
        extern unsigned int vh124_intermediate_rejected;
        static const uint32_t vh124_stops[2]=VH124_STOPS;
        static const uint32_t vh124_marks[2]=VH124_MARKS;
        unsigned char tag[8]={0};
        FILE *exe=file[0] ? fopen(file,"rb") : NULL;
        int authentic=0;
        if(exe) {
            if(fseek(exe,0x4c,SEEK_SET)==0 &&
               fread(tag,1,sizeof(tag),exe)==sizeof(tag) &&
               memcmp(tag,"VH124SY!",sizeof(tag))==0)
                authentic=1;
            fclose(exe);
        }
        if(!authentic || !ready_to_go || Config.Cpu!=1 ||
           psxRegs.pc!=0x80010000u || !GPU_freeze ||
           !psxRegs.ptrs.psxM){
            SysPrintf("VH124_EXE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
        /* Stage 0: CPU-authored GP0 state setup and DMA2 DPCR enable. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
        unsigned int off=0x11180u;
        uint32_t setup_mark=(uint32_t)ram[off]|
            ((uint32_t)ram[off+1u]<<8)|
            ((uint32_t)ram[off+2u]<<16)|
            ((uint32_t)ram[off+3u]<<24);
        if(psxRegs.pc!=vh124_stops[0] || setup_mark!=vh124_marks[0]){
            SysPrintf("VH124_SETUP_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        GPUFreeze_t setup={0};
        uint16_t *setup_pixels=NULL;
        if(GPU_freeze(1,&setup,&setup_pixels)!=1 || !setup_pixels){
            SysPrintf("VH124_SETUP_DRAIN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        /* Enable native observers only after draining setup commands. */
        vh80_reset();
        vh84_set_sampling(1);
        vh115_enable(1);
        vh124_dma_dispatches=0;
        vh124_dma_rejected=0;
        vh124_nodes_seen=0;
        vh124_words_seen=0;
        vh124_intermediate_seen=0;
        vh124_intermediate_rejected=0;
        vh124_intermediate_enabled=1;
        vh124_dma_enabled=1;
        /* Stage 1: ONE interpreted CPU-started linked-list DMA2;
         * five GPU rectangle packets, no host draw submission. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
        vh124_dma_enabled=0;
        vh124_intermediate_enabled=0;
        off=0x11184u;
        uint32_t final_mark=(uint32_t)ram[off]|
            ((uint32_t)ram[off+1u]<<8)|
            ((uint32_t)ram[off+2u]<<16)|
            ((uint32_t)ram[off+3u]<<24);
        if(psxRegs.pc!=vh124_stops[1] || final_mark!=vh124_marks[1]){
            SysPrintf("VH124_MIPS_STAGE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        if(vh124_dma_dispatches!=1u || vh124_dma_rejected!=0u ||
           vh124_nodes_seen!=7u || vh124_words_seen!=15u ||
           vh124_intermediate_seen!=5u || vh124_intermediate_rejected!=0u){
            SysPrintf("VH124_CHAIN_COUNTS_REFUSED dispatches=%u nodes=%u words=%u intermediate=%u bad=%u\n",
                vh124_dma_dispatches,vh124_nodes_seen,vh124_words_seen,
                vh124_intermediate_seen,vh124_dma_rejected+
                vh124_intermediate_rejected);
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        /* Host reads ONLY final VRAM; the 5 intermediate 4x4 states
         * were independently checked after each native Unai callback. */
        GPUFreeze_t final_vram={0};
        uint16_t *pixels=NULL;
        if(GPU_freeze(1,&final_vram,&pixels)!=1 || !pixels){
            SysPrintf("VH124_FINAL_READBACK_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        for(unsigned int y=160u;y<164u;y++)
            for(unsigned int x=40u;x<44u;x++)
                if(pixels[y*1024u+x]!=0x001fu){
                    SysPrintf("VH124_FINAL_PIXEL_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
                }
        vh115_metrics samples={0};
        vh119_quintuplet_metrics five={0};
        if(vh115_get_metrics(&samples)!=0 ||
           vh119_get_quintuplet_metrics(&five)!=0 ||
           samples.handlers!=5u || samples.vblank_edges!=0u ||
           five.consecutive_quintuplets!=1u ||
           five.returned_to_four_back[0]!=1u){
            SysPrintf("VH124_SAMPLE_RETURN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++)
            if(five.same_as_previous[gap] ||
               five.returned_to_two_back[gap] ||
               five.returned_to_three_back[gap] ||
               five.different_from_all_four[gap] ||
               (gap>0u && five.returned_to_four_back[gap])){
                SysPrintf("VH124_EXCLUSIVE_RETURN_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
            }
        vh115_reset();
        if(!vh115_sample_cache_erased()){
            SysPrintf("VH124_CACHE_ERASURE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 39;
        }
        SysPrintf("VH124_ONE_LIST_FIVE_GP0_PASS stages=2 lists=1 nodes=7 words=15 unai=5 intermediate=5 readbacks=1 four_back=1 vblanks=0 erased=1\n");
        ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
    }
#endif

""".replace("VH124_STOPS",st).replace("VH124_MARKS",markers)


def apply(root:Path):
    proof=apply_v123(root)
    base=root.resolve()
    psxdma=base/"libpcsxcore/psxdma.c"
    gpulib=base/"plugins/gpulib/gpu.c"
    unai=base/"plugins/gpu_unai/gpulib_if.cpp"
    frontend=base/"frontend/main.c"
    dma=psxdma.read_text()
    dma=once(dma,"unsigned int vh123_words_seen;\n",
             "unsigned int vh123_words_seen;\n"+DMA_DECL,
             "distinct native v124 one-list DMA state")
    dma=once(dma,"\t\tcase 0x01000401: // dma chain\n",
             "\t\tcase 0x01000401: // dma chain\n"+DMA_OBSERVE,
             "count exactly one native PS1 GPU linked-list DMA")
    psxdma.write_text(dma)

    gpu=gpulib.read_text()
    gpu=once(gpu,"long GPUdmaChain(uint32_t *rambase, uint32_t start_addr,",
             GPU_EXTERN+"long GPUdmaChain(uint32_t *rambase, uint32_t start_addr,",
             "native single list seven-node traversal declarations")
    anchor="    addr = LE32TOH(list[0]) & 0xffffff;\n"
    gpu=once(gpu,anchor,anchor+GPU_NODE,
             "verify actual native seven-node CPU-authored list order")
    gpulib.write_text(gpu)

    source=unai.read_text()
    source=once(source,
       '#include "../../libpcsxcore/vh115_sample_identity.h"\n',
       '#include "../../libpcsxcore/vh115_sample_identity.h"\n'+UNAI_EXTERN,
       "extern C aggregate intermediate GPU sample proof")
    anchor="        vh115_note(vh115_post,24u,changed);\n"
    source=once(source,anchor,anchor+UNAI_INTERMEDIATE,
                "check all 16 native VRAM pixels after each of 5 Unai GPU draws")
    unai.write_text(source)

    src=frontend.read_text()
    src=once(src,"\tint vh123_mips_dma2_list_smoke = 0;\n",
             "\tint vh123_mips_dma2_list_smoke = 0;\n"
             "\tint vh124_mips_one_list_smoke = 0;\n",
             "separate MIPS five-GP0 in-one-list test flag")
    old='\t\telse if (!strcmp(argv[i], "--vh123-mips-gpu-list-return-smoke"))\n'
    src=once(src,old,
             '\t\telse if (!strcmp(argv[i], "--vh124-mips-one-list-return-smoke"))\n'
             '\t\t\tvh124_mips_one_list_smoke=1;\n'+old,
             "opt-in original MIPS single-DMA five-GP0 executable")
    _,stops,_,_=build()
    src=once(src,"\tif (loadst_f) {\n",
             oracle_source(stops)+"\tif (loadst_f) {\n",
             "verify one real MIPS GPU linked list with five interim VRAM states")
    frontend.write_text(src)
    return dict(proof,
        one_actual_mips_started_linked_list_dma2=True,
        seven_real_linked_list_nodes_visited=True,
        five_real_unai_draw_callbacks=True,
        five_in_native_unai_intermediate_vram_pixel_checks=True,
        no_host_authored_gp0_packets=True,
        canonical_private_v82_journal_unchanged=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
