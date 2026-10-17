#!/usr/bin/env python3
"""Stage 234 host-only H05 original CSV preservation and fresh-file regression."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import analyze_switch_audio_log as audio  # noqa: E402
import capture_switch_audio_sd_csv as capture  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_h05_csv_persistence as h05  # noqa: E402
import verify_switch_audio_sd_transfer as transfer  # noqa: E402
from test_capture_switch_audio_sd_csv import RawSDCaptureTests  # noqa: E402
from test_verify_switch_audio_bundle import write_session  # noqa: E402


class OldCSVPersistenceTests(unittest.TestCase):
    def setUp(self):
        fixture = RawSDCaptureTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.old = fixture.names[0]
        self.already = fixture.names[1]
        self.new = "audio-diagnostics-0002.csv"
        self.baseline = fixture.base / "independent-h05-baseline.json"
        self.original_bytes = (fixture.audio_dir / self.old).read_bytes()
        self.pinned = None

    def record(self):
        output = h05.record(
            self.fixture.source_bundle, self.fixture.sd_root,
            self.fixture.plan, self.old, self.baseline)
        self.pinned = output["baseline_sha256"]
        return output

    def add_new(self, pages=1500):
        write_session(self.fixture.audio_dir / self.new, pages=pages)

    def recheck(self, **changes):
        kw = {
            "source_bundle": self.fixture.source_bundle,
            "sd_root": self.fixture.sd_root,
            "plan": self.fixture.plan,
            "baseline_path": self.baseline,
            "expected_sha256": self.pinned,
            "new_csv_name": self.new,
            "operator_confirmed_second_run": True,
        }
        kw.update(changes)
        return h05.recheck(**kw)

    def cli(self, mode, *opts):
        return subprocess.run(
            [sys.executable,
             str(ROOT / "tools" / "verify_switch_audio_h05_csv_persistence.py"),
             mode, "--source-bundle", str(self.fixture.source_bundle),
             "--sd-root", str(self.fixture.sd_root),
             "--transfer-plan", str(self.fixture.plan), *opts],
            capture_output=True, text=True, check=False)

    def test_h05_stable_old_csv_new_file_is_manual_review_only(self):
        recorded = self.record()
        self.add_new()
        result = self.recheck()
        self.assertEqual(recorded["result"], "H05_OLD_CSV_BASELINE_RECORDED")
        self.assertEqual(result["result"],
                         "H05_FILE_PERSISTENCE_CONSISTENT_FOR_MANUAL_REVIEW")
        self.assertEqual(result["old_csv_sha256"], bundle.digest_file(
            self.fixture.audio_dir / self.old)[1])
        self.assertEqual(result["new_csv_name"], self.new)
        self.assertEqual(result["existing_csv_retained_count"], 2)
        self.assertEqual(result["additional_new_csv_names_unattributed"], [])
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertFalse(result["physical_second_run_attested"])
        self.assertFalse(result["audio_attested"])
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")

    def test_canonical_original_baseline_hash_can_be_checked_independently(self):
        result = self.record()
        self.assertEqual(result["baseline_sha256"],
                         bundle.digest_file(self.baseline)[1])
        self.assertEqual(
            len(h05.read_baseline(self.baseline, self.pinned)["existing_csv"]), 2)

    def test_new_csv_already_present_before_old_snapshot_is_rejected(self):
        self.add_new()
        self.record()
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "NEW_CSV_ALREADY_PRESENT_AT_BASELINE"):
            self.recheck()

    def test_new_csv_missing_after_baseline_is_rejected(self):
        self.record()
        with self.assertRaisesRegex(h05.PersistenceError, "NEW_CSV_MISSING"):
            self.recheck()

    def test_old_file_changed_after_baseline_is_detected(self):
        self.record()
        self.add_new()
        write_session(self.fixture.audio_dir / self.old, pages=2200)
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "H05_OLD_CSV_CHANGED_OR_REMOVED"):
            self.recheck()

    def test_old_file_removed_after_baseline_is_detected(self):
        self.record()
        self.add_new()
        (self.fixture.audio_dir / self.old).unlink()
        with self.assertRaisesRegex(h05.PersistenceError, "H05_OLD_CSV_CHANGED_OR_REMOVED"):
            self.recheck()

    def test_nonselected_preexisting_csv_rewrite_is_not_silently_ignored(self):
        self.record()
        self.add_new()
        write_session(self.fixture.audio_dir / self.already, pages=2500)
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "PREEXISTING_CSV_CHANGED_OR_REMOVED"):
            self.recheck()

    def test_new_file_must_have_different_payload_from_old(self):
        self.record()
        shutil.copyfile(self.fixture.audio_dir / self.old,
                        self.fixture.audio_dir / self.new)
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "NEW_CSV_IDENTICAL_TO_OLD_PAYLOAD"):
            self.recheck()

    def test_new_file_cannot_duplicate_another_preexisting_csv(self):
        self.record()
        shutil.copyfile(self.fixture.audio_dir / self.already,
                        self.fixture.audio_dir / self.new)
        with self.assertRaisesRegex(
                h05.PersistenceError,
                "NEW_CSV_DUPLICATES_PREEXISTING_CSV_PAYLOAD"):
            self.recheck()

    def test_new_file_must_be_completed_with_exit(self):
        self.record()
        self.add_new()
        path = self.fixture.audio_dir / self.new
        path.write_text(path.read_text().replace(",EXIT,", ",STATE,"))
        with self.assertRaisesRegex(h05.PersistenceError, "INCOMPLETE_CSV_EXPORT"):
            self.recheck()

    def test_new_bad_csv_header_fails_without_writing_any_sd_file(self):
        self.record()
        (self.fixture.audio_dir / self.new).write_bytes(b"invalid,header\n1,2\n")
        with self.assertRaises(audio.LogFormatError):
            self.recheck()

    def test_partial_tmp_blocks_before_or_after(self):
        tmp = self.fixture.audio_dir / "audio-diagnostics-0002.csv.tmp"
        tmp.write_bytes(b"incomplete")
        with self.assertRaisesRegex(capture.CaptureError, "INCOMPLETE_SD_EXPORT"):
            self.record()
        tmp.unlink()
        self.record()
        self.add_new()
        tmp.write_bytes(b"incomplete")
        with self.assertRaisesRegex(capture.CaptureError, "INCOMPLETE_SD_EXPORT"):
            self.recheck()

    def test_symlinked_prior_csv_rejected(self):
        path = self.fixture.audio_dir / self.old
        path.unlink()
        path.symlink_to(self.fixture.audio_dir / self.already)
        with self.assertRaisesRegex(capture.CaptureError, "symbolic link"):
            self.record()

    def test_wrong_old_name_and_duplicate_new_name_rejected(self):
        with self.assertRaises(capture.CaptureError):
            h05.record(self.fixture.source_bundle, self.fixture.sd_root,
                       self.fixture.plan, "../audio-diagnostics-0000.csv",
                       self.baseline)
        self.record()
        with self.assertRaisesRegex(h05.PersistenceError, "NEW_CSV_IS_OLD_FILE"):
            self.recheck(new_csv_name=self.old)

    def test_operator_confirmation_required(self):
        self.record()
        self.add_new()
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "OPERATOR_CONFIRMATION_REQUIRED"):
            self.recheck(operator_confirmed_second_run=False)

    def test_baseline_sha_anchor_mandatory(self):
        self.record()
        self.add_new()
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "independent baseline SHA-256"):
            self.recheck(expected_sha256="")
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "H05_BASELINE_SHA256_MISMATCH"):
            self.recheck(expected_sha256="f" * 64)

    def test_changed_baseline_rejected_even_if_sd_source_is_unchanged(self):
        self.record()
        self.add_new()
        self.baseline.write_bytes(self.baseline.read_bytes() + b" ")
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "H05_BASELINE_SHA256_MISMATCH"):
            self.recheck()

    def test_rehashed_baseline_forged_hardware_status_is_rejected(self):
        self.record()
        data = h05.read_baseline(self.baseline, self.pinned)
        data["physical_second_run_attested"] = True
        self.baseline.write_bytes(h05.bytes_for(data))
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "must never claim physical testing"):
            h05.read_baseline(
                self.baseline, bundle.digest_file(self.baseline)[1])

    def test_rehashed_baseline_changed_old_digest_not_accepted(self):
        self.record()
        data = h05.read_baseline(self.baseline, self.pinned)
        data["old_csv_sha256"] = "0" * 64
        self.baseline.write_bytes(h05.bytes_for(data))
        with self.assertRaisesRegex(h05.PersistenceError,
                                    "fingerprint differs"):
            h05.read_baseline(
                self.baseline, bundle.digest_file(self.baseline)[1])

    def test_duplicate_json_keys_in_baseline_are_rejected(self):
        self.record()
        self.baseline.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaises(bundle.BundleError):
            h05.read_baseline(self.baseline, bundle.digest_file(self.baseline)[1])

    def test_source_nro_changed_after_baseline_is_rejected(self):
        self.record()
        self.add_new()
        self.fixture.sd_nro.write_bytes(self.fixture.sd_nro.read_bytes() + b"x")
        with self.assertRaises(transfer.TransferError):
            self.recheck()

    def test_source_transfer_plan_changed_after_baseline_is_rejected(self):
        self.record()
        self.add_new()
        obj = json.loads(self.fixture.plan.read_text())
        obj["source_manifest_sha256"] = "f" * 64
        self.fixture.plan.write_text(json.dumps(obj))
        with self.assertRaises(transfer.TransferError):
            self.recheck()

    def test_old_csv_remains_byte_identical_and_all_inputs_are_read_only(self):
        self.record()
        self.add_new()
        paths = [
            self.fixture.sd_nro, self.fixture.audio_dir / self.old,
            self.fixture.audio_dir / self.already,
            self.fixture.audio_dir / self.new,
            self.fixture.source_bundle / bundle.MANIFEST_NAME,
            self.fixture.plan, self.baseline,
        ]
        before = {str(f): f.read_bytes() for f in paths}
        self.recheck()
        self.assertEqual(before, {str(f): f.read_bytes() for f in paths})
        self.assertEqual(self.original_bytes,
                         (self.fixture.audio_dir / self.old).read_bytes())

    def test_more_than_one_new_filename_is_listed_as_unattributed(self):
        self.record()
        self.add_new()
        other = "audio-diagnostics-0003.csv"
        write_session(self.fixture.audio_dir / other, pages=1950)
        result = self.recheck()
        self.assertEqual(result["additional_new_csv_names_unattributed"], [other])

    def test_preexisting_output_refused_without_overwrite(self):
        self.baseline.write_bytes(b"existing")
        with self.assertRaisesRegex(h05.PersistenceError, "refusing overwrite"):
            self.record()
        self.assertEqual(self.baseline.read_bytes(), b"existing")

    def test_baseline_cannot_be_written_on_sd_or_inside_bundle(self):
        for out in (self.fixture.audio_dir / "pin.json",
                    self.fixture.source_bundle / "pin.json"):
            with self.subTest(path=out), self.assertRaisesRegex(
                    h05.PersistenceError, "outside"):
                h05.record(self.fixture.source_bundle, self.fixture.sd_root,
                           self.fixture.plan, self.old, out)
            self.assertFalse(out.exists())

    def test_cli_record_and_recheck_json_success(self):
        report = self.cli(
            "record", "--old-csv", self.old, "--output", str(self.baseline))
        self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
        pinned = json.loads(report.stdout)["baseline_sha256"]
        self.add_new()
        rechecked = self.cli(
            "recheck", "--baseline", str(self.baseline),
            "--expected-baseline-sha256", pinned,
            "--new-csv", self.new, "--operator-confirmed-second-run")
        self.assertEqual(rechecked.returncode, 0,
                         rechecked.stdout + rechecked.stderr)
        self.assertEqual(json.loads(rechecked.stdout)["result"],
                         "H05_FILE_PERSISTENCE_CONSISTENT_FOR_MANUAL_REVIEW")
        self.assertEqual(json.loads(rechecked.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")

    def test_cli_missing_operator_confirmation_fails_closed(self):
        self.record()
        self.add_new()
        outcome = self.cli(
            "recheck", "--baseline", str(self.baseline),
            "--expected-baseline-sha256", self.pinned,
            "--new-csv", self.new)
        self.assertEqual(outcome.returncode, 2)
        self.assertEqual(json.loads(outcome.stdout)["result"], "INVALID_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
