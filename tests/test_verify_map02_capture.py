"""Offline verification of Map02 capture evidence, no proprietary game bytes."""
import hashlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.capture_map02_runtime import capture
from tools.verify_map02_capture import verify_bundle
from test_capture_map02_runtime import fixture


class VerifyMap02CaptureTests(unittest.TestCase):
    def test_completed_capture_round_trip_and_strict_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable, prepared = fixture(root, trace_mode="full")
            bundle = root / "bundle"
            self.assertEqual(capture(executable, prepared, bundle), 0)
            outcome = verify_bundle(bundle)
            self.assertEqual(outcome["integrity"], "verified")
            self.assertTrue(outcome["complete_capture"])
            self.assertEqual(outcome["trace_events"], 6)
            self.assertEqual(
                [json.loads(line)["stage"] for line in
                 (bundle / "map02_trace.jsonl").read_text().splitlines()],
                ["post_load", "post_load", "visit", "draw", "visit", "draw"],
            )
            self.assertEqual(len(outcome["raw_log_sha256"]), 64)
            self.assertEqual(len(outcome["trace_jsonl_sha256"]), 64)
            strict = subprocess.run(
                [sys.executable, "-m", "tools.verify_map02_capture",
                 str(bundle), "--require-complete"],
                text=True, capture_output=True,
            )
            self.assertEqual(strict.returncode, 0, strict.stderr)
            self.assertEqual(json.loads(strict.stdout)["trace_events"], 6)

    def test_full_conflicting_or_unfinished_pass_stays_invalid_on_independent_replay(self):
        for mode, message in (
            ("full_draw_and_skip", "multiple terminal outcomes"),
            ("full_unfinished_visit", "nonempty visit without draw or skip"),
        ):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    executable, prepared = fixture(root, mode=mode, trace_mode="full")
                    bundle = root / "bundle"
                    self.assertEqual(capture(executable, prepared, bundle), 2)
                    integrity = verify_bundle(bundle)
                    self.assertEqual(integrity["integrity"], "verified")
                    self.assertFalse(integrity["complete_capture"])
                    report = json.loads((bundle / "capture_report.json").read_text())
                    self.assertTrue(any(message in err for err in report["analysis"]["errors"]))

    def test_full_capture_missing_visit_is_invalid_but_offline_integrity_verifies(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            executable, prepared = fixture(base, trace_mode="full",
                                           mode="full_missing_visit")
            bundle = base / "bundle"
            self.assertEqual(capture(executable, prepared, bundle), 2)
            outcome = verify_bundle(bundle)
            self.assertEqual(outcome["integrity"], "verified")
            self.assertFalse(outcome["complete_capture"])
            self.assertEqual(outcome["trace_events"], 5)
            report = json.loads((bundle / "capture_report.json").read_text())
            self.assertTrue(any("draw without preceding nonempty visit" in error
                                for error in report["analysis"]["errors"]))

    def test_incomplete_and_invalid_traces_are_verified_but_not_complete(self):
        for mode in ("incomplete", "invalid", "empty", "bad_stage"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    executable, prepared = fixture(root, mode=mode)
                    bundle = root / "bundle"
                    self.assertEqual(capture(executable, prepared, bundle), 2)
                    outcome = verify_bundle(bundle)
                    self.assertFalse(outcome["complete_capture"])
                    strict = subprocess.run(
                        [sys.executable, "-m", "tools.verify_map02_capture",
                         str(bundle), "--require-complete"],
                        text=True, capture_output=True,
                    )
                    self.assertEqual(strict.returncode, 1, strict.stderr)

    def test_raw_log_and_derived_jsonl_mutations_rejected(self):
        for name in ("game_stdout.log", "map02_trace.jsonl"):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    exe, prepared = fixture(root)
                    bundle = root / "bundle"
                    self.assertEqual(capture(exe, prepared, bundle), 0)
                    file = bundle / name
                    data = file.read_bytes()
                    file.write_bytes(data.replace(b"641", b"498", 1))
                    with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                        verify_bundle(bundle)

    def test_report_mutation_and_coordinated_derived_forgery_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, prepared = fixture(root)
            bundle = root / "bundle"
            self.assertEqual(capture(exe, prepared, bundle), 0)
            report_path = bundle / "capture_report.json"
            report = json.loads(report_path.read_text())
            saved = dict(report)
            report["analysis"] = {"errors": [], "observations": []}
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "analysis differs"):
                verify_bundle(bundle)
            report = saved
            derived = bundle / "map02_trace.jsonl"
            altered = derived.read_bytes().replace(b"641", b"498", 1)
            derived.write_bytes(altered)
            report["trace_jsonl_sha256"] = hashlib.sha256(altered).hexdigest()
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "does not match raw stdout"):
                verify_bundle(bundle)

    def test_valid_prefix_from_malformed_console_output_is_verifiable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, prepared = fixture(root)
            valid = '{"z":8,"x":19,"face":0,"stage":"post_load","gfx":641}'
            broken = '{"z":8,"x":19,"face":0,"stage":"draw","gfx":'
            exe.write_text(
                "#!/usr/bin/env python3\n"
                + f"print({valid!r})\n"
                + f"print({broken!r})\n",
                encoding="utf-8",
            )
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
            bundle = root / "bundle"
            self.assertEqual(capture(exe, prepared, bundle), 2)
            outcome = verify_bundle(bundle)
            self.assertEqual(outcome["trace_events"], 1)
            self.assertFalse(outcome["complete_capture"])

    def test_failed_process_launch_retains_verifiable_failure_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, prepared = fixture(root)
            exe.write_text("#!/path/that/does/not/exist\n", encoding="utf-8")
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
            bundle = root / "bundle"
            self.assertEqual(capture(exe, prepared, bundle), 1)
            outcome = verify_bundle(bundle)
            self.assertEqual(outcome["trace_events"], 0)
            self.assertFalse(outcome["complete_capture"])
            self.assertFalse((bundle / "map02_trace.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
