"""End-to-end bridge review tests using synthetic game stdout, not game assets."""
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.capture_map02_runtime import capture
from tools.report_map02_bridge import markdown_review, review_capture
from test_capture_map02_runtime import fixture
from test_evaluate_map02_session import full_events


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

    def test_two_real_c_emitted_map_loads_are_reported_independently(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("C compiler required")
        for second, expected_code, expected_variant in (
            (full_events(), 0, "PRS"),
            (full_events(498, 550), 2, "undetermined"),
        ):
            with self.subTest(second_variant=second[0]["gfx"]), \
                 tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                executable, trace_dir = fixture(root, trace_mode="full")
                source = root / "fake-pcport.c"
                original = source.read_text(encoding="utf-8")
                added = "\n".join(f"puts({json.dumps(json.dumps(event))});"
                                  for event in second)
                self.assertIn("return 0;", original)
                source.write_text(original.replace("return 0;", added + "\nreturn 0;"),
                                  encoding="utf-8")
                subprocess.run([compiler, "-std=c11", str(source), "-o", str(executable)],
                               capture_output=True, text=True, check=True)
                directory = root / "capture"
                self.assertEqual(capture(executable, trace_dir, directory), expected_code)
                report = review_capture(directory)
                self.assertEqual(report["runtime_variant"], expected_variant)
                self.assertEqual(report["map_load_count"], 2)
                self.assertEqual(report["trace_events"], 12)
                self.assertEqual([episode["event_range"]
                                  for episode in report["map_loads"]],
                                 [{"first": 1, "last": 6}, {"first": 7, "last": 12}])
                self.assertEqual(report["faces"], [],
                                 "repeated game loads must never flatten two face sets")
                self.assertEqual([load["post_load_variant"]
                                  for load in report["map_loads"]],
                                 ["PRS", "PRS" if expected_code == 0 else "DAT"])
                self.assertEqual([load["faces"][0]["draw_gfx"]
                                  for load in report["map_loads"]],
                                 [641, 641 if expected_code == 0 else 498])
                self.assertFalse(report["pixels_visually_verified"])
                markdown = markdown_review(report)
                self.assertIn("Map load 1 — JSONL events 1–6", markdown)
                self.assertIn("Map load 2 — JSONL events 7–12", markdown)
                self.assertIn("Visible pixels confirmed:** no", markdown)

    def test_complementary_partial_map_loads_never_form_a_false_prs_verdict(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("C compiler required")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable, trace_dir = fixture(root, trace_mode="full")
            source = root / "fake-pcport.c"
            original = source.read_text(encoding="utf-8")
            first = [full_events()[0], full_events()[2], full_events()[3]]
            second = [full_events()[1], full_events()[4], full_events()[5]]
            emitted = "\n".join(f"puts({json.dumps(json.dumps(event))});"
                                 for event in first + second)
            # Keep the binary provenance strings created by the fixture, but
            # replace the stream with two intentionally incomplete load passes.
            source.write_text(original.split("int main(void) {", 1)[0]
                              + "int main(void) {\n" + emitted
                              + "\nreturn 0;\n}\n", encoding="utf-8")
            subprocess.run([compiler, "-std=c11", str(source), "-o", str(executable)],
                           capture_output=True, text=True, check=True)
            directory = root / "capture"
            self.assertEqual(capture(executable, trace_dir, directory), 2)
            report = review_capture(directory)
            self.assertEqual(report["trace_events"], 6)
            self.assertEqual(report["map_load_count"], 2)
            self.assertEqual(report["runtime_variant"], "undetermined")
            self.assertFalse(report["capture_complete"])
            self.assertEqual(report["faces"], [])
            self.assertTrue(any("map load 1: missing" in error
                                for error in report["errors"]))
            self.assertTrue(any("map load 2: missing" in error
                                for error in report["errors"]))
            self.assertEqual([x["event_range"] for x in report["map_loads"]],
                             [{"first": 1, "last": 3}, {"first": 4, "last": 6}])
            markdown = markdown_review(report)
            self.assertIn("Map load 1 — JSONL events 1–3", markdown)
            self.assertIn("Map load 2 — JSONL events 4–6", markdown)

    def test_unfinished_second_map_load_prevents_prs_verdict(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("C compiler required")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable, trace_dir = fixture(root, trace_mode="full")
            source = root / "fake-pcport.c"
            original = source.read_text(encoding="utf-8")
            incomplete = full_events()[:-1]
            added = "\n".join(f"puts({json.dumps(json.dumps(event))});"
                              for event in incomplete)
            source.write_text(original.replace("return 0;", added + "\nreturn 0;"),
                              encoding="utf-8")
            subprocess.run([compiler, "-std=c11", str(source), "-o", str(executable)],
                           capture_output=True, text=True, check=True)
            directory = root / "capture"
            self.assertEqual(capture(executable, trace_dir, directory), 2)
            report = review_capture(directory)
            self.assertEqual(report["map_load_count"], 2)
            self.assertFalse(report["capture_complete"])
            self.assertEqual(report["runtime_variant"], "undetermined")
            self.assertTrue(any("map load 2:" in e for e in report["errors"]))

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
