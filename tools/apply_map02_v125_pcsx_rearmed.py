#!/usr/bin/env python3
"""Native pinned PCSX witness: 3 MIPS-started variable GPU linked lists.

Uses the already proven v124 Unai post-handler intermediate VRAM check.
Counts actual psxDma2 invocations and individual GPUdmaChain node
traversals; never exports packet words or VRAM pixels.
"""
from pathlib import Path
from .apply_map02_v124_pcsx_rearmed import apply as apply_v124
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v125_variable_gpu_dma_exe import build,MARKERS,BASES

DMA_DECL=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
unsigned int vh125_dma_enabled;
unsigned int vh125_dma_count;
unsigned int vh125_dma_bad;
unsigned int vh125_node_count;
unsigned int vh125_node_words;
#endif
"""
DMA_OBSERVE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
            if(vh125_dma_enabled) {
                static const unsigned start[3]={0x12000u,0x13000u,0x14000u};
                if(vh125_dma_count<3u &&
                   madr==start[vh125_dma_count] &&
                   bcr==0u && chcr==0x01000401u)
                    vh125_dma_count++;
                else
                    vh125_dma_bad++;
            }
#endif
"""
GPU_EXTERN=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
extern unsigned int vh125_dma_enabled;
extern unsigned int vh125_dma_count;
extern unsigned int vh125_dma_bad;
extern unsigned int vh125_node_count;
extern unsigned int vh125_node_words;
#endif
"""
GPU_NODE=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh125_dma_enabled) {
        static const unsigned where_required[10]={
            0x12000u,0x12100u,0x12200u,
            0x13000u,0x13100u,0x13200u,
            0x14000u,0x14100u,0x14200u,0x14300u
        };
        static const unsigned words_required[10]={
            0u,3u,0u,0u,6u,0u,0u,3u,3u,0u
        };
        static const unsigned next_required[10]={
            0x12100u,0x12200u,0x800000u,
            0x13100u,0x13200u,0x800000u,
            0x14100u,0x14200u,0x14300u,0x800000u
        };
        unsigned slot=vh125_node_count;
        unsigned where=(unsigned)((list-rambase)*4);
        if(slot>=10u || where!=where_required[slot] ||
           (unsigned)len!=words_required[slot] ||
           addr!=next_required[slot])
            vh125_dma_bad++;
        else {
            vh125_node_count++;
            vh125_node_words+=(unsigned)len;
        }
    }
#endif
"""


