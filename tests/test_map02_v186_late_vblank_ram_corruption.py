#!/usr/bin/env python3
"""MAP02 v186: model later RAM fault placement and audit native patch wiring."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.apply_map02_v186_late_vblank_ram_corruption import (
    MODE_IDS, EXPECTED_REFUSAL_EXIT, expected_failure, patch_frontend,
    PHASE0_FAULT, PHASE0_BOUNDED, LATE_FAULT
)
from tools.apply_map02_v185_ram_vblank_persistence import (
    GUARD_ADDR, GUARD_VALUE, persistence_oracle
)
from tools.apply_map02_v183_native_ram_values import (
    RAM_ADDRESS, SEED0, SEED1, VALUE, TRANSFORMED
)

def run_phase_model(mode: int):
    """Host-only model, not native PCSX execution."""
    memory = [SEED0, SEED1, GUARD_VALUE]
    expected = (VALUE, TRANSFORMED, GUARD_VALUE)
    checkpoints = 0
    for phase in range(4):
        if phase:
            good = tuple(int(x == y) for x, y in zip(memory, expected))
            if good != (1, 1, 1):
                return phase, *good, checkpoints
            checkpoints += 1
        memory[0] = VALUE                  # model of guest SW
        memory[1] = memory[0] ^ 0xffff     # model of guest LW/XORI/SW
        if phase == (1 if mode <= 6 else 2):
            memory[(mode - 4) % 3] ^= 1    # explicit test-only host bit flip
    return None, 1, 1, 1, checkpoints

class V186LateVBlankCorruption(unittest.TestCase):
    def test_six_faults_detected_only_at_correct_later_boundary(self):
        self.assertEqual(MODE_IDS, tuple(range(4, 10)))
        self.assertEqual(EXPECTED_REFUSAL_EXIT, 86)
        self.assertEqual(GUARD_ADDR, RAM_ADDRESS + 8)
        self.assertEqual(tuple(expected_failure(m) for m in MODE_IDS), (
            (2,0,1,1), (2,1,0,1), (2,1,1,0),
            (3,0,1,1), (3,1,0,1), (3,1,1,0)
        ))
        for mode in MODE_IDS:
            self.assertEqual(run_phase_model(mode),
                             (*expected_failure(mode), mode // 7 + 1))

    def test_rejects_out_of_range_modes(self):
        for mode in (-1,0,1,2,3,10,99):
            with self.assertRaises(ValueError):
                expected_failure(mode)

    def test_native_patch_preserves_original_modes_and_timing(self):
        base = ('\t\telse if (!strcmp(argv[i], "--vh183-guest-ram-values"))\n'
                '\t\t\tvh183_guest_ram_values=1;\n' +
                persistence_oracle())
        self.assertIn(PHASE0_FAULT, base)
        patched = patch_frontend(base)
        self.assertIn(PHASE0_BOUNDED, patched)
        self.assertNotIn(PHASE0_FAULT + '{', patched)
        self.assertIn('vh186_late_vblank_ram_fault', patched)
        self.assertIn(LATE_FAULT.splitlines()[3].strip(), patched)
        for mode in MODE_IDS:
            self.assertIn(f'--vh186-ram-persist-{mode}', patched)
        self.assertIn('VH185_NATIVE_RAM_PERSISTENCE_REFUSED', patched)
        self.assertLess(patched.index('vh183_ram_windows++;'),
                        patched.index('vh186_late_vblank_ram_fault'))
        with self.assertRaises(ValueError):
            patch_frontend(patched)

    def test_native_workflow_requires_six_refusals(self):
        workflow = (ROOT / '.github/workflows/map02-v104-content-guard.yml').read_text()
        independent = (ROOT / '.github/workflows/map02-v186-late-vblank-ram-corruption.yml').read_text()
        for required in (
            'apply_map02_v186_late_vblank_ram_corruption',
            'test_map02_v186_late_vblank_ram_corruption.py',
            'for mode in 4 5 6 7 8 9; do',
            '--vh186-ram-persist-$mode',
            'VH185_NATIVE_RAM_PERSISTENCE_REFUSED phase=',
            'VH186_NATIVE_LATE_RAM_REFUSALS_PASS',
            'test "$rc" -eq 86',
        ):
            self.assertIn(required, workflow)
        self.assertIn('test_map02_v185_ram_vblank_persistence.py', independent)
        self.assertIn('original_retail_executed=0', independent)

if __name__ == "__main__":
    unittest.main()
