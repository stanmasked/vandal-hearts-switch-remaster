"""A truly spawned *synthetic* process exercises private MAP02 launcher."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from tools.run_map02_private_native_capture import capture


# No copyrighted game executable, assets or scenes are used by these tests.
STUB = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["VH_MAP02_GPU_CAPTURE_DIR"])
if "--hang" in sys.argv:
    import time
    time.sleep(5)
    sys.exit(0)
if "--exit-error" in sys.argv:
    sys.exit(6)
if "--no-capture" in sys.argv:
    sys.exit(0)
frame = int(os.environ["VH_MAP02_GPU_CAPTURE_FRAME"])
span = {
    "stage": "native_dda_span", "step": 0, "frame": frame,
    "primitive_ordinal": 0, "primitive_type": 2, "y": 12,
    "x_start": 10, "x_bound": 20, "clip_l": 5, "clip_r": 25,
    "clip_t": 10, "clip_b": 15
}
(root / "dda-native-spans.jsonl").write_text(json.dumps(span) + "\n")
for i, phase in enumerate(("before", "after")):
    event = {
        "stage": "native_vram", "step": i, "frame": frame,
        "phase": phase, "operation": "draw",
        "snapshot": f"gpu-{i:04d}-vram.bin",
        "rect": None, "dest": [0, 0], "rgb": [0, 0, 0],
        "primitive_type": 2, "semi": 0, "window": [0, 0, 0, 0],
        "draw_mode": [0, 0, 0], "upload": "", "ft4": None,
    }
    with (root / "gpu-native-events.jsonl").open("a") as log:
        log.write(json.dumps(event) + "\n")
    (root / event["snapshot"]).write_bytes(bytes(1024 * 512 * 2))
'''


class PrivateNativeLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.capture_dir = self.base / "private-capture"
        self.capture_dir.mkdir(mode=0o700)
        self.capture_dir.chmod(0o700)
        self.executable = self.base / "synthetic-gpu-probe"
        self.executable.write_text(STUB, encoding="utf-8")
        self.executable.chmod(0o700)
        self.preflight = self.base / "preflight.json"
        self.summary = self.base / "summary.json"
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "VH_MAP02_GPU_CAPTURE_DIR": str(self.capture_dir),
            "VH_MAP02_PUTPIXEL_DIR": str(self.capture_dir),
            "VH_MAP02_GPU_CAPTURE_FRAME": "3",
            "VH_MAP02_PUTPIXEL_FRAME": "3",
            "VH_MAP02_PUTPIXEL_X": "12",
            "VH_MAP02_PUTPIXEL_Y": "12",
        }

    def run_synthetic(self, *args):
        return capture(self.executable, self.preflight, self.summary,
                       game_args=list(args), environ=self.env)

    def test_real_subprocess_produces_valid_private_trace(self):
        result = self.run_synthetic()
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 0)
        self.assertTrue(result["capture_verified"])
        self.assertIsNone(result["failure_category"])
        self.assertFalse(result["retail_map02_verified"])
        self.assertFalse(result["hd_replacement_authorized"])
        self.assertTrue(result["verification"]["native_gpu_binding"]["verified"])
        self.assertEqual(result["verification"]["dda_observation_mode"], "entered_only")
        self.assertFalse(result["verification"]["all_dda_journal_classes_observed"])
        self.assertEqual(result["verification"]["native_gpu_pairs_verified"], 1)
        self.assertEqual(len(result["verification"]["vram_snapshot_sha256_list_sha256"]), 64)
        for path in (self.preflight, self.summary):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.summary.read_text())["capture_verified"], True)
        flat = json.dumps(result)
        self.assertNotIn(str(self.capture_dir), flat)
        self.assertNotIn(str(self.executable), flat)
        self.assertNotIn('"x_start"', flat)

    def test_exit_nonzero_is_not_success_even_if_process_started(self):
        result = self.run_synthetic("--exit-error")
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 6)
        self.assertEqual(result["failure_category"], "process_exit_nonzero")
        self.assertFalse(result["capture_verified"])

    def test_zero_exit_without_gpu_data_is_not_verified(self):
        result = self.run_synthetic("--no-capture")
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 0)
        self.assertEqual(result["failure_category"],
                         "incomplete_or_invalid_private_capture")
        self.assertFalse(result["capture_verified"])

    def test_synthetic_process_timeout_is_terminated_and_unverified(self):
        result = capture(self.executable, self.preflight, self.summary,
                         environ=self.env, game_args=("--hang",), timeout=0.2)
        self.assertTrue(result["process_started"])
        self.assertFalse(result["capture_verified"])
        self.assertEqual(result["failure_category"], "process_timeout")
        self.assertIsNone(result["process_exit_code"])
        self.assertTrue(self.summary.exists())

    def test_never_overwrites_receipts_or_reuses_capture_directory(self):
        self.run_synthetic()
        with self.assertRaisesRegex(ValueError, "receipts already exist"):
            self.run_synthetic()
        self.preflight.unlink()
        self.summary.unlink()
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_synthetic()

    def test_bad_environment_or_receipt_inside_capture_never_launches(self):
        self.env["VH_MAP02_PUTPIXEL_FRAME"] = "4"
        with self.assertRaisesRegex(ValueError, "frames must match"):
            self.run_synthetic()
        self.assertFalse(self.preflight.exists())
        self.assertFalse(self.summary.exists())
        self.env["VH_MAP02_PUTPIXEL_FRAME"] = "3"
        with self.assertRaisesRegex(ValueError, "outside empty capture"):
            capture(self.executable, self.capture_dir / "preflight.json",
                    self.summary, environ=self.env)
        self.assertEqual(list(self.capture_dir.iterdir()), [])

    def test_receipt_parent_symlink_must_not_point_into_capture(self):
        alias = self.base / "capture-alias"
        alias.symlink_to(self.capture_dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside empty capture"):
            capture(self.executable, alias / "preflight.json",
                    self.summary, environ=self.env)
        with self.assertRaisesRegex(ValueError, "outside empty capture"):
            capture(self.executable, self.preflight,
                    alias / "summary.json", environ=self.env)
        self.assertEqual(list(self.capture_dir.iterdir()), [])
        self.assertFalse(self.preflight.exists())
        self.assertFalse(self.summary.exists())

    def test_args_are_not_reported(self):
        result = self.run_synthetic("--private-game-asset-reference")
        self.assertTrue(result["capture_verified"])
        self.assertNotIn("--private-game-asset-reference", json.dumps(result))
        self.assertNotIn("--private-game-asset-reference", self.summary.read_text())


if __name__ == "__main__":
    unittest.main()
