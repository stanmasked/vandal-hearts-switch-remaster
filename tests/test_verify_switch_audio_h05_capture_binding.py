#!/usr/bin/env python3
"""Stage 235 host-only pre/post H05 CSV identity vs independently captured bundle."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import capture_switch_audio_sd_csv as capture  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_h05_capture_binding as binding  # noqa: E402
from test_verify_switch_audio_h05_csv_persistence import OldCSVPersistenceTests  # noqa: E402
from test_verify_switch_audio_bundle import write_session  # noqa: E402


class H05CapturedEvidenceTests(unittest.TestCase):
    def setUp(self):
        scenario = OldCSVPersistenceTests("runTest")
        scenario.setUp()
        self.addCleanup(scenario.doCleanups)
        self.case = scenario
        self.host = scenario.fixture
        scenario.record()
        scenario.add_new()
        self.review = self.host.base / "saved-h05-recheck.json"
        self.report = scenario.recheck()
        self.review.write_text(json.dumps(self.report, indent=2), encoding="utf-8")
        self.review_sha = bundle.digest_file(self.review)[1]
        self.output = self.host.output
        self.capture([scenario.old, scenario.already, scenario.new])

    def capture(self, names):
        return capture.capture(
            self.host.source_bundle, self.host.sd_root,
            self.host.plan, names, self.output)

    def run_review(self, **updates):
        params = dict(
            source_bundle=self.host.source_bundle,
            transfer_plan=self.host.plan,
            captured=self.output,
            baseline_path=self.case.baseline,
            baseline_sha256=self.case.pinned,
            review_path=self.review,
            review_sha256=self.review_sha,
        )
        params.update(updates)
        return binding.examine(**params)

    def modify_review(self, key, new):
        obj = json.loads(self.review.read_text(encoding="utf-8"))
        obj[key] = new
        self.review.write_text(json.dumps(obj), encoding="utf-8")
        self.review_sha = bundle.digest_file(self.review)[1]

    def test_exact_capture_preserves_pins_and_never_claims_switch_pass(self):
        x = self.run_review()
        self.assertEqual(x["result"],
                         "H05_CAPTURED_EVIDENCE_CONSISTENT_FOR_MANUAL_REVIEW")
        self.assertEqual(x["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(x["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertEqual(x["captured_session_count"], 3)
        self.assertEqual(x["old_csv"]["name"], self.case.old)
        self.assertEqual(x["old_csv"]["captured_path"],
                         capture.layout(1, self.case.old))
        self.assertEqual(x["new_csv"]["captured_path"],
                         capture.layout(3, self.case.new))
        self.assertEqual(x["old_csv"]["sha256"], self.report["old_csv_sha256"])
        self.assertEqual(x["new_csv"]["sha256"], self.report["new_csv_sha256"])
        self.assertFalse(x["second_run_attested"])
        self.assertFalse(x["audible_audio_attested"])
        self.assertFalse(x["physical_sd_attested"])

    def test_only_old_and_new_selected_is_a_valid_ordered_capture(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=self.host.base) as d:
            alternate = Path(d) / "subset"
            capture.capture(self.host.source_bundle, self.host.sd_root,
                            self.host.plan, [self.case.old, self.case.new], alternate)
            check = self.run_review(captured=alternate)
            self.assertEqual(check["captured_session_count"], 2)
            self.assertEqual(check["new_csv"]["captured_path"],
                             capture.layout(2, self.case.new))

    def test_reversed_sessions_are_not_accepted_as_second_run(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=self.host.base) as d:
            out = Path(d) / "reversed"
            capture.capture(self.host.source_bundle, self.host.sd_root,
                            self.host.plan, [self.case.new, self.case.old], out)
            with self.assertRaisesRegex(binding.BindingError, "SESSION_ORDER_WRONG"):
                self.run_review(captured=out)

    def test_missing_new_csv_in_capture_is_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=self.host.base) as d:
            out = Path(d) / "missing"
            capture.capture(self.host.source_bundle, self.host.sd_root,
                            self.host.plan, [self.case.old], out)
            with self.assertRaisesRegex(binding.BindingError,
                                        "OLD_OR_NEW_CSV_MISSING"):
                self.run_review(captured=out)

    def test_missing_old_csv_in_capture_is_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=self.host.base) as d:
            out = Path(d) / "missing"
            capture.capture(self.host.source_bundle, self.host.sd_root,
                            self.host.plan, [self.case.new], out)
            with self.assertRaisesRegex(binding.BindingError,
                                        "OLD_OR_NEW_CSV_MISSING"):
                self.run_review(captured=out)

    def test_review_sha_independently_pinned_and_edited_json_rejected(self):
        self.review.write_bytes(self.review.read_bytes() + b" ")
        with self.assertRaisesRegex(binding.BindingError, "REVIEW_SHA256_MISMATCH"):
            self.run_review()

    def test_wrong_original_baseline_sha_rejected(self):
        with self.assertRaisesRegex(Exception, "H05_BASELINE_SHA256_MISMATCH"):
            self.run_review(baseline_sha256="f" * 64)

    def test_edited_pinned_baseline_rejected_even_if_review_unchanged(self):
        self.case.baseline.write_bytes(self.case.baseline.read_bytes() + b"x")
        with self.assertRaisesRegex(Exception, "H05_BASELINE_SHA256_MISMATCH"):
            self.run_review()

    def test_hardware_pass_forged_in_review_rejected_even_if_rehashed(self):
        self.modify_review("hardware_status", "PASS")
        with self.assertRaisesRegex(binding.BindingError, "hardware PASS"):
            self.run_review()

    def test_forged_attestation_flag_rejected(self):
        self.modify_review("physical_second_run_attested", True)
        with self.assertRaisesRegex(binding.BindingError, "hardware PASS"):
            self.run_review()

    def test_changed_review_baseline_binding_rejected(self):
        self.modify_review("baseline_sha256", "0" * 64)
        with self.assertRaisesRegex(binding.BindingError,
                                    "BEFORE_AFTER_IDENTITY_MISMATCH"):
            self.run_review()

    def test_changed_review_old_csv_digest_rejected(self):
        self.modify_review("old_csv_sha256", "e" * 64)
        with self.assertRaisesRegex(binding.BindingError,
                                    "BEFORE_AFTER_IDENTITY_MISMATCH"):
            self.run_review()

    def test_changed_review_new_csv_digest_rejected(self):
        self.modify_review("new_csv_sha256", "e" * 64)
        with self.assertRaisesRegex(binding.BindingError,
                                    "CAPTURED_CSV_SHA256_MISMATCH"):
            self.run_review()

    def test_review_claims_new_file_present_before_snapshot_is_rejected(self):
        self.modify_review("new_csv_name", self.case.already)
        with self.assertRaisesRegex(binding.BindingError, "EXISTED_BEFORE"):
            self.run_review()

    def test_review_missing_session_metadata_field_rejected(self):
        self.modify_review("manual_signoff", "AUTOMATED_PASS")
        with self.assertRaisesRegex(binding.BindingError, "hardware PASS"):
            self.run_review()

    def test_review_duplicate_json_keys_rejected(self):
        self.review.write_text('{"result":"a","result":"b"}')
        self.review_sha = bundle.digest_file(self.review)[1]
        with self.assertRaises(bundle.BundleError):
            self.run_review()

    def test_changed_source_manifest_rejected_against_pre_run_sha(self):
        source_manifest = self.host.source_bundle / bundle.MANIFEST_NAME
        data = json.loads(source_manifest.read_text())
        data["git_sha"] = "e" * 40
        source_manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(binding.BindingError,
                                    "PINNED_SOURCE_MANIFEST_CHANGED"):
            self.run_review()

    def test_changed_transfer_plan_rejected_even_if_still_parseable(self):
        data = json.loads(self.host.plan.read_text())
        data["git_sha"] = "e" * 40
        self.host.plan.write_text(json.dumps(data))
        with self.assertRaisesRegex(binding.BindingError,
                                    "PINNED_SD_TRANSFER_PLAN_CHANGED"):
            self.run_review()

    def test_byte_corruption_of_captured_csv_fails_strict_audit(self):
        path = self.output / capture.layout(2, self.case.already)
        path.write_bytes(path.read_bytes() + b"altered")
        with self.assertRaises(bundle.BundleError):
            self.run_review()

    def test_captured_wrong_git_run_identity_is_rejected(self):
        p = self.output / bundle.MANIFEST_NAME
        manifest = json.loads(p.read_text())
        manifest["ci_run_url"] = (
            "https://github.com/stanmasked/vandal-hearts-switch-remaster/"
            "actions/runs/42")
        p.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(binding.BindingError,
                                    "CAPTURED_BUILD_IDENTITY_MISMATCH"):
            self.run_review()

    def test_capture_with_unreported_new_csv_is_rejected(self):
        from tempfile import TemporaryDirectory
        name = "audio-diagnostics-0003.csv"
        write_session(self.host.audio_dir / name, pages=1930)
        with TemporaryDirectory(dir=self.host.base) as d:
            out = Path(d) / "unattributed"
            capture.capture(self.host.source_bundle, self.host.sd_root,
                            self.host.plan, [self.case.old, self.case.new, name], out)
            with self.assertRaisesRegex(binding.BindingError,
                                        "NEW_CSV_NOT_PRESENT_IN_REVIEW"):
                self.run_review(captured=out)

    def test_additional_new_csv_can_be_marked_unattributed_without_claiming_launch(self):
        from tempfile import TemporaryDirectory
        name = "audio-diagnostics-0003.csv"
        write_session(self.host.audio_dir / name, pages=1930)
        self.modify_review("additional_new_csv_names_unattributed", [name])
        with TemporaryDirectory(dir=self.host.base) as d:
            out = Path(d) / "unattributed"
            capture.capture(self.host.source_bundle, self.host.sd_root,
                            self.host.plan, [self.case.old, self.case.new, name], out)
            data = self.run_review(captured=out)
            self.assertEqual(data["unattributed_additional_captured_csv"], [name])
            self.assertFalse(data["second_run_attested"])

    def test_h05_claimed_new_csv_must_not_recycle_prior_bytes(self):
        self.modify_review("new_csv_sha256", self.report["old_csv_sha256"])
        with self.assertRaisesRegex(binding.BindingError,
                                    "NEW_CSV_REUSED_OLD_BYTES"):
            self.run_review()

    def test_inputs_remain_exactly_same_after_analysis(self):
        watch = [self.case.baseline, self.review, self.host.plan,
                 self.host.source_bundle / bundle.MANIFEST_NAME,
                 self.output / bundle.MANIFEST_NAME,
                 self.output / capture.layout(1, self.case.old),
                 self.output / capture.layout(3, self.case.new)]
        before = [p.read_bytes() for p in watch]
        self.run_review()
        self.assertEqual(before, [p.read_bytes() for p in watch])

    def test_cli_valid_and_bad_pin(self):
        command = [sys.executable, str(ROOT / "tools" /
                                      "verify_switch_audio_h05_capture_binding.py"),
                   "--source-bundle", str(self.host.source_bundle),
                   "--transfer-plan", str(self.host.plan),
                   "--captured", str(self.output),
                   "--h05-baseline", str(self.case.baseline),
                   "--baseline-sha256", self.case.pinned,
                   "--h05-review", str(self.review),
                   "--review-sha256", self.review_sha]
        valid = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertEqual(json.loads(valid.stdout)["result"],
                         "H05_CAPTURED_EVIDENCE_CONSISTENT_FOR_MANUAL_REVIEW")
        self.assertEqual(json.loads(valid.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        command[-1] = "f" * 64
        invalid = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2, invalid.stdout + invalid.stderr)
        self.assertEqual(json.loads(invalid.stdout)["result"], "INVALID_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
