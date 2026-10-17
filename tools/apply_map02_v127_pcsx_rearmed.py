#!/usr/bin/env python3
"""Four genuine emulator VBlank profiles across the same three MIPS GPU DMA lists.

Execute the original synthetic MIPS NOP loop for 0, 1 or 2 *real*
psxRcntUpdate GPU_vBlank callbacks between DMA lists. Native v119/v116
counters independently classify five ordered post-Unai samples.
"""
from pathlib import Path
from .apply_map02_v126_pcsx_rearmed import apply as apply_v126
from .apply_map02_v125_pcsx_rearmed import oracle_source as v125_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v127_variable_vblank_exe import build

WAIT=r"""
            if(phase<2u){
                /* Run the *same* CPU NOP pad for the requested number
                 * of genuinely observed psxRcntUpdate callback edges.
                 * A zero gap executes zero wait blocks, not a fake edge. */
                unsigned int target=vh127_boundary_targets[vh127_vblank_mode][phase];
                unsigned int resume_pc=psxRegs.pc;
                unsigned int before=vh78_vblank_observed_count;
                for(unsigned int edge=0u;edge<target;edge++){
                    unsigned int cycle_before=psxRegs.cycle;
                    unsigned int spin_blocks=0;
                    while(vh78_vblank_observed_count==before+edge &&
                          spin_blocks<8000u){
                        psxRegs.pc=VH127_WAIT_PC;
                        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
                        if(psxRegs.pc!=VH127_WAIT_PC){
                            SysPrintf("VH127_WAIT_PC_REFUSED phase=%u edge=%u\n",
                                      phase,edge);
                            ClosePlugins();SysClose();menu_finish();plat_finish();return 42;
                        }
                        spin_blocks++;
                    }
                    if(vh78_vblank_observed_count!=before+edge+1u ||
                       vh78_vblank_last_cycle<=cycle_before ||
                       vh78_vblank_last_hsync==0u ||
                       (real_edges_seen>0u &&
                        vh78_vblank_last_frame!=last_real_frame+1u) ||
                       (real_edges_seen>0u &&
                        vh78_vblank_last_cycle<=last_real_cycle)){
                        SysPrintf("VH127_GENUINE_EDGE_REFUSED phase=%u edge=%u blocks=%u\n",
                                  phase,edge,spin_blocks);
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 42;
                    }
                    last_real_frame=vh78_vblank_last_frame;
                    last_real_cycle=vh78_vblank_last_cycle;
                    real_edges_seen++;
                }
                psxRegs.pc=resume_pc;
                if(vh78_vblank_observed_count!=initial_vblank+real_edges_seen ||
                   real_edges_seen!=expected_total_edges[ vh127_vblank_mode ]*
                       (phase==1u) +
                       (phase==0u ? target : 0u)){
                    SysPrintf("VH127_EDGE_TOTAL_REFUSED phase=%u\n",phase);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 42;
                }
                vh115_metrics after_wait={0};
                if(vh115_get_metrics(&after_wait)!=0 ||
                   after_wait.vblank_edges!=real_edges_seen ||
                   after_wait.handlers!=cumulative_draws[phase]){
                    SysPrintf("VH127_EDGE_BINDING_REFUSED phase=%u\n",phase);
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 42;
                }
            }
"""


