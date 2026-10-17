#!/usr/bin/env python3
"""v119: bounded native 5-handler VRAM equality witness, only coarse totals."""
from pathlib import Path
from .apply_map02_v118_pcsx_rearmed import apply as apply_v118
from .apply_map02_v69_pcsx_rearmed import once


def apply(root: Path):
    proof=apply_v118(root)
    frontend=root.resolve()/"frontend/main.c"
    source=frontend.read_text()
    anchor=('            if(vh83_renderer_smoke)\n'
            '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);')
    addition=(
        '            if(vh104_content_smoke) {\n'
        '                vh119_quintuplet_metrics quints;\n'
        '                if(vh119_get_quintuplet_metrics(&quints)!=0 ||\n'
        '                   quints.consecutive_quintuplets+4u!=observed_unai) {\n'
        '                    SysPrintf("VH119_QUINTUPLETS_REFUSED\\n");\n'
        '                    ClosePlugins();SysClose();menu_finish();plat_finish();return 35;\n'
        '                }\n'
        '                SysPrintf("VH119_QUINTUPLETS_PASS quints=%u g0=%u,%u,%u,%u,%u g1=%u,%u,%u,%u,%u g2=%u,%u,%u,%u,%u g3=%u,%u,%u,%u,%u g4=%u,%u,%u,%u,%u\\n",\n'
        '                    quints.consecutive_quintuplets,\n'
        '                    quints.same_as_previous[0],\n                    quints.returned_to_two_back[0],\n                    quints.returned_to_three_back[0],\n                    quints.returned_to_four_back[0],\n                    quints.different_from_all_four[0],\n                    quints.same_as_previous[1],\n                    quints.returned_to_two_back[1],\n                    quints.returned_to_three_back[1],\n                    quints.returned_to_four_back[1],\n                    quints.different_from_all_four[1],\n                    quints.same_as_previous[2],\n                    quints.returned_to_two_back[2],\n                    quints.returned_to_three_back[2],\n                    quints.returned_to_four_back[2],\n                    quints.different_from_all_four[2],\n                    quints.same_as_previous[3],\n                    quints.returned_to_two_back[3],\n                    quints.returned_to_three_back[3],\n                    quints.returned_to_four_back[3],\n                    quints.different_from_all_four[3],\n                    quints.same_as_previous[4],\n                    quints.returned_to_two_back[4],\n                    quints.returned_to_three_back[4],\n                    quints.returned_to_four_back[4],\n                    quints.different_from_all_four[4]);\n'
        '            }\n'
    )
    source=once(source,anchor,addition+anchor,
                "v119 bounded five-callback exact 24-point sampled VRAM witness")
    frontend.write_text(source)
    return dict(proof,
        exact_five_callback_24_sample_value_witness=True,
        only_four_previous_24_value_buffers_retained=True,
        original_private_v82_jsonl_unchanged=True,
        raw_pixel_values_or_hashes_exported=False,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
