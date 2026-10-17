#!/usr/bin/env python3
"""Additional host-submitted GP0 draw commands, in the ACTUAL pinned Unai GPU.

A->B->C->D->A restores the 24-point sample's first state. The fixture
runs AFTER the canonical private v82 JSONL has been published, and is
never described as MIPS-authored, retail MAP02, or hardware VBlank.
Only aggregate status, not pixel values, enters stdout.
"""
from pathlib import Path
from .apply_map02_v119_pcsx_rearmed import apply as apply_v119
from .apply_map02_v69_pcsx_rearmed import once

FIXTURE=r"""
            if(vh104_content_smoke) {
                /* Separate HOST-SUBMITTED GP0 fixture, after the original
                 * canonical private JSONL was published and prior metrics
                 * were already checked. Does NOT forge a VBlank event. */
                const uint32_t vh120_commands[5]={
                    0x600000ffu,0x6000ff00u,0x60ff0000u,
                    0x6000ffffu,0x600000ffu
                };
                const uint16_t vh120_expected[5]={
                    0x001fu,0x03e0u,0x7c00u,0x03ffu,0x001fu
                };
                vh115_reset();
                if(!vh115_sample_cache_erased()){
                    SysPrintf("VH120_RESET_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 36;
                }
                vh115_enable(1);
                unsigned int vh120_verified=0;
                for(unsigned int i=0;i<5u;i++){
                    /* GP0(60): flat 4x4 opaque rectangle in sample
                     * column x=40, rows y=160..163. Native readback
                     * is checked after the actual Unai draw. */
                    uint32_t packet[3]={
                        vh120_commands[i],
                        (160u<<16)|40u,
                        (4u<<16)|4u
                    };
                    GPU_writeDataMem(packet,3);
                    GPUFreeze_t freeze_state={0};
                    uint16_t *native_pixels=NULL;
                    if(GPU_freeze(1,&freeze_state,&native_pixels)!=1 ||
                       !native_pixels){
                        SysPrintf("VH120_VRAM_FREEZE_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 36;
                    }
                    for(unsigned int dy=0;dy<4u;dy++){
                        for(unsigned int dx=0;dx<4u;dx++){
                            if(native_pixels[(160u+dy)*1024u+40u+dx]!=
                               vh120_expected[i]){
                                SysPrintf("VH120_VRAM_PIXEL_REFUSED phase=%u\n",i);
                                ClosePlugins();SysClose();menu_finish();plat_finish();return 36;
                            }
                        }
                    }
                    vh120_verified++;
                }
                vh115_metrics native;
                vh119_quintuplet_metrics five;
                if(vh115_get_metrics(&native)!=0 ||
                   vh119_get_quintuplet_metrics(&five)!=0 ||
                   native.handlers!=5u || native.vblank_edges!=0u ||
                   vh120_verified!=5u || five.consecutive_quintuplets!=1u ||
                   five.returned_to_four_back[0]!=1u){
                    SysPrintf("VH120_NATIVE_RETURN_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 36;
                }
                for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++){
                    if(five.same_as_previous[gap] ||
                       five.returned_to_two_back[gap] ||
                       five.returned_to_three_back[gap] ||
                       five.different_from_all_four[gap] ||
                       (gap!=0u && five.returned_to_four_back[gap])){
                        SysPrintf("VH120_NATIVE_BINS_REFUSED\n");
                        ClosePlugins();SysClose();menu_finish();plat_finish();return 36;
                    }
                }
                vh115_reset();
                if(!vh115_sample_cache_erased()){
                    SysPrintf("VH120_ERASURE_REFUSED\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 36;
                }
                SysPrintf("VH120_GP0_RETURN_PASS commands=5 native_handlers=5 exact_four_back=1 readbacks=5 erased=1 vblanks=0\n");
            }
"""


def apply(root: Path):
    proof=apply_v119(root)
    frontend=root.resolve()/"frontend/main.c"
    source=frontend.read_text()
    # The old VH82 export status *also* measures vh80_count() and is
    # printed after v119 metrics. Do not disturb that published count:
    # append fixture only before the final v78 success line.
    anchor=(
        'SysPrintf("VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380 '
        'gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1\\n");'
    )
    source=once(source,anchor,FIXTURE.lstrip("\n")+anchor,
                "native GP0 return only after canonical journal AND original export status")
    frontend.write_text(source)
    return dict(proof,
        five_real_host_submitted_gp0_rectangles_executed_inside_pinned_unai=True,
        canonical_private_v82_journal_published_before_v120_fixture=True,
        host_commands_not_mips_authored=True,
        no_additional_emulator_vblank_forged=True,
        raw_vram_pixel_values_never_exported=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
