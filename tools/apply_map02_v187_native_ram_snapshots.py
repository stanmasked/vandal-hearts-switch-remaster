#!/usr/bin/env python3
"""MAP02 v187: exact native RAM readback receipts bound to real VBlank count.

The pinned PCSX frontend emits one numeric pre-execution RAM snapshot for each
of phase boundaries 1, 2 and 3. The observed emulator VBlank count must equal
that phase. This is additive to v186: all nine host-test corruption modes keep
their exact native exit and negative markers. No retail MAP02 execution.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v186_late_vblank_ram_corruption import apply as apply_v186
from .apply_map02_v69_pcsx_rearmed import once

SNAPSHOT_MARKER = "VH187_NATIVE_RAM_SNAPSHOT"
SNAPSHOT_SUCCESS = (
    "VH187_NATIVE_RAM_SNAPSHOTS_PASS boundaries=3 ordered_vblanks=3 "
    "exact_values=1 guard=1 original_retail=0"
)
PRECHECK_ANCHOR = "if(vh185_first!=0x51a7c3d9u ||"
COUNT_ANCHOR = "unsigned int vh185_boundaries=0u;"
SUCCESS_ANCHOR = 'SysPrintf("VH185_NATIVE_RAM_PERSISTENCE_PASS'
EVENT_SEQUENCE_EXIT = 87

def patch_frontend(source: str) -> str:
    if SNAPSHOT_MARKER in source:
        raise ValueError("v187 RAM snapshot instrumentation already present")
    for required in (
        "vh186_late_vblank_ram_fault",
        "VH185_NATIVE_RAM_PERSISTENCE_REFUSED",
        "vh78_vblank_observed_count",
    ):
        if required not in source:
            raise ValueError("v187 requires fully installed v186 native RAM oracle: " + required)
    src = once(
        source, COUNT_ANCHOR, COUNT_ANCHOR + "\n\t\tunsigned int vh187_snapshots=0u;",
        "three precisely counted pre-execution snapshots"
    )
    witness = (
        "if(vh78_vblank_observed_count!=phase){\n"
        '                SysPrintf("VH187_NATIVE_VBLANK_SEQUENCE_REFUSED phase=%u observed=%u\\n",phase,vh78_vblank_observed_count);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 87;\n"
        "\t\t\t}\n"
        '            SysPrintf("VH187_NATIVE_RAM_SNAPSHOT phase=%u vblanks=%u first=%08x derived=%08x guard=%08x\\n",'
        'phase,vh78_vblank_observed_count,vh185_first,vh185_second,vh185_guard);\n'
        "\t\t\tvh187_snapshots++;\n"
        "\t\t\t" + PRECHECK_ANCHOR
    )
    src = once(src, PRECHECK_ANCHOR, witness,
               "strict native emulator VBlank order and real PS1 RAM sample")
    guard = (
        "if(vh187_snapshots!=3u){\n"
        '            SysPrintf("VH187_RAM_SNAPSHOT_COUNT_REFUSED snapshots=%u\\n",vh187_snapshots);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 87;\n"
        "\t\t}\n"
        '        SysPrintf("' + SNAPSHOT_SUCCESS + '\\n");\n'
        "\t\t" + SUCCESS_ANCHOR
    )
    return once(src, SUCCESS_ANCHOR, guard,
                "refuse missing pre-execution snapshot before positive RAM marker")

def apply(root: Path):
    report = apply_v186(root)
    filename = root.resolve() / "frontend/main.c"
    filename.write_text(patch_frontend(filename.read_text()))
    return dict(
        report, v187_exact_native_ram_snapshots=3,
        v187_native_vblank_order_required=True,
        v187_bad_vblank_order_exit=EVENT_SEQUENCE_EXIT,
        v187_original_retail_executed=False,
        v187_physical_switch_output_verified=False,
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout", type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