def oracle_source(stops):
    pcs="{"+",".join(f"0x{x:08x}u" for x in stops)+"}"
    marks="{"+",".join(f"0x{x:08x}u" for x in MARKERS)+"}"
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh125_mips_variable_dma_smoke) {
        extern unsigned int vh125_dma_enabled;
        extern unsigned int vh125_dma_count;
        extern unsigned int vh125_dma_bad;
        extern unsigned int vh125_node_count;
        extern unsigned int vh125_node_words;
        extern unsigned int vh124_intermediate_enabled;
        extern unsigned int vh124_intermediate_seen;
        extern unsigned int vh124_intermediate_rejected;
        static const uint32_t vh125_stops[4]=VH125_STOPS;
        static const uint32_t vh125_marks[4]=VH125_MARKS;
        static const unsigned cumulative_nodes[3]={3u,6u,10u};
        static const unsigned cumulative_words[3]={3u,9u,15u};
        static const unsigned cumulative_draws[3]={1u,3u,5u};
        unsigned char tag[8]={0};
        FILE *exe=file[0]?fopen(file,"rb"):NULL;
        int valid=0;
        if(exe){
            if(fseek(exe,0x4c,SEEK_SET)==0 &&
               fread(tag,1,sizeof(tag),exe)==sizeof(tag) &&
               memcmp(tag,"VH125SY!",sizeof(tag))==0)
                valid=1;
            fclose(exe);
        }
        if(!valid || !ready_to_go || Config.Cpu!=1 ||
           psxRegs.pc!=0x80010000u || !GPU_freeze ||
           !psxRegs.ptrs.psxM){
            SysPrintf("VH125_EXE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
        }
        unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
        /* Execute GPU setup as an original interpreted MIPS stage. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
        unsigned int off=0x111a0u;
        uint32_t marker=(uint32_t)ram[off]|
            ((uint32_t)ram[off+1]<<8)|
            ((uint32_t)ram[off+2]<<16)|
            ((uint32_t)ram[off+3]<<24);
        if(psxRegs.pc!=vh125_stops[0] || marker!=vh125_marks[0]){
            SysPrintf("VH125_SETUP_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
        }
        GPUFreeze_t initial={0};
        uint16_t *initial_pixels=NULL;
        if(GPU_freeze(1,&initial,&initial_pixels)!=1 || !initial_pixels){
            SysPrintf("VH125_SETUP_DRAIN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
        }
        vh80_reset();
        vh84_set_sampling(1);
        vh115_enable(1);
        vh125_dma_count=0;
        vh125_dma_bad=0;
        vh125_node_count=0;
        vh125_node_words=0;
        vh124_intermediate_seen=0;
        vh124_intermediate_rejected=0;
        vh124_intermediate_enabled=1;
        vh125_dma_enabled=1;
        /* DMA phases: A | B,C (one 6-word node) | D,A (two nodes).
         * Check Unai's 16-pixel in-hook state at each phase boundary. */
        for(unsigned int phase=0;phase<3u;phase++){
            psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
            off=0x111a0u+4u*(phase+1u);
            marker=(uint32_t)ram[off]|
                ((uint32_t)ram[off+1]<<8)|
                ((uint32_t)ram[off+2]<<16)|
                ((uint32_t)ram[off+3]<<24);
            if(psxRegs.pc!=vh125_stops[phase+1u] ||
               marker!=vh125_marks[phase+1u]){
                SysPrintf("VH125_MIPS_PHASE_REFUSED phase=%u\n",phase);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
            }
            if(vh125_dma_count!=phase+1u || vh125_dma_bad!=0u ||
               vh125_node_count!=cumulative_nodes[phase] ||
               vh125_node_words!=cumulative_words[phase] ||
               vh124_intermediate_seen!=cumulative_draws[phase] ||
               vh124_intermediate_rejected!=0u){
                SysPrintf("VH125_DMA_CHAIN_REFUSED phase=%u dma=%u nodes=%u words=%u draws=%u bad=%u\n",
                     phase,vh125_dma_count,vh125_node_count,
                     vh125_node_words,vh124_intermediate_seen,
                     vh125_dma_bad+vh124_intermediate_rejected);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
            }
        }
        vh125_dma_enabled=0;
        vh124_intermediate_enabled=0;
        GPUFreeze_t final={0};
        uint16_t *vram=NULL;
        if(GPU_freeze(1,&final,&vram)!=1 || !vram){
            SysPrintf("VH125_FINAL_READBACK_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
        }
        for(unsigned int y=160u;y<164u;y++)
            for(unsigned int x=40u;x<44u;x++)
                if(vram[y*1024u+x]!=0x001fu){
                    SysPrintf("VH125_FINAL_PIXEL_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
                }
        vh115_metrics native={0};
        vh119_quintuplet_metrics quints={0};
        if(vh115_get_metrics(&native)!=0 ||
           vh119_get_quintuplet_metrics(&quints)!=0 ||
           native.handlers!=5u || native.vblank_edges!=0u ||
           quints.consecutive_quintuplets!=1u ||
           quints.returned_to_four_back[0]!=1u){
            SysPrintf("VH125_RETURN_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
        }
        for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++)
            if(quints.same_as_previous[gap] ||
               quints.returned_to_two_back[gap] ||
               quints.returned_to_three_back[gap] ||
               quints.different_from_all_four[gap] ||
               (gap>0u && quints.returned_to_four_back[gap])){
                SysPrintf("VH125_RETURN_BINS_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
            }
        vh115_reset();
        if(!vh115_sample_cache_erased()){
            SysPrintf("VH125_CACHE_ERASE_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 40;
        }
        SysPrintf("VH125_VARIABLE_DMA_PASS stages=4 dma=3 nodes=10 words=15 unai=5 intermediate=5 readbacks=1 four_back=1 vblanks=0 erased=1\n");
        ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
    }
#endif

""".replace("VH125_STOPS",pcs).replace("VH125_MARKS",marks)


def apply(root:Path):
    proof=apply_v124(root)
    base=root.resolve()
    dmafile=base/"libpcsxcore/psxdma.c"
    gpulib=base/"plugins/gpulib/gpu.c"
    frontend=base/"frontend/main.c"

    dma=dmafile.read_text()
    dma=once(dma,"unsigned int vh124_intermediate_rejected;\n",
        "unsigned int vh124_intermediate_rejected;\n"+DMA_DECL,
        "new bounded three-list DMA counters distinct from v124")
    dma=once(dma,"\t\tcase 0x01000401: // dma chain\n",
        "\t\tcase 0x01000401: // dma chain\n"+DMA_OBSERVE,
        "count three real MIPS linked-list DMA starts by address")
    dmafile.write_text(dma)

    gpu=gpulib.read_text()
    gpu=once(gpu,"long GPUdmaChain(uint32_t *rambase, uint32_t start_addr,",
        GPU_EXTERN+"long GPUdmaChain(uint32_t *rambase, uint32_t start_addr,",
        "native variable-node expected traversal declaration")
    anchor="    addr = LE32TOH(list[0]) & 0xffffff;\n"
    gpu=once(gpu,anchor,anchor+GPU_NODE,
             "verify native 3+3+4 nodes and 3/6/3+3 GPU words")
    gpulib.write_text(gpu)

    src=frontend.read_text()
    src=once(src,"\tint vh124_mips_one_list_smoke = 0;\n",
        "\tint vh124_mips_one_list_smoke = 0;\n"
        "\tint vh125_mips_variable_dma_smoke = 0;\n",
        "add separate v125 synthetic MIPS variable-list opt-in")
    old='\t\telse if (!strcmp(argv[i], "--vh124-mips-one-list-return-smoke"))\n'
    src=once(src,old,
        '\t\telse if (!strcmp(argv[i], "--vh125-mips-variable-dma-smoke"))\n'
        '\t\t\tvh125_mips_variable_dma_smoke=1;\n'+old,
        "new separate three DMA starting-address fixture")
    _,stops,_,_=build()
    src=once(src,"\tif (loadst_f) {\n",
        oracle_source(stops)+"\tif (loadst_f) {\n",
        "actual CPU DMA2 starts and five in-native Unai states")
    frontend.write_text(src)
    return dict(proof,
        three_actual_mips_linked_list_dma_transfers=True,
        different_list_start_addresses=True,
        one_six_word_node_contains_two_gpu_draw_packets=True,
        native_unai_intermediate_pixel_checks_five=True,
        no_host_gpu_draw_submissions=True,
        canonical_private_v82_journal_untouched=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
