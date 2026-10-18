#!/usr/bin/env python3
"""v164: independently verify five genuine guest-MIPS GP0 rectangles in VRAM.

Extends *existing* v121 source-authored interpreted PS-X EXE experiment.
The host only captures GPU VRAM via GPU_freeze; it never submits GP0 draw
commands in this mode. Checks five per-stage 4x4 pixel changes plus 20
untouched border pixels, with original CPU-written markers and PC gates kept.
This is a synthetic MIPS scene, not original retail Vandal Hearts MAP02.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v163_host_unai_rectangle import apply as apply_v163
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v121_mips_gp0_return_exe import build, COLORS, EXPECTED_PIXELS

MAIN="int main(int argc, char *argv[])\n"
FLAG="\tint vh121_mips_return_smoke = 0;\n"
CLI='\t\telse if (!strcmp(argv[i], "--vh121-mips-gp0-return-smoke"))\n'
ARM="    if(vh121_mips_return_smoke) {\n"
BASELINE=(
    "        vh80_reset();\n"
    "        vh84_set_sampling(1);\n"
    "        vh115_enable(1);\n"
    "        unsigned int readbacks=0;"
)
PHASE=(
    '                        SysPrintf("VH121_VRAM_REFUSED phase=%u\\n",phase);\n'
    "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 37;\n"
    "                    }\n"
    "            vh115_metrics metrics={0};"
)
PASS='        SysPrintf("VH121_MIPS_GP0_RETURN_PASS stages=6'


def halo_validator_c() -> str:
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Read-only observer. Count one 4x4 exact changed rectangle and
 * twenty completely unchanged neighboring pixels per MIPS stage. */
static int vh164_check_mips_halo(uint16_t previous[36],
                                 const uint16_t *vram, uint16_t expected,
                                 unsigned *changed, unsigned *border)
{
    unsigned inner=0u, outer=0u;
    if(!previous || !vram || !changed || !border) return -1;
    for(unsigned y=0u;y<6u;y++)
        for(unsigned x=0u;x<6u;x++){
            const uint16_t actual=vram[(159u+y)*1024u+39u+x];
            const uint16_t old=previous[y*6u+x];
            if(x>=1u && x<=4u && y>=1u && y<=4u){
                if(actual!=expected || actual==old) return -1;
                inner++;
            } else {
                if(actual!=old) return -1;
                outer++;
            }
        }
    if(inner!=16u || outer!=20u) return -1;
    for(unsigned y=0u;y<6u;y++)
        for(unsigned x=0u;x<6u;x++)
            previous[y*6u+x]=vram[(159u+y)*1024u+39u+x];
    *changed+=inner;
    *border+=outer;
    return 0;
}
#endif

"""


def patch_frontend(source: str) -> str:
    if "vh164_check_mips_halo" in source:
        raise ValueError("refuse duplicate MIPS-authored halo witness")
    raw, stops, ops, starts = build()
    if raw[:8]!=b"PS-X EXE" or raw[0x4c:0x54]!=b"VH121SY!" or \
       len(stops)!=6 or len(starts)!=6 or len(EXPECTED_PIXELS)!=5 or \
       tuple(COLORS)!=(0x600000ff,0x6000ff00,0x60ff0000,0x6000ffff,0x600000ff):
        raise ValueError("existing source-authored v121 guest executable changed")
    source=once(source,MAIN,halo_validator_c()+MAIN,
                "place bounded read-only halo checker at global C scope")
    source=once(source,FLAG,
                FLAG+"\tint vh164_mips_raster_bounds = 0;\n",
                "separate opt-in MIPS authored VRAM delta witness")
    source=once(source,CLI,
                '\t\telse if (!strcmp(argv[i], "--vh164-mips-vram-halo")) {\n'
                '\t\t\tvh121_mips_return_smoke=1;\n'
                '\t\t\tvh164_mips_raster_bounds=1;\n'
                '\t\t}\n'+CLI,
                "v164 flag always activates guest-MIPS v121, never host draw")
    source=once(source,ARM,ARM+
                "        if(vh164_mips_raster_bounds &&\n"
                "           (vh163_host_rectangle || vh158_five_instructions ||\n"
                "            vh158_mutate_fifth)) {\n"
                '            SysPrintf("VH164_MIXED_PROVENANCE_REFUSED\\n");\n'
                "            ClosePlugins();SysClose();menu_finish();plat_finish();return 68;\n"
                "        }\n",
                "reject simultaneous host-draw or disjoint native-fifth modes")
    source=once(source,BASELINE,
                "        uint16_t vh164_previous[36]={0};\n"
                "        unsigned vh164_changes=0u,vh164_neighbors=0u;\n"
                "        if(vh164_mips_raster_bounds)\n"
                "            for(unsigned y=0u;y<6u;y++)\n"
                "                for(unsigned x=0u;x<6u;x++)\n"
                "                    vh164_previous[y*6u+x]=\n"
                "                        setup_pixels[(159u+y)*1024u+39u+x];\n"
                +BASELINE,
                "snapshot six-by-six VRAM after MIPS-authored setup, before draws")
    source=once(source,PHASE,
                '                        SysPrintf("VH121_VRAM_REFUSED phase=%u\\n",phase);\n'
                "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 37;\n"
                "                    }\n"
                "            if(vh164_mips_raster_bounds &&\n"
                "               vh164_check_mips_halo(vh164_previous,vram,\n"
                "                                      vh121_colors[phase],\n"
                "                                      &vh164_changes,&vh164_neighbors)!=0){\n"
                '                SysPrintf("VH164_MIPS_HALO_REFUSED phase=%u\\n",phase);\n'
                "                ClosePlugins();SysClose();menu_finish();plat_finish();return 68;\n"
                "            }\n"
                "            vh115_metrics metrics={0};",
                "validate exact 16 changed pixels and 20 untouched neighbors for all five guest rectangles")
    source=once(source,PASS,
                "        if(vh164_mips_raster_bounds){\n"
                "            if(vh164_changes!=80u || vh164_neighbors!=100u ||\n"
                "               readbacks!=5u){\n"
                '                SysPrintf("VH164_GUEST_RASTER_COUNT_REFUSED\\n");\n'
                "                ClosePlugins();SysClose();menu_finish();plat_finish();return 68;\n"
                "            }\n"
                '            SysPrintf("VH164_GUEST_MIPS_UNAI_VRAM_PASS"'
                '" rectangles=5 changed=80 border=100"'
                '" host_draws=0 original_retail=0\\n");\n'
                "        }\n"+PASS,
                "only emit guest-MIPS raster marker after five pixel+border transitions")
    return source


def apply(root: Path):
    proof=apply_v163(root)
    front=root.resolve()/"frontend/main.c"
    front.write_text(patch_frontend(front.read_text()))
    return dict(proof,
        v164_source_authored_guest_MIPS_rectangles=5,
        v164_per_rectangle_pixel_delta=16,
        v164_per_rectangle_untouched_border=20,
        v164_no_host_submitted_gp0=True,
        v164_retail_MAP02_frame_verified=False,
        v164_nintendo_switch_raster_verified=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
