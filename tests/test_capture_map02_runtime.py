"""Host-only tests for the opt-in local map02 runtime capture command."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from tools.capture_map02_runtime import capture


def fixture(root: Path, mode="complete", modified=False):
    trace_dir = root / "prepared"
    trace_dir.mkdir()
    provenance = {
        "trace_mode": "legacy",
        "allow_modified_source": modified,
        "source_files": {
            name: {"matches_pinned": not modified}
            for name in ("src/core/graphics.c", "src/states/game_setup.c", "platform/pc/Makefile")
        },
    }
    (trace_dir / "source_provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    executable = root / "fake-pcport"
    events = [
        {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": 641},
        {"z": 11, "x": 11, "face": 0, "stage": "post_load", "gfx": 643},
        {"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": 641},
        {"z": 11, "x": 11, "face": 0, "stage": "draw", "gfx": 643},
    ]
    if mode == "incomplete":
        events = events[:2]
    if mode == "invalid":
        events[2]["gfx"] = 498
    if mode == "empty":
        events = []
    lines = ["booting pc-port", *(json.dumps(ev) for ev in events), "normal shutdown"]
    source = "#!/usr/bin/env python3\n" + "\n".join(
        ["import sys", f"print({chr(10).join(lines)!r})",
         f"raise SystemExit({7 if mode == 'crash' else 0})"]
    ) + "\n"
    executable.write_text(source, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable, trace_dir


class CaptureMap02RuntimeTests(unittest.TestCase):
    def test_complete_capture_writes_raw_log_jsonl_report_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            dest = base / "run"
            self.assertEqual(capture(exe, trace_dir, dest), 0)
            report = json.loads((dest / "capture_report.json").read_text())
            self.assertEqual(report["trace_events"], 4)
            self.assertEqual(report["analysis"]["errors"], [])
            self.assertEqual(report["analysis"]["draw_overall_variant"], "PRS")
            self.assertEqual(len(report["binary_sha256"]), 64)
            self.assertIn("booting pc-port", (dest / "game_stdout.log").read_text())
            self.assertEqual(len((dest / "map02_trace.jsonl").read_text().splitlines()), 4)
            with self.assertRaisesRegex(ValueError, "already exists"):
                capture(exe, trace_dir, dest)

    def test_incomplete_and_invalid_traces_fail_but_preserve_evidence(self):
        for mode in ("incomplete", "invalid", "empty"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as folder:
                    base = Path(folder)
                    exe, trace_dir = fixture(base, mode=mode)
                    dest = base / "run"
                    self.assertEqual(capture(exe, trace_dir, dest), 2)
                    self.assertTrue((dest / "game_stdout.log").exists())
                    report = json.loads((dest / "capture_report.json").read_text())
                    self.assertTrue(report["analysis"]["errors"])

    def test_modified_provenance_requires_explicit_override(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, modified=True)
            dest = base / "run"
            with self.assertRaisesRegex(ValueError, "--allow-modified-source"):
                capture(exe, trace_dir, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(capture(exe, trace_dir, dest, allow_modified_source=True), 0)
            self.assertTrue(json.loads((dest / "capture_report.json").read_text())
                            ["source_provenance"]["allow_modified_source"])

    def test_process_failure_is_not_mistaken_for_success(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, mode="crash")
            dest = base / "run"
            self.assertEqual(capture(exe, trace_dir, dest), 1)
            report = json.loads((dest / "capture_report.json").read_text())
            self.assertEqual(report["game_exit_code"], 7)


if __name__ == "__main__":
    unittest.main()
