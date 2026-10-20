"""Asset-free tests of RU source receipt + full trace independent replay gate."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_capture_map02_runtime import fixture as pc_fixture
from test_check_map02_ru_receipt import fixture as receipt_fixture
from tools.capture_map02_runtime import capture
from tools.reconcile_map02_ru_runtime_trace import (
    check_source_provenance, ensure_analysis, reconcile,
)


class RuTraceReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        exe, trace = pc_fixture(cls.root, trace_mode="full")
        cls.bundle = cls.root / "pc-capture"
        if capture(exe, trace, cls.bundle) != 0:
            raise AssertionError("synthetic full trace did not complete")
        cls.receipt = cls.root / "receipt.json"
        cls.receipt.write_text(json.dumps(receipt_fixture()), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_roundtrip_replays_real_synthetic_stdout(self):
        result = reconcile(self.receipt, self.bundle)
        self.assertEqual(result["pc_trace_consistent_variant"], "PRS")
        self.assertEqual(result["separate_map_loads_checked"], 1)
        self.assertTrue(result["source_receipt_consistent"])
        self.assertTrue(result["capture_stdout_independently_replayed"])
        self.assertFalse(result["same_owned_disc_used_by_executable_proven"])
        self.assertFalse(result["native_gpu_ft4_and_vram_verified_by_this_tool"])
        self.assertFalse(result["original_gameplay_authenticated"])

    def test_cli_outputs_only_aggregate_evidence(self):
        completed = subprocess.run(
            [sys.executable, "-m", "tools.reconcile_map02_ru_runtime_trace",
             str(self.receipt), str(self.bundle)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["pc_trace_consistent_variant"], "PRS")
        self.assertNotIn(str(self.root), completed.stdout)
        self.assertNotIn("74048", completed.stdout)
        self.assertNotIn("texture", completed.stdout.lower())

    def test_refuses_modified_source_receipt(self):
        original = self.receipt.read_bytes()
        data = json.loads(original)
        data["prs"]["lba"] += 1
        try:
            self.receipt.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prs.lba"):
                reconcile(self.receipt, self.bundle)
        finally:
            self.receipt.write_bytes(original)

    def test_rejects_legacy_or_modified_upstream_provenance(self):
        report = json.loads((self.bundle / "capture_report.json").read_text())
        for change in ("legacy", "modified", "source"):
            bad = copy.deepcopy(report)
            if change == "legacy":
                bad["source_provenance"]["trace_mode"] = "legacy"
            elif change == "modified":
                bad["source_provenance"]["allow_modified_source"] = True
            else:
                name = next(iter(bad["source_provenance"]["source_files"]))
                bad["source_provenance"]["source_files"][name]["matches_pinned"] = False
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    check_source_provenance(bad)

    def test_incomplete_full_trace_is_not_accepted(self):
        report = json.loads((self.bundle / "capture_report.json").read_text())
        case = copy.deepcopy(report["analysis"])
        case["observations"][0]["draw_status"] = "skipped_in_observed_passes"
        with self.assertRaisesRegex(ValueError, "not submitted"):
            ensure_analysis(case)
        case = copy.deepcopy(report["analysis"])
        case["observations"][0]["visit_observation_count"] = 0
        with self.assertRaisesRegex(ValueError, "renderer visit"):
            ensure_analysis(case)

    def test_rejects_mismatched_gfx_or_duplicate_face(self):
        report = json.loads((self.bundle / "capture_report.json").read_text())
        altered = copy.deepcopy(report["analysis"])
        altered["observations"][0]["draw_gfx"] = 498
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            ensure_analysis(altered)
        altered = copy.deepcopy(report["analysis"])
        altered["observations"][1] = copy.deepcopy(altered["observations"][0])
        with self.assertRaisesRegex(ValueError, "duplicated"):
            ensure_analysis(altered)

    def test_rejects_variant_drift_across_loads(self):
        report = json.loads((self.bundle / "capture_report.json").read_text())
        first = copy.deepcopy(report["analysis"])
        second = copy.deepcopy(first)
        second["post_load_overall_variant"] = "DAT"
        second["draw_overall_variant"] = "DAT"
        for row in second["observations"]:
            row["post_load_gfx"] -= 143 if row["z"] == 8 else 93
            row["draw_gfx"] = row["post_load_gfx"]
        combined = {
            "errors": [],
            "map_loads": [first, second],
            "post_load_overall_variant": "mixed",
            "draw_overall_variant": "mixed",
        }
        with self.assertRaisesRegex(ValueError, "changed across"):
            ensure_analysis(combined)

    def test_rejects_symlink_capture_log(self):
        # Replacing one named file with a link may redirect a private read.
        log = self.bundle / "game_stdout.log"
        other = self.root / "saved-stdout.log"
        original = log.read_bytes()
        try:
            log.unlink()
            other.write_bytes(original)
            log.symlink_to(other)
            with self.assertRaisesRegex(ValueError, "redirected"):
                reconcile(self.receipt, self.bundle)
        finally:
            if log.is_symlink():
                log.unlink()
            log.write_bytes(original)
            other.unlink(missing_ok=True)

    def test_rejects_capture_report_modification_via_replay(self):
        report_path = self.bundle / "capture_report.json"
        original = report_path.read_bytes()
        report = json.loads(original)
        report["analysis"]["observations"][0]["draw_gfx"] = 498
        try:
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "analysis differs"):
                reconcile(self.receipt, self.bundle)
        finally:
            report_path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
