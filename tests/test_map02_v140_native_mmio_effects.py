#!/usr/bin/env python3
"""v140 direct GP0/DMA MMIO effect proof, using only generated synthetic PS-X."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from tools.apply_map02_v138_interpreter_pc import (
    expected_pc_events,native_probe_declarations,modified_native_oracle
)
from tools.apply_map02_v139_mips_word_stages import (
    codeword_expectations,patch_v138_probe_c,modify_oracle as v139_oracle
)
from tools.apply_map02_v140_mmio_effects import (
    expected_actual_mmio,patch_native_value_observer,patch_synthetic_oracle
)
from tools.check_map02_v140_native_mmio_effects import sample_source
from tools.make_map02_v129_four_vblank_exe import build
from tools.make_map02_v125_variable_gpu_dma_exe import (
    BASES,DMA2_BCR,DMA2_CHCR,DMA2_DPCR
)
from tools.make_map02_v121_mips_gp0_return_exe import SETUP


class MipsNativeMMIOEffects(unittest.TestCase):
    def test_exact_original_source_authored_values_match_static_pc_classes(self):
        events,words,prefixes=codeword_expectations()
        actual=expected_actual_mmio()
        self.assertEqual(len(actual),19)
        self.assertEqual(prefixes,(7,11,15,19))
        self.assertEqual([value for addr,value in actual if addr==0x1f801810],
                         list(SETUP))
        self.assertEqual(actual[6],(0x1f8010f0,DMA2_DPCR))
        for stage,base in enumerate(BASES):
            self.assertEqual(actual[7+4*stage:11+4*stage],(
                (0x1f8010a8,0),(0x1f8010a0,base),
                (0x1f8010a4,DMA2_BCR),(0x1f8010a8,DMA2_CHCR)))
        self.assertEqual(sum(a==0x1f8010a8 and v==0x01000401
                             for a,v in actual),3)
        self.assertEqual(sum(a==0x1f8010a8 and v==0 for a,v in actual),3)
        self.assertEqual(len({pc for pc,*_ in events}),len(actual))

    def test_native_actual_memory_store_observer_checks_exact_address_and_value(self):
        original=patch_v138_probe_c(native_probe_declarations(
            expected_pc_events()))
        modified=patch_native_value_observer(original)
        for token in (
            "vh140_expected_addr[]","vh140_expected_value[]",
            "vh140_mmio_observe(u32 addr,u32 value)",
            "addr!=vh140_expected_addr[vh140_count]",
            "value!=expected_value",
            "vh140_dma2_starts==3u","vh140_dma2_resets==3u",
            "vh140_gp0==6u","expected_value^=1u",
            "if(vh140_active) vh140_mmio_observe(addr,value)",
        ):
            self.assertIn(token,modified)
        self.assertEqual(modified.count("vh138_pc_observe(psxRegisters"),1)
        self.assertNotIn("GPU_writeData(",modified)
        self.assertNotIn("regs->pc=",modified)
        self.assertNotIn("psxRegs.cycle=",modified)
        self.assertNotIn("SysPrintf(",modified)

    def test_runtime_oracle_verifies_before_old_source_pc_pass_without_gpu_changes(self):
        _,stops,ops,starts,wait=build()
        events=expected_pc_events()
        original=v139_oracle(modified_native_oracle(stops,wait,len(events)),
                             len(events))
        next=patch_synthetic_oracle(original)
        self.assertIn("VH140_NATIVE_MMIO_VALUES_PASS",next)
        self.assertIn("VH140_NATIVE_MMIO_VALUE_REFUSED",next)
        self.assertIn("vh140_mmio_verify()!=0u",next)
        self.assertIn("vh140_mmio_enable(vh140_corrupt_value)",next)
        self.assertIn("VH139_NATIVE_MIPS_WORDS_PASS",next)
        self.assertIn("VH138_NATIVE_INTERPRETER_PC_PASS",next)
        self.assertEqual(original.count("psxCpu->ExecuteBlock(&psxRegs"),
                         next.count("psxCpu->ExecuteBlock(&psxRegs"))
        self.assertEqual(original.count("GPU_freeze("),next.count("GPU_freeze("))
        self.assertEqual(original.count("vh139_check_stage("),
                         next.count("vh139_check_stage("))

    def test_independent_compiled_negative_controls_are_mandatory(self):
        src,events,effects,prefixes=sample_source()
        self.assertEqual(len(events),19)
        self.assertEqual(len(effects),19)
        for token in ("trial(0u)","trial(1u)","trial(2u)",
                      "trial(3u)","trial(4u)",
                      "addr^=0x80000000u","value^=1u",
                      "vh140_expected_value[1u]",
                      "vh140_mmio_verify()",
                      "VH140_COMPILED_MMIO_EFFECT_PASS"):
            self.assertIn(token,src)

    def test_native_workflow_executes_true_interpreted_positive_and_negative(self):
        file=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for token in (
            "apply_map02_v140_mmio_effects",
            "check_map02_v140_native_mmio_effects",
            "test_map02_v140_native_mmio_effects.py",
            "--vh140-mmio-values",
            "--vh140-corrupt-value-witness",
            "VH140_NATIVE_MMIO_VALUES_PASS",
            "VH140_NATIVE_MMIO_VALUE_REFUSED",
            "VH139_NATIVE_MIPS_WORDS_PASS",
            "VH138_NATIVE_INTERPRETER_PC_PASS",
            "for mode in 04 13 22 31 40; do",
            "sha256sum -c proof/private/v131-same-exe.sha256",
        ):
            self.assertIn(token,file)
        standalone=(ROOT/".github/workflows/map02-v140-native-mmio-effects.yml").read_text()
        for token in (
            "check_map02_v140_native_mmio_effects",
            "test_map02_v140_native_mmio_effects.py",
            "no_retail_images_in_ci=1"):
            self.assertIn(token,standalone)


if __name__=="__main__":
    unittest.main()
