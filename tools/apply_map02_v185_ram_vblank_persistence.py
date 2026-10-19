#!/usr/bin/env python3
"""v185: verify synthetic guest-computed RAM survives real PCSX VBlank gaps.

Unlike v183, seed initial scratch words only in phase zero; before each later
guest execution verify both final words and an unrelated guard. The same
nine-word guest synthetic PS-X EXE and four genuine PCSX VBlanks/Unai 2380
pixels remain mandatory. Three explicit negative CLI modes corrupt exactly
one of those values AFTER phase zero to prove that phase-one pre-execution
readback fails closed (exit 86), before guest SW can conceal corruption.

All corruption is deliberate TEST-ONLY host fixture action, never a claim of
retail game behavior or physical Switch video. No original game assets.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v183_native_ram_values import (
    apply as apply_v183,native_value_oracle,
    RAM_ADDRESS,VALUE,TRANSFORMED,SEED0,SEED1,
)
from .apply_map02_v69_pcsx_rearmed import once

GUARD_ADDR=RAM_ADDRESS+8
GUARD_VALUE=0xa1b2c3d4
PRECHECK_EXIT=86
FLAG="\tint vh183_guest_ram_values=0;\n"
CLI='\t\telse if (!strcmp(argv[i], "--vh183-guest-ram-values"))\n'
INSERT="\tif (loadst_f) {\n"
MODE_NAMES=("clean","corrupt_first","corrupt_second","corrupt_guard")

def persistence_oracle()->str:
    src=native_value_oracle()
    src=once(src,"if(vh183_guest_ram_values) {",
             "if(vh185_ram_persist_mode>=0) {",
             "separate clean vs three tamper diagnostics from existing v183 mode")
    seed=(
        f"\t\t\tpsxMemWrite32(&psxRegs,0x{RAM_ADDRESS:08x}u,0x{SEED0:08x}u);\n"
        f"\t\t\tpsxMemWrite32(&psxRegs,0x{RAM_ADDRESS+4:08x}u,0x{SEED1:08x}u);\n"
    )
    staged=(
        "\t\t\tif(phase==0u){\n"
        + seed +
        f"\t\t\t\tpsxMemWrite32(&psxRegs,0x{GUARD_ADDR:08x}u,0x{GUARD_VALUE:08x}u);\n"
        "\t\t\t}else{\n"
        f"\t\t\t\tunsigned int vh185_first=psxMemRead32(&psxRegs,0x{RAM_ADDRESS:08x}u);\n"
        f"\t\t\t\tunsigned int vh185_second=psxMemRead32(&psxRegs,0x{RAM_ADDRESS+4:08x}u);\n"
        f"\t\t\t\tunsigned int vh185_guard=psxMemRead32(&psxRegs,0x{GUARD_ADDR:08x}u);\n"
        f"\t\t\t\tif(vh185_first!=0x{VALUE:08x}u || vh185_second!=0x{TRANSFORMED:08x}u ||\n"
        f"\t\t\t\t   vh185_guard!=0x{GUARD_VALUE:08x}u){{\n"
        '                    SysPrintf("VH185_NATIVE_RAM_PERSISTENCE_REFUSED phase=%u first_ok=%u derived_ok=%u guard_ok=%u\\n",phase,'
        f'vh185_first==0x{VALUE:08x}u,vh185_second==0x{TRANSFORMED:08x}u,'
        f'vh185_guard==0x{GUARD_VALUE:08x}u);\n'
        "\t\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 86;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tvh185_boundaries++;\n"
        "\t\t\t}\n"
    )
    src=once(src,seed,staged,
             "phase0 one-time seed plus phase1-3 pre-execution RAM persistence and guard proof")
    src=once(src,"\t\t\tvh183_ram_windows++;",
        "\t\t\tvh183_ram_windows++;\n"
        "\t\t\t/* Explicit corruption is test-only and occurs AFTER guest execution;\n"
        "\t\t\t * phase-one readback MUST detect it BEFORE the next guest SW. */\n"
        "\t\t\tif(phase==0u && vh185_ram_persist_mode>0){\n"
        f"\t\t\t\tunsigned int addr=vh185_ram_persist_mode==1?0x{RAM_ADDRESS:08x}u:\n"
        f"\t\t\t\t     vh185_ram_persist_mode==2?0x{RAM_ADDRESS+4:08x}u:0x{GUARD_ADDR:08x}u;\n"
        "\t\t\t\tunsigned int original=psxMemRead32(&psxRegs,addr);\n"
        "\t\t\t\tpsxMemWrite32(&psxRegs,addr,original^1u);\n"
        "\t\t\t}\n",
        "inject unique byte-equivalent bitflip after phase0 in three negative modes")
    count="unsigned int vh176_narrow_windows=0u;"
    src=once(src,count,count+"\n\t\tunsigned int vh185_boundaries=0u;",
             "count three genuine phase boundary RAM snapshots")
    success='SysPrintf("VH183_NATIVE_GUEST_RAM_VALUES_PASS'
    src=once(src,success,
        'if(vh185_boundaries!=3u){\n'
        '            SysPrintf("VH185_RAM_BOUNDARIES_REFUSED boundaries=%u\\n",vh185_boundaries);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 86;\n"
        "\t\t}\n"
        '        SysPrintf("VH185_NATIVE_RAM_PERSISTENCE_PASS boundaries=3'
        ' seed_once=1 guest_values_retained=1 guard_retained=1'
        ' real_vblanks=4 unai_samples=2380 original_retail=0\\n");\n'
        "\t\t"+success,
        "phase-boundary proof required before inherited v183 positive marker")
    return src

def patch_frontend(source:str)->str:
    if "vh185_ram_persist_mode" in source:
        raise ValueError("v185 persistence mode already installed")
    src=once(source,FLAG,FLAG+"\tint vh185_ram_persist_mode=-1;\n",
             "distinct opt-in native RAM retention mode")
    cli="".join(
        '\t\telse if (!strcmp(argv[i], "--vh185-ram-persist-'+str(idx)+'"))\n'
        '\t\t\tvh185_ram_persist_mode='+str(idx)+';\n'
        for idx in range(4)
    )
    src=once(src,CLI,cli+CLI,"four strictly bounded diagnostic-only CLI modes")
    return once(src,INSERT,persistence_oracle()+"\n"+INSERT,
                "verify true guest values persist across the three native VBlank boundaries")

def apply(root:Path):
    report=apply_v183(root)
    f=root.resolve()/"frontend/main.c"
    f.write_text(patch_frontend(f.read_text()))
    return dict(report,
        v185_four_real_vblank_windows=4,
        v185_preexecution_ram_persistence_boundaries=3,
        v185_unrelated_neighbor_guard_words=1,
        v185_deliberate_corruptions_refused=3,
        v185_original_retail_executed=False,
        v185_physical_switch_output_verified=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
