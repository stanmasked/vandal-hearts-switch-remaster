#!/usr/bin/env python3
"""v126: genuine GPU_vBlank events from interpreted MIPS time between DMA.

Keeps v125's exact 1+2+2 GPU linked lists and native intermediate Unai
value checks. Temporarily executes an original 512-NOP PS1 MIPS wait pad
until actual pinned psxRcntUpdate GPU_vBlank callback occurs; never
writes CPU cycles, VBlank counters or any fake timeline event.
"""
from pathlib import Path
from .apply_map02_v125_pcsx_rearmed import (
    apply as apply_v125, oracle_source as v125_oracle
)
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v126_vblank_dma_exe import build

WAIT=r"""
            if(phase<2u){
                /* Between native GPU DMA2 stages, execute only the
                 * interpreted NOP/JUMP wait pad. Genuine psxRcntUpdate
                 * must invoke GPU_vBlank(1,0); do not forge a VBlank. */
                unsigned int before=vh78_vblank_observed_count;
                unsigned int cycle_before=psxRegs.cycle;
                unsigned int next_dma_pc=psxRegs.pc;
                unsigned int waits=0;
                while(vh78_vblank_observed_count==before && waits<8000u){
                    psxRegs.pc=VH126_WAIT_PC;
                    psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
                    if(psxRegs.pc!=VH126_WAIT_PC){
                        SysPrintf("VH126_WAIT_PC_REFUSED phase=%u\n",phase);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 41;
                    }
                    waits++;
                }
                psxRegs.pc=next_dma_pc;
                if(vh78_vblank_observed_count!=before+1u ||
                   vh78_vblank_observed_count!=initial_vblank+phase+1u ||
                   vh78_vblank_last_cycle<=cycle_before ||
                   vh78_vblank_last_hsync==0u ||
                   (phase>0u && vh78_vblank_last_frame!=last_vblank_frame+1u)){
                    SysPrintf("VH126_REAL_VBLANK_REFUSED phase=%u waits=%u\n",
                        phase,waits);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 41;
                }
                last_vblank_frame=vh78_vblank_last_frame;
                vh115_metrics between={0};
                if(vh115_get_metrics(&between)!=0 ||
                   between.vblank_edges!=phase+1u ||
                   between.handlers!=cumulative_draws[phase]){
                    SysPrintf("VH126_VBLANK_BINDING_REFUSED phase=%u\n",phase);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 41;
                }
            }
"""


def oracle_source(stops,wait_pc):
    src=v125_oracle(stops)
    src=once(src,"if(vh125_mips_variable_dma_smoke) {",
             "if(vh126_mips_vblank_dma_smoke) {",
             "distinct v126 separate real-VBlank DMA test")
    src=once(src,'memcmp(tag,"VH125SY!",sizeof(tag))==0',
             'memcmp(tag,"VH126SY!",sizeof(tag))==0',
             "genuine VBlank synthetic original EXE signature")
    src=src.replace("VH125_","VH126_")
    src=once(src,"        vh125_dma_enabled=1;\n",
        "        vh125_dma_enabled=1;\n"
        "        unsigned int initial_vblank=vh78_vblank_observed_count;\n"
        "        unsigned int last_vblank_frame=0;\n",
        "track only VBlank events that occur after sample observer enabled")
    anchor="        }\n        vh125_dma_enabled=0;\n"
    src=once(src,anchor,WAIT+"        }\n        vh125_dma_enabled=0;\n",
             "genuine psxRcntUpdate VBlank wait after phases A and BC")
    src=once(src,"native.handlers!=5u || native.vblank_edges!=0u ||",
        "native.handlers!=5u || native.vblank_edges!=2u ||",
        "native exact sample lifetime includes two genuine VBlank events")
    src=once(src,"quints.returned_to_four_back[0]!=1u",
        "quints.returned_to_four_back[2]!=1u",
        "native exact return is classified in two-edge, not zero-edge bin")
    src=once(src,"(gap>0u && quints.returned_to_four_back[gap])",
        "(gap!=2u && quints.returned_to_four_back[gap])",
        "refuse misclassified four-back return in all other VBlank gaps")

    final_anchor="        vh115_reset();\n"
    bins=r"""
        vh116_gap_metrics gaps={0};
        if(vh116_get_gap_metrics(&gaps)!=0 ||
           vh78_vblank_observed_count!=initial_vblank+2u){
            SysPrintf("VH126_GAP_TOTAL_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 41;
        }
        for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++){
            const unsigned num=gaps.equal_count_identical[gap]+
                gaps.equal_count_different[gap]+gaps.different_count[gap];
            if(num!=(gap<2u?2u:0u)){
                SysPrintf("VH126_GAP_BINS_REFUSED\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 41;
            }
        }
"""
    src=once(src,final_anchor,bins+final_anchor,
             "cross-DMA adjacent handler gaps 1 0 1 0 independently verified")
    original=('VH126_VARIABLE_DMA_PASS stages=4 dma=3 nodes=10 words=15 '
              'unai=5 intermediate=5 readbacks=1 four_back=1 vblanks=0 erased=1')
    status=('VH126_GENUINE_VBLANK_DMA_PASS stages=4 dma=3 nodes=10 words=15 '
            'unai=5 intermediate=5 adjacent_gaps=1,0,1,0 '
            'real_vblanks=2 four_back_gap2=1 erased=1')
    src=once(src,original,status,
             "publish exclusively aggregate genuine two VBlank return witness")
    return src.replace("VH126_WAIT_PC",f"0x{wait_pc:08x}u")


def apply(root:Path):
    proof=apply_v125(root)
    front=root.resolve()/"frontend/main.c"
    src=front.read_text()
    src=once(src,"\tint vh125_mips_variable_dma_smoke = 0;\n",
        "\tint vh125_mips_variable_dma_smoke = 0;\n"
        "\tint vh126_mips_vblank_dma_smoke = 0;\n",
        "new independent pinned MIPS real-VBlank DMA option")
    old='\t\telse if (!strcmp(argv[i], "--vh125-mips-variable-dma-smoke"))\n'
    src=once(src,old,
        '\t\telse if (!strcmp(argv[i], "--vh126-mips-vblank-dma-smoke"))\n'
        '\t\t\tvh126_mips_vblank_dma_smoke=1;\n'+old,
        "separate unchanged legacy v125 command line")
    _,stops,_,_,wait_pc=build()
    src=once(src,"\tif (loadst_f) {\n",
        oracle_source(stops,wait_pc)+"\tif (loadst_f) {\n",
        "genuine psxRcntUpdate VBlank intervals between three native linked lists")
    front.write_text(src)
    return dict(proof,
        two_real_emulated_psxVBlank_callbacks_between_dma_phases=True,
        only_interpreted_mips_cpu_cycles_drive_vblank=True,
        no_cpu_cycle_or_hsync_counter_forgery=True,
        original_v125_gpu_dma_node_and_unai_hook_preserved=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
