#!/usr/bin/env python3
"""Stage 233 synthetic SD CSV capture regression; no real Switch/SD access."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import analyze_switch_audio_log as audio  # noqa: E402
import capture_switch_audio_sd_csv as capture  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_sd_transfer as transfer  # noqa: E402
from test_verify_switch_audio_bundle import (  # noqa: E402
    synthetic_structural_nro, write_session,
)


class RawSDCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source_bundle = self.base / "verified-source"
        (self.source_bundle / "nro").mkdir(parents=True)
        self.origin_nro = self.source_bundle / capture.NRO_PATH
        self.origin_nro.write_bytes(synthetic_structural_nro())
        self.sha = "a" * 40
        self.ci_url = (
            "https://github.com/stanmasked/vandal-hearts-switch-remaster/"
            "actions/runs/987654321")
        bundle.create(self.source_bundle, capture.NRO_PATH, [], self.sha, self.ci_url)
        self.sd_root = self.base / "mock-sd"
        self.audio_dir = self.sd_root / capture.AUDIO_DIR
        self.audio_dir.mkdir(parents=True)
        self.sd_nro = self.audio_dir / "vandal-hearts-prototype.nro"
        shutil.copyfile(self.origin_nro, self.sd_nro)
        self.names = ("audio-diagnostics-0000.csv", "audio-diagnostics-0001.csv")
        write_session(self.audio_dir / self.names[0], pages=1200)
        write_session(self.audio_dir / self.names[1], pages=1300)
        self.plan = self.base / "transfer-plan.json"
        transfer.create_plan(self.source_bundle, self.sd_root, self.plan)
        self.output = self.base / "captured-sessions"

    def capture(self, names=None):
        return capture.capture(
            self.source_bundle, self.sd_root, self.plan,
            list(self.names if names is None else names), self.output)

    def verify(self):
        return capture.verify(self.source_bundle, self.sd_root,
                              self.plan, self.output)

    def cli(self, action, *extra):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" /
                                 "capture_switch_audio_sd_csv.py"), action,
             "--source-bundle", str(self.source_bundle),
             "--sd-root", str(self.sd_root),
             "--transfer-plan", str(self.plan),
             *extra],
            capture_output=True, text=True, check=False)

    def test_two_csv_and_nro_are_exact_and_no_hardware_claim(self):
        report = self.capture()
        self.assertEqual(report["result"], "RAW_SD_CSV_COPIES_CAPTURED_AND_RECHECKED")
        self.assertEqual(report["session_count"], 2)
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["physical_session_independence"], "NOT_ATTESTED")
        self.assertEqual(report["source_sd_medium"], "NOT_ATTESTED")
        checked = bundle.inspect(self.output)
        self.assertEqual(checked["integrity"], "VERIFIED")
        self.assertEqual(checked["session_count"], 2)
        self.assertEqual(checked["telemetry_readiness"],
                         "ENOUGH_DATA_FOR_MANUAL_REVIEW")
        self.assertEqual(
            (self.output / capture.NRO_PATH).read_bytes(), self.sd_nro.read_bytes())
        for n, name in enumerate(self.names, 1):
            target = self.output / capture.layout(n, name)
            self.assertEqual(target.read_bytes(),
                             (self.audio_dir / name).read_bytes())

    def test_fresh_readback_detects_same_sd_bytes(self):
        self.capture()
        checked = self.verify()
        self.assertEqual(checked["result"], "CAPTURED_RAW_BYTES_MATCH_FRESH_SD_READBACK")
        self.assertEqual(checked["session_count"], 2)
        self.assertEqual(checked["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(len(checked["raw_csv_sha256"]), 2)

    def test_unselected_older_csv_is_not_silently_imported(self):
        older = "audio-diagnostics-9999.csv"
        write_session(self.audio_dir / older)
        report = self.capture([self.names[0]])
        self.assertEqual(report["session_count"], 1)
        self.assertFalse((self.output / older).exists())
        self.assertEqual(bundle.inspect(self.output)["session_count"], 1)
        self.assertEqual(self.verify()["session_count"], 1)

    def test_incomplete_sd_tmp_stops_capture_before_destination_exists(self):
        (self.audio_dir / "audio-diagnostics-0002.csv.tmp").write_bytes(b"partial")
        with self.assertRaisesRegex(capture.CaptureError, "INCOMPLETE_SD_EXPORT"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_missing_csv_never_creates_output(self):
        with self.assertRaisesRegex(capture.CaptureError, "missing"):
            self.capture(["audio-diagnostics-9999.csv"])
        self.assertFalse(self.output.exists())

    def test_empty_csv_rejected_before_copy(self):
        (self.audio_dir / self.names[0]).write_bytes(b"")
        with self.assertRaisesRegex(capture.CaptureError, "empty"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_bad_header_fails_strict_csv_parser_without_copy(self):
        (self.audio_dir / self.names[0]).write_text("invalid,fields\n0,1\n")
        with self.assertRaises(audio.LogFormatError):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_truncated_csv_not_completed_rejected_by_strict_parser(self):
        path = self.audio_dir / self.names[0]
        with path.open("a", encoding="utf-8") as stream:
            stream.write("incomplete-row\n")
        with self.assertRaises(audio.LogFormatError):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_symlink_csv_to_outside_or_other_session_rejected(self):
        original = self.audio_dir / self.names[0]
        original.unlink()
        original.symlink_to(self.audio_dir / self.names[1])
        with self.assertRaisesRegex(capture.CaptureError, "symbolic link"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_duplicate_csv_names_and_traversal_rejected(self):
        for names in ([self.names[0], self.names[0]],
                      ["../../audio-diagnostics-0000.csv"],
                      ["x/audio-diagnostics-0000.csv"],
                      ["audio-diagnostics-0000.csv.tmp"], [], list(self.names) * 33):
            with self.subTest(names=names), self.assertRaises(capture.CaptureError):
                self.capture(names)
            self.assertFalse(self.output.exists())

    def test_output_directory_preexists_no_overwrite(self):
        self.output.mkdir()
        sentinel = self.output / "do-not-overwrite.txt"
        sentinel.write_bytes(b"private data")
        with self.assertRaisesRegex(capture.CaptureError, "refusing overwrite"):
            self.capture()
        self.assertEqual(sentinel.read_bytes(), b"private data")

    def test_output_inside_sd_rejected(self):
        self.output = self.audio_dir / "evidence"
        with self.assertRaisesRegex(capture.CaptureError, "outside"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_output_inside_original_evidence_rejected(self):
        self.output = self.source_bundle / "extra"
        with self.assertRaisesRegex(capture.CaptureError, "outside"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_source_sd_nro_changed_or_swapped_rejected(self):
        self.sd_nro.write_bytes(self.sd_nro.read_bytes() + b"x")
        with self.assertRaises(transfer.TransferError):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_source_manifest_changed_after_transfer_plan_rejected(self):
        manifest = self.source_bundle / bundle.MANIFEST_NAME
        payload = json.loads(manifest.read_text())
        payload["git_sha"] = "b" * 40
        manifest.write_text(json.dumps(payload))
        with self.assertRaises(transfer.TransferError):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_empty_ci_run_url_not_assumed_provenance(self):
        manifest = self.source_bundle / bundle.MANIFEST_NAME
        payload = json.loads(manifest.read_text())
        payload["ci_run_url"] = ""
        manifest.write_text(json.dumps(payload))
        self.plan.unlink()
        transfer.create_plan(self.source_bundle, self.sd_root, self.plan)
        with self.assertRaisesRegex(capture.CaptureError, "GitHub run URL"):
            self.capture()

    def test_source_mutation_during_copy_fails_and_leaves_no_output(self):
        real_copy = capture.copy_strict
        def mutate_during_copy(source, destination, cap, expected):
            if source.name == self.names[0]:
                with source.open("ab") as stream:
                    stream.write(b"\nchanged")
            return real_copy(source, destination, cap, expected)
        with patch.object(capture, "copy_strict", side_effect=mutate_during_copy):
            with self.assertRaisesRegex(capture.CaptureError, "SOURCE_CHANGED_BEFORE_COPY"):
                self.capture()
        self.assertFalse(self.output.exists())
        self.assertFalse(any(self.base.glob(".vh-audio-capture-*")))

    def test_captured_csv_modified_is_rejected_against_manifest(self):
        self.capture()
        copied = self.output / capture.layout(1, self.names[0])
        copied.write_bytes(copied.read_bytes() + b"damage")
        with self.assertRaises(bundle.BundleError):
            self.verify()

    def test_original_sd_csv_changed_after_capture_detected(self):
        self.capture()
        path = self.audio_dir / self.names[0]
        write_session(path, pages=1550)
        with self.assertRaisesRegex(capture.CaptureError, "CAPTURED_CSV_IDENTITY_MISMATCH"):
            self.verify()

    def test_captured_nro_modified_is_rejected(self):
        self.capture()
        nro = self.output / capture.NRO_PATH
        nro.write_bytes(nro.read_bytes() + b"bad")
        with self.assertRaises(bundle.BundleError):
            self.verify()

    def test_capture_never_modifies_sd_source_manifest_or_plan(self):
        observed = [
            self.sd_nro, self.origin_nro,
            self.audio_dir / self.names[0],
            self.audio_dir / self.names[1],
            self.source_bundle / bundle.MANIFEST_NAME,
            self.plan,
        ]
        before = {str(p):p.read_bytes() for p in observed}
        self.capture()
        self.verify()
        self.assertEqual(before, {str(p):p.read_bytes() for p in observed})

    def test_cli_capture_then_verify_reports_hardware_not_tested(self):
        args = ["--csv", self.names[0], "--csv", self.names[1],
                "--output", str(self.output)]
        outcome = self.cli("capture", *args)
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertEqual(json.loads(outcome.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        confirmed = self.cli("verify", "--captured", str(self.output))
        self.assertEqual(confirmed.returncode, 0, confirmed.stdout + confirmed.stderr)
        self.assertEqual(json.loads(confirmed.stdout)["result"],
                         "CAPTURED_RAW_BYTES_MATCH_FRESH_SD_READBACK")

    def test_cli_invalid_fails_closed(self):
        result = self.cli("capture", "--csv", "audio-diagnostics-0000.csv.tmp",
                          "--output", str(self.output))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["result"], "INVALID_EVIDENCE")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
