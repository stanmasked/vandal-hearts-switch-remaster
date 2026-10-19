#!/usr/bin/env python3
"""MAP02 v185: exact source and semantics for 3 VBlank RAM boundaries."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v185_ram_vblank_persistence import (
    GUARD_ADDR,GUARD_VALUE,PRECHECK_EXIT,MODE_NAMES,
    persistence_oracle,patch_frontend
)
from tools.apply_map02_v183_native_ram_values import (
    RAM_ADDRESS,VALUE,TRANSFORMED,SEED0,SEED1
)

def boundary_run(tamper_kind=0):
    """Model only the phase-boundary contract, NOT native PCSX or a frame."""
    expected=(VALUE,TRANSFORMED,GUARD_VALUE)
    memory={RAM_ADDRESS:SEED0,RAM_ADDRESS+4:SEED1,GUARD_ADDR:GUARD_VALUE}
    prechecked=0
    for phase in range(4):
        if phase:
            observed=tuple(memory[a] for a in
                           (RAM_ADDRESS,RAM_ADDRESS+4,GUARD_ADDR))
            if observed!=expected:
                return phase,prechecked,tuple(a==b for a,b in zip(observed,expected))
            prechecked+=1
        memory[RAM_ADDRESS]=VALUE  # real guest SW (modelled)
        memory[RAM_ADDRESS+4]=memory[RAM_ADDRESS]^0xffff  # guest LW/XORI/SW
        if phase==0 and tamper_kind:
            address=(RAM_ADDRESS,RAM_ADDRESS+4,GUARD_ADDR)[tamper_kind-1]
            memory[address]^=1   # explicit test-only post-guest corruption
    return None,prechecked,(True,True,True)

class V185PhaseBoundaryPersistence(unittest.TestCase):
    def test_clean_mode_has_three_preexecution_boundaries(self):
        self.assertEqual(MODE_NAMES,
            ("clean","corrupt_first","corrupt_second","corrupt_guard"))
        self.assertEqual(GUARD_ADDR,RAM_ADDRESS+8)
        self.assertEqual(GUARD_VALUE,0xa1b2c3d4)
        self.assertNotIn(GUARD_VALUE,(SEED0,SEED1,VALUE,TRANSFORMED))
        self.assertEqual(PRECHECK_EXIT,86)
        self.assertEqual(boundary_run(),(None,3,(True,True,True)))

    def test_corrupt_first_second_or_guard_refused_at_phase_one(self):
        for kind,expected in (
            (1,(False,True,True)),
            (2,(True,False,True)),
            (3,(True,True,False))
        ):
            self.assertEqual(boundary_run(kind),(1,0,expected))

    def test_native_oracle_seed_once_and_check_before_next_guest_execution(self):
        source=persistence_oracle()
        for token in (
            "if(vh185_ram_persist_mode>=0)",
            "if(phase==0u)",
            "if(phase==0u && vh185_ram_persist_mode>0)",
            "vh185_boundaries++;",
            "vh185_boundaries!=3u",
            "psxMemRead32(&psxRegs,0x001e0000u)",
            "psxMemRead32(&psxRegs,0x001e0004u)",
            "psxMemRead32(&psxRegs,0x001e0008u)",
            "psxMemWrite32(&psxRegs,0x001e0008u,0xa1b2c3d4u)",
            "VH185_NATIVE_RAM_PERSISTENCE_REFUSED",
            "VH185_NATIVE_RAM_PERSISTENCE_PASS",
            "VH183_NATIVE_GUEST_RAM_VALUES_PASS",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "return 86;",
        ):self.assertIn(token,source)
        precheck=source.index("unsigned int vh185_first=psxMemRead32")
        execution=source.index("unsigned int entry_count=vh78_vblank_observed_count;")
        self.assertLess(precheck,execution)
        self.assertLess(source.index("VH185_NATIVE_RAM_PERSISTENCE_REFUSED"),execution)
        self.assertLess(source.index("vh185_boundaries!=3u"),
                        source.index("VH183_NATIVE_GUEST_RAM_VALUES_PASS"))
        self.assertEqual(source.count("psxMemWrite32(&psxRegs,0x001e0000u,0x1478295au);"),1)
        self.assertEqual(source.count("psxMemWrite32(&psxRegs,0x001e0004u,0xd15ea5edu);"),1)

    def test_modes_fully_separate_and_reentrant_patch_forbidden(self):
        original=('\tint vh183_guest_ram_values=0;\n'
                  '\t\telse if (!strcmp(argv[i], "--vh183-guest-ram-values"))\n'
                  '\tif (loadst_f) {\n')
        modified=patch_frontend(original)
        for n in range(4):self.assertIn(f"--vh185-ram-persist-{n}",modified)
        self.assertIn("--vh183-guest-ram-values",modified)
        self.assertIn("VH185_NATIVE_RAM_PERSISTENCE_REFUSED",modified)
        with self.assertRaises(ValueError):patch_frontend(modified)

    def test_workflow_preserves_native_positive_and_requires_three_fail_closed_exits(self):
        s=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v185-ram-vblank-persistence.yml").read_text()
        for token in (
            "apply_map02_v185_ram_vblank_persistence",
            "test_map02_v185_ram_vblank_persistence.py",
            "for mode in 0 1 2 3; do",
            "--vh185-ram-persist-$mode",
            "V183_RAM_CORRECT.EXE",
            "VH185_NATIVE_RAM_PERSISTENCE_PASS",
            "VH185_NATIVE_RAM_PERSISTENCE_REFUSED phase=1",
            "VH185_NATIVE_RAM_VBLANK_PERSISTENCE_PASS",
            "VH183_NATIVE_GUEST_RAM_VALUES_PASS",
            'test "$rc" -eq 86',
        ):self.assertIn(token,s)
        self.assertIn("test_map02_v184_ram_data_chain_refusals.py",own)
        self.assertIn("original_retail_executed=0",own)

if __name__=="__main__":
    unittest.main()
