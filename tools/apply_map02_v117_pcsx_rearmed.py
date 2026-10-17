#!/usr/bin/env python3
"""v117: add native A-B-A exact sample return counts to pinned Unai.

Only integer counters are emitted; same original v82 private JSONL.
"""
from pathlib import Path
from .apply_map02_v116_pcsx_rearmed import apply as apply_v116
from .apply_map02_v69_pcsx_rearmed import once


def apply(root: Path):
    proof=apply_v116(root)
    frontend=root.resolve()/"frontend/main.c"
    text=frontend.read_text()
    anchor=('            if(vh83_renderer_smoke)\n'
            '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);')
    addition=(
        '            if(vh104_content_smoke) {\n'
        '                vh117_triplet_metrics triplets;\n'
        '                if(vh117_get_triplet_metrics(&triplets)!=0 ||\n'
        '                   triplets.consecutive_triplets+2u!=observed_unai) {\n'
        '                    SysPrintf("VH117_TRIPLETS_REFUSED\\n");\n'
        '                    ClosePlugins();SysClose();menu_finish();plat_finish();return 33;\n'
        '                }\n'
        '                SysPrintf("VH117_TRIPLETS_PASS triples=%u g0=%u,%u,%u g1=%u,%u,%u g2=%u,%u,%u g3=%u,%u,%u g4=%u,%u,%u\\n",\n'
        '                    triplets.consecutive_triplets,\n'
        '                    triplets.same_as_previous[0],triplets.returned_to_two_back[0],triplets.different_from_both[0],\n                    triplets.same_as_previous[1],triplets.returned_to_two_back[1],triplets.different_from_both[1],\n                    triplets.same_as_previous[2],triplets.returned_to_two_back[2],triplets.different_from_both[2],\n                    triplets.same_as_previous[3],triplets.returned_to_two_back[3],triplets.different_from_both[3],\n                    triplets.same_as_previous[4],triplets.returned_to_two_back[4],triplets.different_from_both[4]);\n'
        '            }\n'
    )
    text=once(text,anchor,addition+anchor,
              "v117 exact A-B-A native 24-point post-handler values")
    frontend.write_text(text)
    return dict(proof,
        verified_three_consecutive_unai_post_handler_sample_values=True,
        only_aggregate_return_counts_exposed=True,
        complete_vram_or_physical_frame_persistence_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
