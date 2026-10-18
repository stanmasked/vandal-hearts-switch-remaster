#!/usr/bin/env python3
"""Actual native MIPS MMIO receipt path: source-only adversarial fixtures."""
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v136_original_code_sections import synthetic_with_exec_section
from test_map02_v141_private_original_mmio_claims import (
    synthetic_source_claims,encode_events,
)
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.apply_map02_v138_interpreter_pc import (
    expected_pc_events,native_probe_declarations,modified_native_oracle,
)
from tools.apply_map02_v139_mips_word_stages import (
    patch_v138_probe_c,modify_oracle as v139_oracle,codeword_expectations
)
from tools.apply_map02_v140_mmio_effects import (
    patch_native_value_observer,patch_synthetic_oracle as v140_oracle
)
from tools.apply_map02_v142_native_private_mmio_receipt import (
    patch_native_observer,patch_native_oracle,native_private_receipt_code
)
from tools.check_map02_v142_native_private_receipt import (
    verify_source_authored_native_receipt
)
from tools.make_map02_v129_four_vblank_exe import build


class RealInterpreterSourceReceipt(unittest.TestCase):
    def setUp(self):
        self.exe,self.elf,self.records=synthetic_source_claims()

    def _private(self,folder,events=None):
        p=Path(folder)/"vh142-interpreter-mmio.jsonl"
        p.write_bytes(encode_events(self.records if events is None else events))
        p.chmod(0o600)
        return p

    def test_source_authored_positive_full_private_receipt(self):
        with tempfile.TemporaryDirectory(prefix="vh142-ok-") as folder:
            path=self._private(folder)
            report=verify_source_authored_native_receipt(path)
            self.assertEqual(report["source_bound_candidate_events"],19)
            self.assertEqual(report["statically_bound_linked_list_start_claims"],3)
            self.assertIs(report["original_map02_loaded_or_rendered"],False)
            self.assertIs(report["trace_producer_authenticated"],False)

    def test_word_mutation_at_third_sw_refused_even_without_cpu_tamper(self):
        change=list(self.records)
        pc,word,addr,value=change[2]
        change[2]=(pc,word^1,addr,value)
        with tempfile.TemporaryDirectory(prefix="vh142-word-") as folder:
            path=self._private(folder,change)
            with self.assertRaises(Refused):
                verify_source_authored_native_receipt(path)

    def test_gp0_value_mutation_refused_by_exact_synthetic_source_binding(self):
        change=list(self.records)
        pc,word,addr,value=change[1]
        change[1]=(pc,word,addr,value^1)
        with tempfile.TemporaryDirectory(prefix="vh142-value-") as folder:
            path=self._private(folder,change)
            with self.assertRaises(Refused):
                verify_source_authored_native_receipt(path)

    def test_order_pc_and_effective_address_mutations_refused(self):
        variants=[]
        changed=list(self.records)
        changed[1],changed[2]=changed[2],changed[1]
        variants.append(changed)
        changed=list(self.records)
        pc,word,addr,value=changed[4]
        changed[4]=(pc+4,word,addr,value)
        variants.append(changed)
        changed=list(self.records)
        pc,word,addr,value=changed[5]
        changed[5]=(pc,word,addr|0x80000000,value)
        variants.append(changed)
        for i,items in enumerate(variants):
            with tempfile.TemporaryDirectory(prefix="vh142-mutate-") as folder:
                path=self._private(folder,items)
                with self.subTest(i=i),self.assertRaises(Refused):
                    verify_source_authored_native_receipt(path)

    def test_cli_outputs_only_aggregate_result_and_negative_refusal(self):
        for mutate in (False,True):
            with tempfile.TemporaryDirectory(prefix="vh142-cli-") as folder:
                events=list(self.records)
                if mutate:
                    pc,word,addr,value=events[2]
                    events[2]=(pc,word^1,addr,value)
                path=self._private(folder,events)
                run=subprocess.run([
                    sys.executable,"-m",
                    "tools.check_map02_v142_native_private_receipt",
                    str(path),*(["--expect-refusal"] if mutate else [])],
                    cwd=ROOT,capture_output=True,text=True,check=False,timeout=20)
                self.assertEqual(run.returncode,0)
                expected=("VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED"
                          if mutate else
                          "VH142_NATIVE_SOURCE_EXE_ELF_RECEIPT_PASS")
                self.assertIn(expected,run.stdout)
                self.assertEqual(run.stderr,"")
                self.assertNotIn(str(path),run.stdout)
                for pc,word,addr,value in events:
                    self.assertNotIn(str(pc),run.stdout)
                    self.assertNotIn(str(word),run.stdout)
                    self.assertNotIn(str(addr),run.stdout)
                if not mutate:
                    fake=subprocess.run([
                        sys.executable,"-m",
                        "tools.check_map02_v142_native_private_receipt",
                        str(path),"--expect-refusal"],cwd=ROOT,
                        capture_output=True,text=True,check=False,timeout=20)
                    self.assertEqual(fake.returncode,3)
                    self.assertEqual(fake.stdout,"")
                    self.assertIn("FALSE_ACCEPT_REFUSED",fake.stderr)

    def test_actual_native_hook_uses_interpreter_pc_and_private_writer(self):
        source=patch_native_observer(
            patch_native_value_observer(
                patch_v138_probe_c(native_probe_declarations(
                    expected_pc_events()))))
        for needle in (
            "vh142_capture(psxRegisters *regs,u32 address,u32 value)",
            "vh142_events[vh142_count].pc=regs->pc-4u",
            "vh142_events[vh142_count].word=regs->code",
            "vh142_events[vh142_count].address=address",
            "vh142_events[vh142_count].value=value",
            "if(vh142_active) vh142_capture(regs,addr,value)",
            "O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600",
            "O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC",
            "vh142_write_all(fd,line,(size_t)count)",
            "fsync(fd)",
            "if(corrupt_claim && i==2u) word^=1u",
        ):
            self.assertIn(needle,source)
        self.assertEqual(source.count("vh142_capture(regs,addr,value)"),1)
        self.assertNotIn("SysPrintf",native_private_receipt_code())
        self.assertNotIn("GPU_writeData",native_private_receipt_code())
        self.assertNotIn("psxRegs.pc=",native_private_receipt_code())

    def test_native_old_vblank_gpu_oracle_remains_byte_stable(self):
        _,stops,_,_,wait_pc=build()
        events=expected_pc_events()
        original=v140_oracle(v139_oracle(
            modified_native_oracle(stops,wait_pc,len(events)),
            len(events)))
        changed=patch_native_oracle(original)
        for name in ("psxCpu->ExecuteBlock(&psxRegs",
                     "GPU_freeze(","vh78_vblank_observed_count",
                     "vh139_check_stage("):
            self.assertEqual(original.count(name),changed.count(name))
        self.assertIn("VH142_NATIVE_PRIVATE_RECEIPT_PASS",changed)
        self.assertIn("VH142_PRIVATE_RECEIPT_REFUSED",changed)
        self.assertIn("vh142_write_receipt(private_receipt_dir",changed)
        self.assertIn("VH140_NATIVE_MMIO_VALUES_PASS",changed)

    def test_ci_protects_private_receipt_and_runs_source_verifier(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v142-private-mmio-receipt.yml").read_text()
        for item in (
            "test_map02_v142_native_private_receipt.py",
            "check_map02_v142_native_private_receipt",
            "apply_map02_v142_native_private_mmio_receipt",
            "VH142_NATIVE_PRIVATE_RECEIPT_PASS",
            "VH142_NATIVE_SOURCE_EXE_ELF_RECEIPT_PASS",
            "VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED",
            "VH142_PRIVATE_RECEIPT_DIR",
            "--vh142-private-receipt","--vh142-corrupt-receipt",
            "for mode in 04 13 22 31 40; do",
        ):
            self.assertIn(item,native)
        for item in ("test_map02_v142_native_private_receipt.py",
                     "no_retail_psx_exe_in_ci=1"):
            self.assertIn(item,standalone)
        self.assertIn("path: proof/public/",native)


if __name__=="__main__":
    unittest.main()
