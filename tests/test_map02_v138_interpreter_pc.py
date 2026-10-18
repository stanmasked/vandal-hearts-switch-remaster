#!/usr/bin/env python3
"""v138 exact true-PC observation is synthetic only, independently audited."""
from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v138_interpreter_pc import (
    MAX_EVENTS,CLASS_CODES,REGISTER_MAP,MIPS_START,
    expected_pc_events,native_probe_declarations,modified_native_oracle,
)
from tools.check_map02_v138_native_pc_observer import sample_program
from tools.apply_map02_v129_pcsx_rearmed import oracle_source
from tools.make_map02_v129_four_vblank_exe import build
from tools.analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text


class TrueInterpreterPCBinding(unittest.TestCase):
    def test_source_defined_synthetic_expected_addresses_order_and_classes(self):
        events=expected_pc_events()
        self.assertGreater(len(events),10)
        self.assertLess(len(events),MAX_EVENTS)
        self.assertEqual([p for p,*_ in events],sorted(p for p,*_ in events))
        self.assertEqual(len({p for p,*_ in events}),len(events))
        self.assertTrue(all((p-MIPS_START)%4==0 for p,*_ in events))
        self.assertEqual(sum(k==CLASS_CODES["dma2_chcr"]
                             for _,k,*_ in events),6)
        self.assertEqual(sum(linked for *_,linked in events),3)
        self.assertEqual(sum(k==CLASS_CODES["dma2_madr"]
                             for _,k,*_ in events),3)
        self.assertEqual(sum(k==CLASS_CODES["dma2_bcr"]
                             for _,k,*_ in events),3)
        self.assertEqual(sum(k==CLASS_CODES["dma_dpcr"]
                             for _,k,*_ in events),1)
        self.assertTrue(any(k==CLASS_CODES["gpu_gp0"]
                            for _,k,*_ in events))
        self.assertEqual(sum(k==CLASS_CODES["gpu_gp1"]
                             for _,k,*_ in events),0)

    def test_source_exe_static_callback_exact_vs_generated_expected(self):
        raw,stops,ops,starts,wait=build()
        got=[]
        counts,metadata=analyze_delay_aware_text(
            raw[2048:2048+4*len(ops)],
            site_sink=lambda offset,kind,linked:
                got.append((MIPS_START+offset,CLASS_CODES[kind],kind,linked)))
        self.assertEqual(got,list(expected_pc_events()))
        self.assertEqual(counts["dma2_linked_list_chcr_literal"],3)
        self.assertEqual(metadata["ambiguous_control_in_delay_slot"],0)

    def test_actual_native_hook_checks_current_interpreter_code_and_pc(self):
        source=inspect.getsource(native_probe_declarations)
        for expected in (
            "regs->pc-4u","regs->code>>26",
            "vh138_seen>=VH138_EXPECTED_COUNT",
            "vh138_expected_pc[vh138_seen]",
            "vh138_expected_kind[vh138_seen]",
            "vh138_pc_inject_error",
            "vh138_pc_observe","vh138_pc_check",
            "case 0x1f8010a0u","case 0x1f8010a8u",
            "case 0x1f801810u",
        ):
            self.assertIn(expected,source)
        self.assertNotIn("SysPrintf",source)
        self.assertNotIn("GPU_writeData",source)
        self.assertNotIn("psxDma2(",source)
        self.assertNotIn("regs->cycle=",source)
        self.assertNotIn("psxRegs.pc=",source)

    def test_pinned_original_mips_oracle_independently_preserved(self):
        _,stops,_,_,wait=build()
        original=oracle_source(stops,wait)
        modified=modified_native_oracle(stops,wait,len(expected_pc_events()))
        self.assertIn("VH129_REAL_VBLANK_PROFILES_PASS",modified)
        self.assertIn("VH138_NATIVE_INTERPRETER_PC_PASS",modified)
        self.assertIn("VH138_NATIVE_MIPS_PC_REFUSED",modified)
        self.assertIn("vh138_pc_inject_error()",modified)
        self.assertIn("vh138_pc_check()!=0u",modified)
        self.assertIn("vh138_pc_enable()",modified)
        self.assertEqual(original.count("vh78_vblank_observed_count"),
                         modified.count("vh78_vblank_observed_count"))
        self.assertEqual(original.count("psxCpu->ExecuteBlock(&psxRegs"),
                         modified.count("psxCpu->ExecuteBlock(&psxRegs"))
        self.assertEqual(original.count("GPU_freeze("),modified.count("GPU_freeze("))
        self.assertEqual(original.count("vh125_dma_enabled=1;"),
                         modified.count("vh125_dma_enabled=1;"))

    def test_injected_c_observer_program_is_independent_sanitized_source(self):
        source,events=sample_program()
        self.assertEqual(len(events),len(expected_pc_events()))
        for guard in ("vh138_feed_all(2u)","vh138_pc_inject_error();",
                      "regs.code=0x20000000u","VH138_COMPILED_PC_OBSERVER_PASS",
                      "vh138_pc_observe(&regs",
                      "#ifdef VH_MAP02_V66_PCSX_PROBE"):
            self.assertIn(guard,source)
        self.assertNotIn("retail_exe",source.lower())

    def test_full_pinned_native_ci_executes_true_interpreter_source_and_negative(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for needle in (
            "apply_map02_v138_interpreter_pc",
            "test_map02_v138_interpreter_pc.py",
            "check_map02_v138_native_pc_observer",
            "--vh138-interpreter-pc",
            "--vh138-corrupt-pc-witness",
            "VH138_NATIVE_INTERPRETER_PC_PASS",
            "VH138_NATIVE_MIPS_PC_REFUSED",
            "for mode in 04 13 22 31 40; do",
            "sha256sum -c proof/private/v131-same-exe.sha256",
        ):
            self.assertIn(needle,workflow)
        standalone=(ROOT/".github/workflows/map02-v138-interpreter-pc.yml").read_text()
        for needle in ("test_map02_v138_interpreter_pc.py",
                       "check_map02_v138_native_pc_observer",
                       "no_retail_original_game_assets=1"):
            self.assertIn(needle,standalone)


if __name__=="__main__":
    unittest.main()
