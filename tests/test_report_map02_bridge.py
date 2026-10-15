"""End-to-end bridge review tests using synthetic game stdout, not game assets."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.capture_map02_runtime import capture
from tools.report_map02_bridge import markdown_review, review_capture
from test_capture_map02_runtime import fixture


class ReportMap02BridgeTests(unittest.TestCase):
    def test_full_trace_reports_prs_both_submissions_without_pixel_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe, trace_dir = fixture(root, trace_mode="full")
            output = root / "capture"
            self.assertEqual(capture(exe, trace_dir, output), 0)
            report = review_capture(output)
            self.assertEqual(report["evidence_integrity"], "verified")
            self.assertTrue(report["capture_complete"])
            self.assertEqual(report["runtime_variant"], "PRS")
            self.assertEqual(report["trace_events"], 6)
            self.assertFalse(report["pixels_visually_verified"])
            self.assertEqual([face["post_load_gfx"] for face in report["faces"]],
                             [641, 643])
            self.assertEqual([face["draw_gfx"] for face in report["faces"]],
                             [641, 643])
            self.assertEqual([face["renderer_visits"] for face in report["faces"]],
                             [1, 1])
            self.assertEqual([face["draw_submissions"] for face in report["faces"]],
                             [1, 1])
            self.assertEqual(report["faces"][0]["paths"], ["normal"])
            markdown = markdown_review(report)
            self.assertIn("Visible pixels confirmed:** no", markdown)
            self.assertIn("AddPrim GFX", markdown)
            self.assertIn("u=not recorded", markdown)
            self.assertNotIn("Visible pixels confirmed:** yes", markdown)

            json_path = root / "review.json"
            md_path = root / "review.md"
            result = subprocess.run(
                [sys.executable, "-m", "tools.report_map02_bridge",
                 str(output), "--json", str(json_path),
                 "--markdown", str(md_path), "--require-complete"],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(json_path.read_text())["runtime_variant"], "PRS")
            self.assertEqual(md_path.read_text(), markdown)
            # Never replace a report from a previous review without consent.
            again = subprocess.run(
                [sys.executable, "-m", "tools.report_map02_bridge",
                 str(output), "--markdown", str(md_path)],
                text=True, capture_output=True,
            )
            self.assertNotEqual(again.returncode, 0)

    def test_dat_decision_uses_recorded_values_not_prs_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe, trace_dir = fixture(root, trace_mode="legacy")
            original = exe.read_text()
            self.assertIn("641", original)
            self.assertIn("643", original)
            exe.write_text(original.replace("641", "498").replace("643", "550"))
            output = root / "capture"
            self.assertEqual(capture(exe, trace_dir, output), 0)
            report = review_capture(output)
            self.assertEqual(report["runtime_variant"], "DAT")
            self.assertEqual([face["post_load_variant"] for face in report["faces"]],
                             ["DAT", "DAT"])
            self.assertEqual([face["draw_variant"] for face in report["faces"]],
                             ["DAT", "DAT"])
            self.assertEqual([face["draw_gfx"] for face in report["faces"]],
                             [498, 550])
            self.assertFalse(report["pixels_visually_verified"])

    def test_partial_capture_never_declares_runtime_variant(self):
        for mode in ("incomplete", "invalid", "empty", "bad_stage"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                exe, trace_dir = fixture(root, mode=mode, trace_mode="legacy")
                output = root / "capture"
                self.assertEqual(capture(exe, trace_dir, output), 2)
                report = review_capture(output)
                self.assertEqual(report["runtime_variant"], "undetermined")
                self.assertFalse(report["capture_complete"])
                strict = subprocess.run(
                    [sys.executable, "-m", "tools.report_map02_bridge",
                     str(output), "--require-complete"],
                    text=True, capture_output=True,
                )
                self.assertEqual(strict.returncode, 1, strict.stderr)

    def test_report_rejects_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe, trace_dir = fixture(root)
            output = root / "capture"
            self.assertEqual(capture(exe, trace_dir, output), 0)
            path = output / "map02_trace.jsonl"
            path.write_bytes(path.read_bytes() + b'{"forged":true}\n')
            with self.assertRaisesRegex(ValueError, "byte count changed"):
                review_capture(output)


if __name__ == "__main__":
    unittest.main()
