#!/usr/bin/env python3
"""v118: native exact 24-point four-handler returns, aggregate-only stdout."""
from pathlib import Path
from .apply_map02_v117_pcsx_rearmed import apply as apply_v117
from .apply_map02_v69_pcsx_rearmed import once


def apply(root: Path):
    proof=apply_v117(root)
    frontend=root.resolve()/"frontend/main.c"
    source=frontend.read_text()
    anchor=('            if(vh83_renderer_smoke)\n'
            '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);')
    addition=(
        '            if(vh104_content_smoke) {\n'
        '                vh118_quadruplet_metrics quads;\n'
        '                if(vh118_get_quadruplet_metrics(&quads)!=0 ||\n'
        '                   quads.consecutive_quadruplets+3u!=observed_unai) {\n'
        '                    SysPrintf("VH118_QUADRUPLETS_REFUSED\\n");\n'
        '                    ClosePlugins();SysClose();menu_finish();plat_finish();return 34;\n'
        '                }\n'
        '                SysPrintf("VH118_QUADRUPLETS_PASS quads=%u g0=%u,%u,%u,%u g1=%u,%u,%u,%u g2=%u,%u,%u,%u g3=%u,%u,%u,%u g4=%u,%u,%u,%u\\n",\n'
        '                    quads.consecutive_quadruplets,\n'
        '                    quads.same_as_previous[0],\n                    quads.returned_to_two_back[0],\n                    quads.returned_to_three_back[0],\n                    quads.different_from_all_three[0],\n                    quads.same_as_previous[1],\n                    quads.returned_to_two_back[1],\n                    quads.returned_to_three_back[1],\n                    quads.different_from_all_three[1],\n                    quads.same_as_previous[2],\n                    quads.returned_to_two_back[2],\n                    quads.returned_to_three_back[2],\n                    quads.different_from_all_three[2],\n                    quads.same_as_previous[3],\n                    quads.returned_to_two_back[3],\n                    quads.returned_to_three_back[3],\n                    quads.different_from_all_three[3],\n                    quads.same_as_previous[4],\n                    quads.returned_to_two_back[4],\n                    quads.returned_to_three_back[4],\n                    quads.different_from_all_three[4]);\n'
        '            }\n'
    )
    source=once(source,anchor,addition+anchor,
                "v118 four consecutive Unai post-handler exact-value matches")
    frontend.write_text(source)
    return dict(proof,
        exact_four_callback_24_sample_value_return_witness=True,
        raw_pixel_values_or_hashes_published=False,
        canonical_v82_private_jsonl_unchanged=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
