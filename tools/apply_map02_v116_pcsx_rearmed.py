#!/usr/bin/env python3
"""v116: publish aggregate exact-sample equality by number of VBlank edges.

Extends the v115 native-only 24-value comparison, not canonical JSONL.
"""
from pathlib import Path
from .apply_map02_v115_pcsx_rearmed import apply as apply_v115
from .apply_map02_v69_pcsx_rearmed import once


def apply(root: Path):
    proof=apply_v115(root)
    frontend=root.resolve()/"frontend/main.c"
    text=frontend.read_text()
    anchor=('            if(vh83_renderer_smoke)\n'
            '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);')
    addition=(
        '            if(vh104_content_smoke) {\n'
        '                vh116_gap_metrics gaps;\n'
        '                if(vh116_get_gap_metrics(&gaps)!=0) {\n'
        '                    SysPrintf("VH116_GAPS_REFUSED\\n");\n'
        '                    ClosePlugins();SysClose();menu_finish();plat_finish();return 32;\n'
        '                }\n'
        '                SysPrintf("VH116_GAPS_PASS g0=%u,%u,%u g1=%u,%u,%u g2=%u,%u,%u g3=%u,%u,%u g4=%u,%u,%u\\n",\n'
        '                    gaps.equal_count_identical[0],gaps.equal_count_different[0],gaps.different_count[0],\n                    gaps.equal_count_identical[1],gaps.equal_count_different[1],gaps.different_count[1],\n                    gaps.equal_count_identical[2],gaps.equal_count_different[2],gaps.different_count[2],\n                    gaps.equal_count_identical[3],gaps.equal_count_different[3],gaps.different_count[3],\n                    gaps.equal_count_identical[4],gaps.equal_count_different[4],gaps.different_count[4]);\n'
        '            }\n'
    )
    text=once(text,anchor,addition+anchor,"v116 native 0..4 VBlank-gap class summary")
    frontend.write_text(text)
    return dict(proof,
        exact_24_sample_identity_classified_by_intervening_vblank_edges=True,
        native_sample_values_never_exported=True,
        canonical_v82_private_jsonl_unchanged=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