def oracle_source(stops,wait_pc):
    src=v125_oracle(stops)
    src=once(src,"if(vh125_mips_variable_dma_smoke) {",
             "if(vh127_vblank_mode>=0) {",
             "one of four isolated genuine VBlank wait modes")
    src=once(src,'memcmp(tag,"VH125SY!",sizeof(tag))==0',
             'memcmp(tag,"VH127SY!",sizeof(tag))==0',
             "require original v127 synthetic PS-X EXE signature")
    src=src.replace("VH125_","VH127_")
    anchor="        static const unsigned cumulative_draws[3]={1u,3u,5u};\n"
    declaration=r"""        static const unsigned vh127_boundary_targets[4][2]={
            {0u,0u}, {1u,1u}, {0u,2u}, {2u,0u}
        };
        static const unsigned vh127_adjacent_histograms[4][3]={
            {4u,0u,0u}, {2u,2u,0u},
            {3u,0u,1u}, {3u,0u,1u}
        };
        static const unsigned expected_total_edges[4]={0u,2u,2u,2u};
        static const unsigned return_gap[4]={0u,2u,2u,2u};
"""
    src=once(src,anchor,anchor+declaration,
             "four distinct genuine callback gap profiles")
    src=once(src,"        vh125_dma_enabled=1;\n",
             "        vh125_dma_enabled=1;\n"
             "        if(vh127_vblank_mode>3){\n"
             "            SysPrintf(\"VH127_MODE_REFUSED\\n\");\n"
             "            ClosePlugins();SysClose();menu_finish();plat_finish();return 42;\n"
             "        }\n"
             "        const unsigned initial_vblank=vh78_vblank_observed_count;\n"
             "        unsigned int real_edges_seen=0u;\n"
             "        unsigned int last_real_cycle=0u,last_real_frame=0u;\n",
             "isolate observed frame count for current synthetic CPU program")
    src=once(src,"        }\n        vh125_dma_enabled=0;\n",
             WAIT+"        }\n        vh125_dma_enabled=0;\n",
             "execute bounded real MIPS wait after DMA phase one and two")
    src=once(src,"native.handlers!=5u || native.vblank_edges!=0u ||",
             "native.handlers!=5u ||\n"
             "           native.vblank_edges!=expected_total_edges[vh127_vblank_mode] ||",
             "require actual zero/two native VBlank callback counts")
    src=once(src,"quints.returned_to_four_back[0]!=1u",
             "quints.returned_to_four_back[return_gap[vh127_vblank_mode]]!=1u",
             "dynamic v119 exact sampled VRAM return gap classification")
    src=once(src,"(gap>0u && quints.returned_to_four_back[gap])",
             "(gap!=return_gap[vh127_vblank_mode] &&\n"
             "                quints.returned_to_four_back[gap])",
             "reject all incorrect sampled-value four-back bins")
    extras=r"""
        vh116_gap_metrics gaps={0};
        if(vh116_get_gap_metrics(&gaps)!=0 ||
           vh78_vblank_observed_count!=
               initial_vblank+expected_total_edges[vh127_vblank_mode]){
            SysPrintf("VH127_GAP_TOTAL_REFUSED\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 42;
        }
        for(unsigned int gap=0u;gap<=VH116_MAX_VBLANK_GAP;gap++){
            const unsigned count=gaps.equal_count_identical[gap]+
                gaps.equal_count_different[gap]+gaps.different_count[gap];
            const unsigned expected=(gap<3u?
               vh127_adjacent_histograms[vh127_vblank_mode][gap]:0u);
            if(count!=expected){
                SysPrintf("VH127_GAP_HISTOGRAM_REFUSED gap=%u\n",gap);
                ClosePlugins();SysClose();menu_finish();plat_finish();return 42;
            }
        }
"""
    src=once(src,"        vh115_reset();\n",extras+"        vh115_reset();\n",
             "independently verify adjacent handler gaps for each profile")

    old=("VH127_VARIABLE_DMA_PASS stages=4 dma=3 nodes=10 words=15 "
         "unai=5 intermediate=5 readbacks=1 four_back=1 vblanks=0 erased=1")
    new=("VH127_REAL_VBLANK_PROFILES_PASS mode=%u gaps=%u,%u,%u,%u "
         "stages=4 dma=3 nodes=10 words=15 unai=5 intermediate=5 "
         "real_vblanks=%u four_back_gap=%u erased=1")
    if old not in src:
        raise ValueError("v125 output evidence marker missing")
    src=src.replace(
        'SysPrintf("'+old+'\\n");',
        'SysPrintf("'+new+'\\n",vh127_vblank_mode,'
        'vh127_boundary_targets[vh127_vblank_mode][0],0u,'
        'vh127_boundary_targets[vh127_vblank_mode][1],0u,'
        'expected_total_edges[vh127_vblank_mode],'
        'return_gap[vh127_vblank_mode]);'
    )
    # Executable C instruction sites are replaced, not diagnostic strings.
    src=src.replace("psxRegs.pc=VH127_WAIT_PC;",
                    f"psxRegs.pc=0x{wait_pc:08x}u;")
    src=src.replace("psxRegs.pc!=VH127_WAIT_PC)",
                    f"psxRegs.pc!=0x{wait_pc:08x}u)")
    if "VH127_WAIT_PC;" in src or "VH127_VARIABLE_DMA_PASS" in src:
        raise ValueError("unfinished v127 native oracle substitution")
    return src


def apply(root:Path):
    original=apply_v126(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,"\tint vh126_mips_vblank_dma_smoke = 0;\n",
             "\tint vh126_mips_vblank_dma_smoke = 0;\n"
             "\tint vh127_vblank_mode = -1;\n",
             "new independent v127 genuine-VBlank matrix, v126 unchanged")
    flags=(
        ("--vh127-vblank-00",0),("--vh127-vblank-11",1),
        ("--vh127-vblank-02",2),("--vh127-vblank-20",3),
    )
    old='\t\telse if (!strcmp(argv[i], "--vh126-mips-vblank-dma-smoke"))\n'
    added="".join(
        f'\t\telse if (!strcmp(argv[i], "{flag}"))\n'
        f'\t\t\tvh127_vblank_mode={mode};\n'
        for flag,mode in flags
    )
    src=once(src,old,added+old,
             "four deliberate CLI modes 0/0 1/1 0/2 2/0")
    _,stops,_,_,wait_pc=build()
    src=once(src,"\tif (loadst_f) {\n",
             oracle_source(stops,wait_pc)+"\tif (loadst_f) {\n",
             "four real VBlank gap profiles on native MIPS GPU DMA lists")
    frontend.write_text(src)
    return dict(original,
        original_v126_real_vblank_witness_unmodified=True,
        v127_real_vblank_gap_profiles=["00","11","02","20"],
        no_synthetic_gpu_vblank_or_cpu_cycle_mutation=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("checkout",type=Path)
    print(apply(parser.parse_args().checkout))
