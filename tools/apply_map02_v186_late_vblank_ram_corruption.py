#!/usr/bin/env python3
"""MAP02 v186: detect PS1 RAM faults injected after later native VBlank phases.

Six test-only modes corrupt one of three RAM words after phase 1 or 2;
the next phase must fail closed before interpreted guest SW can rewrite it.
No retail game content or forged VBlank/GPU evidence.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v185_ram_vblank_persistence import apply as apply_v185
from .apply_map02_v69_pcsx_rearmed import once

MODE_IDS = tuple(range(4, 10))
EXPECTED_REFUSAL_EXIT = 86
CLI_ANCHOR = '\t\telse if (!strcmp(argv[i], "--vh183-guest-ram-values"))\n'
PHASE0_FAULT = 'if(phase==0u && vh185_ram_persist_mode>0)'
PHASE0_BOUNDED = 'if(phase==0u && vh185_ram_persist_mode>0 && vh185_ram_persist_mode<=3)'
LATE_FAULT = (
    '\t\t\t/* vh186_late_vblank_ram_fault: Test-only fault AFTER phase 1 or 2 execution;\n'
    '\t\t\t * the next boundary readback precedes subsequent guest SW writes. */\n'
    '\t\t\tif((phase==1u && vh185_ram_persist_mode>=4 && vh185_ram_persist_mode<=6) ||\n'
    '\t\t\t   (phase==2u && vh185_ram_persist_mode>=7 && vh185_ram_persist_mode<=9)){\n'
    '\t\t\t\tunsigned int lane=(unsigned int)(vh185_ram_persist_mode-4)%3u;\n'
    '\t\t\t\tunsigned int addr=lane==0u?0x001e0000u:\n'
    '\t\t\t\t     lane==1u?0x001e0004u:0x001e0008u;\n'
    '\t\t\t\tunsigned int previous=psxMemRead32(&psxRegs,addr);\n'
    '\t\t\t\tpsxMemWrite32(&psxRegs,addr,previous^1u);\n'
    '\t\t\t}\n'
)

def expected_failure(mode: int) -> tuple[int, int, int, int]:
    """Expected phase and three field booleans; this is NOT an emulator result."""
    if mode not in MODE_IDS:
        raise ValueError("v186 modes must be 4..9")
    phase = 2 if mode < 7 else 3
    flags = [1, 1, 1]
    flags[(mode - 4) % 3] = 0
    return (phase, *flags)

def patch_frontend(source: str) -> str:
    if 'vh186_late_vblank_ram_fault' in source:
        raise ValueError("v186 late fault already installed")
    if PHASE0_FAULT not in source or 'VH185_NATIVE_RAM_PERSISTENCE_REFUSED' not in source:
        raise ValueError("v186 requires existing v185 pre-execution RAM readback")
    src = once(source, PHASE0_FAULT, PHASE0_BOUNDED,
               "limit v185 phase-zero faults to original modes 1..3")
    cli = ''.join(
        '\t\telse if (!strcmp(argv[i], "--vh186-ram-persist-' + str(idx) + '"))\n'
        '\t\t\tvh185_ram_persist_mode=' + str(idx) + ';\n'
        for idx in MODE_IDS
    )
    src = once(src, CLI_ANCHOR, cli + CLI_ANCHOR,
               "six separate opt-in late-phase fault diagnostics")
    src = once(src, PHASE0_BOUNDED, LATE_FAULT + '\t\t\t' + PHASE0_BOUNDED,
               "inject late faults only after completed phase one or two")
    return src

def apply(root: Path):
    report = apply_v185(root)
    filename = root.resolve() / "frontend/main.c"
    filename.write_text(patch_frontend(filename.read_text()))
    return dict(report,
        v186_late_fault_modes=6,
        v186_late_fault_phases=(1,2),
        v186_next_boundary_refusals=(2,3),
        v186_exit_on_corruption=EXPECTED_REFUSAL_EXIT,
        v186_original_retail_executed=False,
        v186_physical_switch_output_verified=False)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout", type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
