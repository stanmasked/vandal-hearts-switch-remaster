#!/usr/bin/env python3
"""Stage 231 synthetic readback before/after operator-claimed SD reinsertion."""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_sd_reinsert as reinsert  # noqa: E402
import verify_switch_audio_sd_transfer as transfer  # noqa: E402
import verify_switch_audio_build_provenance as provenance  # noqa: E402
from test_verify_switch_audio_launch_gate import LaunchGateTests  # noqa: E402
from test_verify_switch_audio_live_preflight import NOW  # noqa: E402


class SDReinsertTests(unittest.TestCase):
    def setUp(self):
        gate = LaunchGateTests("runTest")
        gate.setUp()
        self.addCleanup(gate.doCleanups)
        self.gate = gate
        gate.copy_sd()
        self.baseline = gate.gh.base / "saved-before-manual-reinsert.json"
        self.saved_hash = None

    def record(self, **options):
        kw = {"api_fetch": self.gate.fetch, "now": NOW}
        kw.update(options)
        out = reinsert.record(
            self.gate.gh.folder, self.gate.gh.archive, self.gate.sd_root,
            self.gate.plan, self.gate.gh.run_id, self.gate.gh.artifact_id,
            self.baseline, **kw)
        self.saved_hash = out["baseline_sha256"]
        return out

    def verify(self, **options):
        opts = {"api_fetch": self.gate.fetch,
                "now": NOW + timedelta(minutes=5),
                "operator_confirmed_reinsert": True}
        opts.update(options)
        return reinsert.recheck(
            self.gate.gh.folder, self.gate.gh.archive,
            self.gate.sd_root, self.gate.plan,
            self.gate.gh.run_id, self.gate.gh.artifact_id,
            self.baseline, self.saved_hash, **opts)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" /
                                 "verify_switch_audio_sd_reinsert.py"), *args],
            capture_output=True, text=True, check=False)

    def test_baseline_and_recheck_same_nro_not_hardware_pass(self):
        original = self.record()
        self.assertEqual(original["result"], "PRE_REMOUNT_SD_READBACK_RECORDED")
        self.assertEqual(original["hardware_status"], "HARDWARE NOT TESTED")
        self.assertFalse(original["physical_sd_attested"])
        after = self.verify()
        self.assertEqual(after["result"], "POST_REINSERT_LOCAL_NRO_BYTES_MATCH")
        self.assertEqual(after["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(after["baseline_sha256"], original["baseline_sha256"])
        self.assertEqual(after["installed_nro_sha256"],
                         self.gate.gh.sha256(self.gate.sd_file))
        self.assertEqual(after["operator_reinsert_claim"],
                         "SELF_REPORTED_NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(after["physical_sd_medium"], "NOT_ATTESTED")
        self.assertEqual(after["audible_music"], "NOT_TESTED")
        self.assertEqual(after["sd_power_loss_durability"], "NOT_TESTED")

    def test_hash_of_baseline_is_full_exact_file_sha(self):
        original = self.record()
        self.assertEqual(original["baseline_sha256"],
                         bundle.digest_file(self.baseline)[1])
        parsed = reinsert.read_baseline(self.baseline, self.saved_hash)
        self.assertEqual(parsed["run_id"], self.gate.gh.run_id)
        self.assertEqual(parsed["installed_nro_sha256"],
                         self.gate.gh.sha256(self.gate.sd_file))
        self.assertFalse(parsed["remount_performed"])

    def test_remount_is_manual_claim_not_inferred_from_matching_bytes(self):
        self.record()
        with self.assertRaisesRegex(reinsert.ReinsertError,
                                    "OPERATOR_CONFIRMATION_REQUIRED"):
            self.verify(operator_confirmed_reinsert=False)

    def test_changed_sd_nro_same_size_is_rejected(self):
        self.record()
        changed = bytearray(self.gate.sd_file.read_bytes())
        changed[-1] ^= 1
        self.gate.sd_file.write_bytes(changed)
        with self.assertRaisesRegex(transfer.TransferError, "SHA-256/size"):
            self.verify()

    def test_removed_sd_copy_rejected(self):
        self.record()
        self.gate.sd_file.unlink()
        with self.assertRaisesRegex(transfer.TransferError, "missing"):
            self.verify()

    def test_wrong_baseline_digest_rejected(self):
        self.record()
        with self.assertRaisesRegex(reinsert.ReinsertError,
                                    "BASELINE_SHA256_MISMATCH"):
            self.verify(expected_baseline_sha256="0" * 64)  # replaced separately below

    def test_corrupted_baseline_detected_even_with_same_name(self):
        self.record()
        self.baseline.write_bytes(self.baseline.read_bytes() + b" ")
        with self.assertRaisesRegex(reinsert.ReinsertError,
                                    "BASELINE_SHA256_MISMATCH"):
            self.verify()

    def test_rehashed_baseline_cannot_claim_hardware_pass_or_remount(self):
        self.record()
        for key, value in (("hardware_status", "PASS"),
                           ("remount_performed", True),
                           ("physical_sd_attested", True)):
            baseline = reinsert.read_baseline(self.baseline, self.saved_hash)
            modified = {**baseline, key: value}
            self.baseline.write_bytes(reinsert.baseline_bytes(modified))
            new_hash = bundle.digest_file(self.baseline)[1]
            with self.subTest(key=key), self.assertRaises(reinsert.ReinsertError):
                reinsert.read_baseline(self.baseline, new_hash)
            self.baseline.write_bytes(reinsert.baseline_bytes(baseline))

    def test_duplicate_json_field_is_rejected(self):
        self.record()
        self.baseline.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(bundle.BundleError, "duplicate JSON key"):
            reinsert.read_baseline(
                self.baseline, bundle.digest_file(self.baseline)[1])

    def test_baseline_output_never_inside_sd_or_evidence(self):
        for output in (self.gate.sd_root / "baseline.json",
                       self.gate.gh.folder / "baseline.json"):
            with self.subTest(path=output), self.assertRaisesRegex(
                    reinsert.ReinsertError, "outside source evidence"):
                reinsert.record(
                    self.gate.gh.folder, self.gate.gh.archive,
                    self.gate.sd_root, self.gate.plan,
                    self.gate.gh.run_id, self.gate.gh.artifact_id,
                    output, api_fetch=self.gate.fetch, now=NOW)
            self.assertFalse(output.exists())

    def test_existing_baseline_not_overwritten(self):
        self.record()
        original = self.baseline.read_bytes()
        with self.assertRaisesRegex(reinsert.ReinsertError,
                                    "refusing overwrite"):
            self.record()
        self.assertEqual(self.baseline.read_bytes(), original)

    def test_wrong_run_or_attempt_after_record_rejected(self):
        self.record()
        self.gate.gh.run["run_attempt"] = 2
        with self.assertRaisesRegex(provenance.ProvenanceError, "attempt"):
            self.verify()

    def test_github_branch_move_requires_fresh_gate(self):
        self.record()
        self.gate.ref["object"]["sha"] = "f" * 40
        with self.assertRaisesRegex(provenance.ProvenanceError, "STALE_BUILD"):
            self.verify()

    def test_zip_mutation_detected_during_post_check(self):
        self.record()
        with self.gate.gh.archive.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(provenance.ProvenanceError):
            self.verify()

    def test_source_plan_mutation_rejected(self):
        self.record()
        planned = json.loads(self.gate.plan.read_text())
        planned["git_sha"] = "f" * 40
        self.gate.plan.write_text(json.dumps(planned))
        with self.assertRaises(transfer.TransferError):
            self.verify()

    def test_manifest_changed_without_nro_edit_is_rejected(self):
        self.record()
        manifest_path = self.gate.gh.folder / bundle.MANIFEST_NAME
        current = json.loads(manifest_path.read_text())
        current["ci_run_url"] = "https://github.com/other/other/actions/runs/1"
        manifest_path.write_text(json.dumps(current))
        with self.assertRaises(transfer.TransferError):
            self.verify()

    def test_recheck_time_cannot_precede_baseline(self):
        self.record()
        with self.assertRaisesRegex(reinsert.ReinsertError, "PREDATES_BASELINE"):
            self.verify(now=NOW - timedelta(seconds=10))

    def test_same_bytes_during_deliberate_simulated_unmount_does_not_prove_remount(self):
        self.record()
        target = self.gate.sd_file
        data = target.read_bytes()
        target.unlink()
        target.write_bytes(data)
        result = self.verify()
        self.assertEqual(result["physical_sd_medium"], "NOT_ATTESTED")
        self.assertEqual(result["operator_reinsert_claim"],
                         "SELF_REPORTED_NOT_INDEPENDENTLY_ATTESTED")

    def test_recheck_is_read_only_for_all_inputs(self):
        self.record()
        paths = [self.gate.gh.archive, self.gate.sd_file,
                 self.gate.gh.folder / self.gate.gh.nro,
                 self.gate.gh.folder / bundle.MANIFEST_NAME,
                 self.gate.plan, self.baseline]
        before = {str(p): p.read_bytes() for p in paths}
        self.verify()
        self.assertEqual(before, {str(p): p.read_bytes() for p in paths})

    def test_cli_requires_explicit_remount_confirmation(self):
        self.record()
        args = [
            "recheck", str(self.gate.gh.folder),
            "--artifact-zip", str(self.gate.gh.archive),
            "--sd-root", str(self.gate.sd_root),
            "--transfer-plan", str(self.gate.plan),
            "--run-id", str(self.gate.gh.run_id),
            "--artifact-id", str(self.gate.gh.artifact_id),
            "--baseline", str(self.baseline),
            "--expected-baseline-sha256", self.saved_hash,
        ]
        result = self.cli(*args)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["result"], "INVALID_EVIDENCE")
        self.assertEqual(json.loads(result.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")

    def test_baseline_recheck_cannot_change_selected_artifact(self):
        self.record()
        with self.assertRaisesRegex(reinsert.ReinsertError,
                                    "RECHECK_RUN_ID_CHANGED"):
            reinsert.recheck(
                self.gate.gh.folder, self.gate.gh.archive,
                self.gate.sd_root, self.gate.plan,
                self.gate.gh.run_id + 1, self.gate.gh.artifact_id,
                self.baseline, self.saved_hash, operator_confirmed_reinsert=True,
                api_fetch=self.gate.fetch, now=NOW)


if __name__ == "__main__":
    unittest.main()
