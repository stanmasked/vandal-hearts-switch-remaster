#!/usr/bin/env python3
"""Generic bounded native MIPS MMIO event collector regression, no retail."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v141_private_original_mmio_claims import (
    encode_events,synthetic_source_claims,
)
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.apply_map02_v147_generic_native_mmio import (
    native_generic_capture_code,patch_generic_memory,patch_generic_frontend,
)
from tools.apply_map02_v142_native_private_mmio_receipt import (
    patch_native_observer,patch_native_oracle,
)
from tools.apply_map02_v144_private_run_challenge import (
    native_challenge_bound_receipt_code,
)
from tools.apply_map02_v140_mmio_effects import (
    patch_native_value_observer,patch_synthetic_oracle,
)
from tools.apply_map02_v139_mips_word_stages import (
    patch_v138_probe_c,modify_oracle as v139_oracle,
)
from tools.apply_map02_v138_interpreter_pc import (
    native_probe_declarations,expected_pc_events,modified_native_oracle,
)
from tools.check_map02_v147_native_bounded_c import native_test_source
from tools.check_map02_v147_native_generic_mmio import (
    verify_bounded_synthetic,verify_bounded_original_claims,
)
from tools.make_map02_v129_four_vblank_exe import build


class GeneralMipsPrivateCollector(unittest.TestCase):
    def setUp(self):
        _,_,self.records=synthetic_source_claims()

    def _private_fixture(self,root,events=None):
        root=Path(root)
        output=root/"output"
        external=root/"external"
        output.mkdir(mode=0o700)
        external.mkdir(mode=0o700)
        for d in (output,external):d.chmod(0o700)
        path=output/"vh147-original-mips-events.jsonl"
        path.write_bytes(encode_events(
            self.records if events is None else events))
        path.chmod(0o600)
        challenge=b"ab4f96372d5056e02a1fc748bb0d1e39\n"
        sidecar=output/"vh144-run-challenge.hex"
        sidecar.write_bytes(challenge)
        sidecar.chmod(0o600)
        retained=external/"expected.hex"
        retained.write_bytes(challenge)
        retained.chmod(0o600)
        return path,retained,sidecar

    def test_synthetic_exact_bytes_are_verified_without_runtime_retail_claim(self):
        with tempfile.TemporaryDirectory(prefix="vh147-") as temp:
            trace,nonce,_=self._private_fixture(temp)
            report=verify_bounded_synthetic(trace,nonce)
            self.assertEqual(report["events"],19)
            self.assertIs(report["source_matching_passed"],True)
            self.assertIs(report["runtime_retail_execution_authenticated"],False)
            self.assertIs(report["original_map02_rendered"],False)

    def test_generic_reader_refuses_changed_words_values_and_wrong_nonce(self):
        for idx,field in ((0,0),(2,1),(3,2),(4,3)):
            changed=list(self.records)
            row=list(changed[idx])
            row[field]^=1
            changed[idx]=tuple(row)
            with tempfile.TemporaryDirectory(prefix="vh147-tamper-") as temp:
                trace,nonce,_=self._private_fixture(temp,changed)
                with self.subTest(index=idx,field=field),self.assertRaises(Refused):
                    verify_bounded_synthetic(trace,nonce)
        with tempfile.TemporaryDirectory(prefix="vh147-nonce-") as temp:
            trace,nonce,_=self._private_fixture(temp)
            nonce.write_bytes(b"0"*32+b"\n")
            with self.assertRaises(Refused):
                verify_bounded_synthetic(trace,nonce)

    def test_bounded_synthetic_and_repeated_events_must_match_source(self):
        with tempfile.TemporaryDirectory(prefix="vh147-short-") as temp:
            trace,nonce,_=self._private_fixture(temp,self.records[:5])
            with self.assertRaises(Refused):
                verify_bounded_synthetic(trace,nonce)
        with tempfile.TemporaryDirectory(prefix="vh147-repeat-") as temp:
            trace,nonce,_=self._private_fixture(temp,self.records[:1]*2)
            with self.assertRaises(Refused):
                verify_bounded_synthetic(trace,nonce)

    def test_unowned_retail_code_cannot_be_inferred_from_public_synthetic(self):
        with tempfile.TemporaryDirectory(prefix="vh147-retail-refused-") as temp:
            trace,nonce,_=self._private_fixture(temp)
            private=Path(temp)/"files"
            private.mkdir(mode=0o700)
            exe,elf,_=synthetic_source_claims()
            exe_path=private/"private-us-exe"
            elf_path=private/"private-us-elf"
            for path,content in ((exe_path,exe),(elf_path,elf)):
                path.write_bytes(content)
                path.chmod(0o600)
            with self.assertRaises(Refused):
                verify_bounded_original_claims(trace,nonce,exe_path,elf_path)

    def test_native_dynamic_capture_has_no_hardcoded_pc_or_count_19(self):
        source=native_generic_capture_code()
        for required in (
            "VH147_MAX_EVENTS 1024u",
            "vh147_count>=VH147_MAX_EVENTS",
            "vh147_bad++",
            "vh147_events[vh147_count].pc=regs->pc-4u",
            "vh147_events[vh147_count].word=regs->code",
            "vh147_events[vh147_count].address=address",
            "vh147_events[vh147_count].value=value",
            "vh143_open_verified_directory(private_dir)",
            "vh144_write_challenge(dirfd,challenge,&challenge_created)",
            "linkat(dirfd,VH147_STAGE_NAME,dirfd,VH147_FINAL_NAME,0)",
            "VH147_FINAL_NAME",
        ):
            self.assertIn(required,source)
        self.assertNotIn("VH138_EXPECTED_COUNT",source)
        self.assertNotIn("vh138_expected_pc",source)
        self.assertNotIn("VH142_EXPECTED_EVENTS",source)
        self.assertNotIn("GPU_writeData",source)
        self.assertNotIn("SysPrintf",source)

    def test_native_actual_mips_hook_and_synthetic_oracle_are_additive(self):
        native=patch_native_observer(
            patch_native_value_observer(
                patch_v138_probe_c(native_probe_declarations(
                    expected_pc_events()))))
        newer=patch_generic_memory(native)
        self.assertEqual(newer.count(
            "vh147_capture(regs,addr,value)"),1)
        self.assertEqual(newer.count(
            "vh142_capture(regs,addr,value)"),1)
        self.assertIn("vh147_write_receipt(const char *private_dir)",newer)
        _,stops,_,_,wait=build()
        old=patch_native_oracle(patch_synthetic_oracle(v139_oracle(
            modified_native_oracle(stops,wait,19),19)))
        # Original generated oracle is decorated in the actual frontend with
        # flags before calling patch_generic_frontend.
        self.assertIn("vh142_write_receipt",old)
        self.assertIn("vh140_mmio_verify",old)

    def test_full_native_c_fixture_uses_same_generic_writer(self):
        fixture=native_test_source()
        self.assertIn(native_generic_capture_code(),fixture)
        self.assertIn(native_challenge_bound_receipt_code(),fixture)
        self.assertIn('strcmp(argv[1],"repeat")==0',fixture)
        self.assertIn('strcmp(argv[1],"overflow")==0 ? 1025u',fixture)

    def test_cli_proves_only_synthetic_and_generic_original_selector_refuses(self):
        with tempfile.TemporaryDirectory(prefix="vh147-cli-") as temp:
            trace,nonce,_=self._private_fixture(temp)
            cmd=[sys.executable,"-m",
                 "tools.check_map02_v147_native_generic_mmio",
                 str(trace),str(nonce)]
            ok=subprocess.run(cmd,cwd=ROOT,capture_output=True,
                              text=True,timeout=18,check=False)
            self.assertEqual(ok.returncode,0)
            self.assertIn("VH147_NATIVE_GENERIC_MMIO_SOURCE_BOUND_PASS",ok.stdout)
            self.assertIn("retail_executed=0",ok.stdout)
            self.assertEqual(ok.stderr,"")
            for secret in (str(trace),str(nonce),str(self.records[0][0])):
                self.assertNotIn(secret,ok.stdout)
            false=subprocess.run(cmd+["--expect-refusal"],
                cwd=ROOT,capture_output=True,text=True,timeout=18)
            self.assertEqual(false.returncode,3)
            self.assertEqual(false.stdout,"")

    def test_ci_keeps_all_earlier_native_profiles_and_only_public_artifacts(self):
        full=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        stand=(ROOT/".github/workflows/map02-v147-generic-native-mmio.yml").read_text()
        for key in (
            "apply_map02_v147_generic_native_mmio",
            "check_map02_v147_native_bounded_c",
            "check_map02_v147_native_generic_mmio",
            "test_map02_v147_generic_native_mmio.py",
            "VH147_NATIVE_BOUNDED_MMIO_PASS",
            "VH147_NATIVE_GENERIC_MMIO_SOURCE_BOUND_PASS",
            "VH147_COMPILED_BOUNDED_NATIVE_PASS",
            "VH147_PRIVATE_TRACE_DIR",
            "for mode in 04 13 22 31 40; do",
            "VH146_VERIFIED_FD_NATIVE_LAUNCH_PASS",
            "path: proof/public/",
        ):
            self.assertIn(key,full)
        for key in ("test_map02_v147_generic_native_mmio.py",
                    "no_retail_exe_in_public_tests=1"):
            self.assertIn(key,stand)


if __name__=="__main__":
    unittest.main()
