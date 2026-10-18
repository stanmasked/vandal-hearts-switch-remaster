#!/usr/bin/env python3
"""v163: opt-in HOST-submitted Unai VRAM rectangle, after native v162 proof.

This is deliberately NOT the fifth MIPS-authored E3 command: that word
only sets GPU state and cannot draw. The extra seven GP0 words are sent
by a separate, explicitly named host-only test, never attributed to the
game, source-authored guest MIPS or a Nintendo Switch renderer.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v162_gpulib_parse_flush import apply as apply_v162
from .apply_map02_v69_pcsx_rearmed import once

MARKER='                    SysPrintf("VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS"'
VALIDATE="    if((vh158_five_instructions || vh158_mutate_fifth) &&\n"
FLAG="\tint vh158_five_instructions = 0;\n"
PARSE='\t\telse if (!strcmp(argv[i], "--vh158-five-instructions"))\n'


def host_only_gpu_smoke_c() -> str:
    return r'''
                    if(vh163_host_rectangle){
                        /* All v158-v162 source-linked witnesses have
                         * already been disarmed and validated here.
                         * The following draw commands are HOST-authored. */
                        if(!GPU_freeze || !GPU_writeDataMem || !GPU_readStatus){
                            SysPrintf("VH163_HOST_GPU_API_REFUSED\n");
                            ClosePlugins();SysClose();menu_finish();plat_finish();return 67;
                        }
                        GPUFreeze_t vh163_state={0};
                        uint16_t *vh163_vram=NULL;
                        if(GPU_freeze(1,&vh163_state,&vh163_vram)!=1 ||
                           !vh163_vram){
                            SysPrintf("VH163_HOST_GPU_BEFORE_REFUSED\n");
                            ClosePlugins();SysClose();menu_finish();plat_finish();return 67;
                        }
                        /* Observe a 6x6 bounding box at X=607..612,
                         * Y=447..452. Expect only the inner 4x4 red. */
                        uint16_t vh163_before[36];
                        for(unsigned int y=0;y<6u;y++)
                            for(unsigned int x=0;x<6u;x++)
                                vh163_before[y*6u+x]=
                                    vh163_vram[(447u+y)*1024u+607u+x];
                        for(unsigned int y=1;y<5u;y++)
                            for(unsigned int x=1;x<5u;x++)
                                if(vh163_before[y*6u+x]==0x001fu){
                                    SysPrintf("VH163_HOST_GPU_BASELINE_REFUSED\n");
                                    ClosePlugins();SysClose();menu_finish();plat_finish();return 67;
                                }
                        /* GP0 E3/E4/E5/E6 setup and one 60h rectangle.
                         * This array is NOT executed by guest MIPS. */
                        uint32_t vh163_rect[7]={
                            0xe3000000u,0xe407ffffu,0xe5000000u,0xe6000000u,
                            0x600000ffu,0x01c00260u,0x00040004u
                        };
                        GPU_writeDataMem(vh163_rect,7);
                        (void)GPU_readStatus();
                        if(GPU_freeze(1,&vh163_state,&vh163_vram)!=1 ||
                           !vh163_vram){
                            SysPrintf("VH163_HOST_GPU_AFTER_REFUSED\n");
                            ClosePlugins();SysClose();menu_finish();plat_finish();return 67;
                        }
                        unsigned int changed=0u,border_same=0u;
                        for(unsigned int y=0;y<6u;y++)
                            for(unsigned int x=0;x<6u;x++){
                                const uint16_t actual=
                                    vh163_vram[(447u+y)*1024u+607u+x];
                                if(x>=1u && x<=4u && y>=1u && y<=4u){
                                    if(actual==0x001fu && actual!=vh163_before[y*6u+x])
                                        changed++;
                                } else if(actual==vh163_before[y*6u+x])
                                    border_same++;
                            }
                        if(changed!=16u || border_same!=20u){
                            SysPrintf("VH163_HOST_GPU_PIXEL_REFUSED changed=%u border=%u\n",
                                      changed,border_same);
                            ClosePlugins();SysClose();menu_finish();plat_finish();return 67;
                        }
                        SysPrintf("VH163_HOST_ONLY_UNAI_VRAM_RECT_PASS"
                                  " pixels_changed=16 border_unchanged=20"
                                  " original_retail=0 mips_raster=0\n");
                    }
'''


def patch_frontend(source: str) -> str:
    if "vh163_host_rectangle" in source:
        raise ValueError("refusing duplicate host-only raster smoke")
    source=once(source,FLAG,
        FLAG+"\tint vh163_host_rectangle = 0;\n",
        "separate opt-in host raster mode state")
    source=once(source,PARSE,
        '\t\telse if (!strcmp(argv[i], "--vh163-host-unai-rectangle"))\n'
        '\t\t\tvh163_host_rectangle=1;\n'+PARSE,
        "parse explicit host-only rectangle flag")
    source=once(source,VALIDATE,
        "    if(vh163_host_rectangle &&\n"
        "       (!vh158_five_instructions || vh158_mutate_fifth ||\n"
        "        !vh156_verify_register_effects ||\n"
        "        !vh155_four_instructions || !vh150_bounded_instructions ||\n"
        "        vh152_mutate_post_verify || vh153_mutate_second_word ||\n"
        "        vh154_mutate_third_word || vh155_mutate_fourth_word ||\n"
        "        vh156_corrupt_t0_second || vh157_corrupt_t1_fourth)){\n"
        '        SysPrintf("VH163_INVALID_HOST_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 67;\n"
        "    }\n"+VALIDATE,
        "host-only smoke cannot run without validated native 5-opcode mode")
    source=once(source,MARKER,host_only_gpu_smoke_c()+MARKER,
        "render a host-submitted rectangle only after MIPS proof validated")
    return source


def apply(root: Path):
    proof=apply_v162(root)
    frontend=root.resolve()/"frontend/main.c"
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(proof,
        v163_host_only_gpulib_rectangle_probe_installed=True,
        v163_original_retail_gpu_rasterization_verified=False,
        v163_guest_mips_pixel_rasterization_verified=False,
        v163_switch_hd_parity_verified=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
