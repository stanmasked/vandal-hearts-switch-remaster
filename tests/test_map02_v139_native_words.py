#!/usr/bin/env python3
"""Source-authored native exact MIPS word + four CPU-stage proofs for v139."""
from __future__ import annotations
import inspect
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from tools.make_map02_v129_four_vblank_exe import build
from tools.apply_map02_v138_interpreter_pc import (
    expected_pc_events,native_probe_declarations,modified_native_oracle,
)
from tools.apply_map02_v139_mips_word_stages import (
    codeword_expectations,patch_v138_probe_c,modify_oracle,
)
from tools.check_map02_v139_native_words import sample_source


class OriginalMipsWordStageWitness(unittest.TestCase):
    def test_original_generated_executable_word_bytes_and_prefixes(self):
        data,stops,ops,starts,_=build()
        events,words,prefixes=codeword_expectations()
        self.assertEqual(len(events),19)
        self.assertEqual(len(words),19)
        self.assertEqual(len(prefixes),4)
        self.assertEqual(prefixes[-1],19)
        self.assertEqual(list(prefixes),sorted(set(prefixes)))
        for ((pc,cls,kind,linked),word) in zip(events,words):
            relative=pc-0x80010000
            self.assertEqual(
                word,int.from_bytes(data[2048+relative:2052+relative],"little"))
            self.assertEqual(word,ops[relative//4])
            self.assertEqual(word>>26,0x2b)
            self.assertIn(kind,("dma2_madr","dma2_bcr","dma2_chcr",
                                "dma_dpcr","gpu_gp0","gpu_gp1"))
        self.assertEqual(events,expected_pc_events())
        self.assertEqual(
            prefixes,tuple(sum(pc<stop for pc,*_ in events) for stop in stops))

    def test_patch_proves_current_register_codeword_exact_not_opcode_only(self):
        originals=native_probe_declarations(expected_pc_events())
        changed=patch_v138_probe_c(originals)
        self.assertIn("regs->code!=want",changed)
        self.assertIn("want^=1u",changed)
        self.assertIn("vh139_check_stage(unsigned stage)",changed)
        self.assertIn("vh139_stage_next==4u",changed)
        self.assertIn("vh138_seen!=vh139_stage_prefix[stage]",changed)
        self.assertIn("vh139_expected_word",changed)
        self.assertIn("vh139_word_table_bound",changed)
        self.assertEqual(changed.count("vh138_pc_observe(psxRegisters"),1)
        self.assertEqual(changed.count("vh139_check_stage(unsigned stage)"),1)
        self.assertEqual(changed.count("vh139_verify(void)"),1)
        self.assertNotIn("SysPrintf(",changed)
        self.assertNotIn("GPU_writeData(",changed)
        self.assertNotIn("psxRegs.pc=",changed)

    def test_native_timing_and_dma_original_oracle_not_changed(self):
        data,stops,ops,starts,wait=build()
        base=modified_native_oracle(stops,wait,len(expected_pc_events()))
        current=modify_oracle(base,len(expected_pc_events()))
        self.assertEqual(base.count("psxCpu->ExecuteBlock(&psxRegs"),
                         current.count("psxCpu->ExecuteBlock(&psxRegs"))
        self.assertEqual(base.count("GPU_freeze("),current.count("GPU_freeze("))
        self.assertEqual(base.count("vh78_vblank_observed_count"),
                         current.count("vh78_vblank_observed_count"))
        self.assertIn("vh139_check_stage(0u)",current)
        self.assertIn("vh139_check_stage(phase+1u)",current)
        self.assertIn("VH139_NATIVE_MIPS_WORDS_PASS",current)
        self.assertIn("VH139_NATIVE_WORD_REFUSED",current)
        self.assertIn("VH138_NATIVE_INTERPRETER_PC_PASS",current)
        self.assertIn("VH129_REAL_VBLANK_PROFILES_PASS",current)
        self.assertIn("vh139_enable(vh139_corrupt_word)",current)

    def test_compiled_positive_and_four_negative_controls_present(self):
        source,events,words,prefixes=sample_source()
        self.assertEqual(len(events),19)
        self.assertEqual(len(words),19)
        self.assertEqual(len(prefixes),4)
        for check in ("run_case(0u)","run_case(1u)","run_case(2u)",
                      "run_case(4u)","run_case(8u)",
                      "regs.code^=0x00010000u",
                      "vh139_check_stage(","VH139_COMPILED_WORD_STAGE_PASS",
                      "vh139_expected_word[i]","vh138_pc_observe("):
            self.assertIn(check,source)

    def test_native_ci_real_emulator_requires_two_extra_runs(self):
        source=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for key in (
            "apply_map02_v139_mips_word_stages",
            "check_map02_v139_native_words",
            "test_map02_v139_native_words.py",
            "--vh139-codewords",
            "--vh139-corrupt-word-witness",
            "VH139_NATIVE_MIPS_WORDS_PASS",
            "VH139_NATIVE_WORD_REFUSED",
            "for mode in 04 13 22 31 40; do",
            "sha256sum -c proof/private/v131-same-exe.sha256",
            "VH138_NATIVE_INTERPRETER_PC_PASS",
        ):
            self.assertIn(key,source)
        standalone=(ROOT/".github/workflows/map02-v139-native-words.yml").read_text()
        for key in (
            "test_map02_v139_native_words.py",
            "check_map02_v139_native_words",
            "no_original_retail_data_in_ci=1",
        ):
            self.assertIn(key,standalone)


if __name__=="__main__":
    unittest.main()
