#!/usr/bin/env python3
"""Private native run challenge: source-only no-replay and nonattestation tests."""
from __future__ import annotations
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
    synthetic_source_claims,encode_events
)
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.apply_map02_v143_atomic_private_receipt import native_atomic_private_receipt_code
from tools.apply_map02_v144_private_run_challenge import (
    native_challenge_bound_receipt_code,patch_native_challenge_writer
)
from tools.check_map02_v144_native_challenge_c import sample_challenge_c
from tools.check_map02_v144_run_challenge import (
    SIDECAR,_read_private_challenge,_independent_synthetic_receipt_bytes,
    verify_native_run_challenge,
)


class BoundFreshNativeMipsReceipt(unittest.TestCase):
    def setUp(self):
        _,_,self.records=synthetic_source_claims()
        self.first=b"bc452e98d6a41f709308de5b2ac7610f\n"
        self.second=b"c2578a11e0d446af9b33d004af6b1243\n"

    def _make(self,root,nonce=None,receipt_data=None):
        output=Path(root)/"receipt"
        expected=Path(root)/"expected"
        output.mkdir(mode=0o700)
        expected.mkdir(mode=0o700)
        path=output/"vh142-interpreter-mmio.jsonl"
        path.write_bytes(encode_events(self.records)
                         if receipt_data is None else receipt_data)
        path.chmod(0o600)
        sidecar=output/SIDECAR
        sidecar.write_bytes(self.first if nonce is None else nonce)
        sidecar.chmod(0o600)
        pre=expected/"challenge.hex"
        pre.write_bytes(self.first)
        pre.chmod(0o600)
        return path,pre,sidecar

    def test_source_authored_receipt_and_independent_challenge_match(self):
        with tempfile.TemporaryDirectory(prefix="vh144-unit-") as root:
            receipt,expected,sidecar=self._make(root)
            result=verify_native_run_challenge(receipt,expected)
            self.assertEqual(result["events"],19)
            self.assertIs(result["fresh_externally_supplied_run_challenge_matched"],True)
            self.assertIs(result["complete_source_authored_mips_tuple_sha256_matched"],True)
            self.assertIs(result["retail_original_executed"],False)
            self.assertIs(result["runtime_producer_cryptographically_authenticated"],False)
            self.assertIs(result["nintendo_switch_hd_parity_proven"],False)
            self.assertEqual(_read_private_challenge(expected),self.first)
            self.assertEqual(_independent_synthetic_receipt_bytes(),
                             encode_events(self.records))

    def test_replay_another_run_challenge_refused_even_if_receipt_identical(self):
        with tempfile.TemporaryDirectory(prefix="vh144-replay-") as root:
            receipt,expected,sidecar=self._make(root,nonce=self.second)
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,expected)
            sidecar.write_bytes(self.first)
            self.assertTrue(verify_native_run_challenge(
                receipt,expected)["fresh_externally_supplied_run_challenge_matched"])

    def test_missing_wrong_mode_symlink_and_malformed_sidecar_refused(self):
        with tempfile.TemporaryDirectory(prefix="vh144-bad-") as root:
            receipt,expected,sidecar=self._make(root)
            for raw in (b"",b"1"*31+b"\n",b"f"*33+b"\n",
                        self.first.upper(),b"g"*32+b"\n",
                        self.first[:-1],self.first+b"\n",
                        b"0"*31+b" \n"):
                sidecar.write_bytes(raw)
                with self.subTest(kind="noncanonical"),self.assertRaises(Refused):
                    verify_native_run_challenge(receipt,expected)
            sidecar.write_bytes(self.first)
            sidecar.chmod(0o644)
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,expected)
            sidecar.chmod(0o600)
            sidecar.unlink()
            sidecar.symlink_to(expected)
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,expected)
            sidecar.unlink()
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,expected)

    def test_expected_challenge_must_be_independently_retained_and_private(self):
        with tempfile.TemporaryDirectory(prefix="vh144-ext-") as root:
            receipt,expected,sidecar=self._make(root)
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,sidecar)
            expected.chmod(0o644)
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,expected)
            expected.chmod(0o600)
            expected.write_bytes(self.second)
            with self.assertRaises(Refused):
                verify_native_run_challenge(receipt,expected)

    def test_sw_word_gp0_value_and_event_order_mutations_refused(self):
        variants=[]
        for index,field,bits in ((2,1,1),(0,3,1),(3,2,0x80000000)):
            changed=list(self.records)
            arr=list(changed[index])
            arr[field]^=bits
            changed[index]=tuple(arr)
            variants.append(encode_events(changed))
        changed=list(self.records)
        changed[0],changed[1]=changed[1],changed[0]
        variants.append(encode_events(changed))
        for i,bytes_ in enumerate(variants):
            with tempfile.TemporaryDirectory(prefix="vh144-tamper-") as root:
                receipt,expected,sidecar=self._make(root,receipt_data=bytes_)
                with self.subTest(i=i),self.assertRaises(Refused):
                    verify_native_run_challenge(receipt,expected)

    def test_cli_refuses_replay_without_emitting_nonce_paths_pcs_or_hashes(self):
        with tempfile.TemporaryDirectory(prefix="vh144-cli-") as root:
            receipt,expected,sidecar=self._make(root)
            args=[sys.executable,"-m","tools.check_map02_v144_run_challenge",
                  str(receipt),str(expected)]
            ok=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,
                              timeout=20,check=False)
            self.assertEqual(ok.returncode,0)
            self.assertIn("VH144_NATIVE_RUN_CHALLENGE_BOUND_PASS",ok.stdout)
            self.assertEqual(ok.stderr,"")
            for secret in (str(receipt),str(expected),self.first.decode().strip(),
                           str(self.records[0][0]),str(self.records[0][2])):
                self.assertNotIn(secret,ok.stdout)
            false=subprocess.run(args+["--expect-refusal"],cwd=ROOT,
                                 capture_output=True,text=True,
                                 timeout=20,check=False)
            self.assertEqual(false.returncode,3)
            self.assertEqual(false.stdout,"")
            sidecar.write_bytes(self.second)
            no=subprocess.run(args+["--expect-refusal"],cwd=ROOT,
                              capture_output=True,text=True,
                              timeout=20,check=False)
            self.assertEqual(no.returncode,0)
            self.assertIn("VH144_REPLAYED_OR_CHANGED_NATIVE_RECEIPT_REJECTED",no.stdout)

    def test_exact_native_writer_compiles_and_requires_fresh_challenge(self):
        older=native_atomic_private_receipt_code()
        changed=patch_native_challenge_writer(older)
        self.assertIn("vh144_write_challenge(dirfd,fresh_hex,&challenge_created)",changed)
        self.assertIn("if(ok!=0 && challenge_created)",changed)
        self.assertIn("vh142_write_all(fd,hex,32u)",changed)
        self.assertIn("VH144_RECEIPT_CHALLENGE_HEX",changed)
        self.assertEqual(changed.count("vh142_capture(psxRegisters"),1)
        self.assertEqual(changed.count("vh142_write_receipt(const char *"),1)
        self.assertNotIn("GPU_writeData(",changed)
        self.assertNotIn("SysPrintf(",changed)
        sample=sample_challenge_c()
        self.assertIn("vh144_write_challenge",sample)

    def test_full_pinned_emulator_and_independent_ci_cover_replay_refusal(self):
        main=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v144-run-challenge.yml").read_text()
        for part in (
            "apply_map02_v144_private_run_challenge",
            "check_map02_v144_native_challenge_c",
            "check_map02_v144_run_challenge",
            "test_map02_v144_run_challenge.py",
            "VH144_NATIVE_RUN_CHALLENGE_BOUND_PASS",
            "VH144_REPLAYED_OR_CHANGED_NATIVE_RECEIPT_REJECTED",
            "VH144_RECEIPT_CHALLENGE_HEX",
            "VH142_NATIVE_PRIVATE_RECEIPT_PASS",
            "VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED",
            "for mode in 04 13 22 31 40; do",
            "path: proof/public/",
        ):
            self.assertIn(part,main)
        for part in (
            "test_map02_v144_run_challenge.py",
            "check_map02_v144_native_challenge_c",
            "no_retail_exe_in_public_tests=1",
        ):
            self.assertIn(part,isolated)


if __name__=="__main__":
    unittest.main()
