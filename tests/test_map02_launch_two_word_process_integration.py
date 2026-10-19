"""Spawn a REAL asset-free process and cross-replay native DDA and two-word FT4.

This harness is a synthetic file-emitting Python subprocess, NOT the
original Vandal Hearts executable and not a gameplay capture. It exercises
the otherwise independently unit-tested launcher, its persisted receipt,
the complete original-source GPU/VRAM/FT4 fixture and their joint verifier
without mocking ANY of the replay functions.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

import test_verify_map02_putpixel_multi_scope as fixture_module
from tools.audit_map02_launch_two_word_binding import audit_launch_two_word
from tools.run_map02_private_native_capture import capture
from tools.verify_map02_private_capture_receipt import replay_receipt


# The argument is an asset-free, entirely synthetic native witness directory
# built by Python test fixtures. Nothing is read from real game resources.
EMITTER = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1])
destination = Path(os.environ["VH_MAP02_GPU_CAPTURE_DIR"])
if "--empty" in sys.argv:
    sys.exit(0)
if not destination.is_dir() or any(destination.iterdir()):
    sys.exit(7)
for entry in source.iterdir():
    if not entry.is_file() or entry.is_symlink():
        sys.exit(8)
    shutil.copyfile(entry, destination / entry.name)
frame = int(os.environ["VH_MAP02_GPU_CAPTURE_FRAME"])
dda = {
    "stage": "native_dda_span",
    "step": 0, "frame": frame,
    "primitive_ordinal": 1, "primitive_type": 2,
    "y": 30, "x_start": 30, "x_bound": 35,
    "clip_l": 20, "clip_r": 45,
    "clip_t": 25, "clip_b": 40
}
(destination / "dda-native-spans.jsonl").write_text(
    json.dumps(dda, sort_keys=True) + "\n", encoding="utf-8")
'''


class SpawnedTwoWordCrossAuditTests(unittest.TestCase):
    def setUp(self):
        f = fixture_module.TwoWordPutPixelTests(
            methodName="test_interleaved_two_coordinates_bound_to_same_drawotag")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fixture = f
        self.source, self.template = f.source, f.native
        # Nested fixture classes can put self.source directly below
        # /tmp. Never create fixed receipt/native paths at that parent:
        # different unittest cases would collide and retain private bytes.
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-real-subprocess-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.native = root / "fresh-spawned-native"
        self.native.mkdir(mode=0o700)
        self.native.chmod(0o700)
        self.executable = root / "synthetic-file-emitter"
        self.executable.write_text(EMITTER, encoding="utf-8")
        self.executable.chmod(0o700)
        self.preflight = root / "process-preflight.json"
        self.receipt = root / "process-receipt.json"
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "VH_MAP02_GPU_CAPTURE_DIR": str(self.native),
            "VH_MAP02_PUTPIXEL_DIR": str(self.native),
            "VH_MAP02_GPU_CAPTURE_FRAME": "12",
            "VH_MAP02_PUTPIXEL_FRAME": "12",
            "VH_MAP02_PUTPIXEL_X": "30",
            "VH_MAP02_PUTPIXEL_Y": "30",
            "VH_MAP02_PUTPIXEL_X2": "35",
            "VH_MAP02_PUTPIXEL_Y2": "35",
        }

    def spawn(self, *options):
        return capture(
            self.executable, self.preflight, self.receipt,
            game_args=(str(self.template), *options),
            environ=self.env, timeout=10,
        )

    def cross_audit(self):
        return audit_launch_two_word(
            self.native, self.source,
            launch_receipt=self.receipt,
            preflight_report=self.preflight,
            executable=self.executable,
        )

    def test_actual_subprocess_two_verifiers_and_stable_receipt_agree(self):
        proc = self.spawn()
        self.assertTrue(proc["process_started"])
        self.assertEqual(proc["process_exit_code"], 0)
        self.assertTrue(proc["capture_verified"])
        self.assertFalse(proc["retail_map02_verified"])
        self.assertFalse(proc["hd_replacement_authorized"])
        self.assertEqual(proc["verification"]["native_gpu_pairs_verified"], 3)
        self.assertEqual(proc["verification"]["dda_observation_mode"], "entered_only")
        self.assertTrue(self.preflight.is_file())
        self.assertTrue(self.receipt.is_file())
        self.assertEqual(stat.S_IMODE(self.preflight.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.receipt.stat().st_mode), 0o600)

        independently_replayed = replay_receipt(
            self.native, receipt_file=self.receipt,
            preflight_report=self.preflight, executable=self.executable)
        joint = self.cross_audit()
        native_log_sha = hashlib.sha256(
            (self.native / "gpu-native-events.jsonl").read_bytes()).hexdigest()
        self.assertEqual(independently_replayed["native_gpu_event_log_sha256"],
                         native_log_sha)
        self.assertEqual(joint["native_gpu_event_log_sha256"], native_log_sha)
        self.assertEqual(joint["original_launch_receipt_sha256"],
                         independently_replayed["original_receipt_sha256"])
        self.assertEqual(joint["native_gpu_frame"], 12)
        self.assertEqual(joint["source_frame"], 411)
        self.assertEqual(joint["source_keyed_ft4_draws_checked"], 2)
        self.assertTrue(joint["private_dependency_inventory_stable_through_replays"])
        self.assertTrue(joint["original_launcher_receipt_replayed_twice"])
        for field in (
            "native_process_to_log_causality_authenticated",
            "retail_map02_gameplay_authenticated",
            "ps1_or_switch_pixel_equivalence_verified",
            "hd_replacement_authorized",
            "raw_pixel_coordinates_or_colors_emitted",
        ):
            self.assertFalse(joint[field])
        public = json.dumps(joint)
        for forbidden in (
            str(self.native), str(self.source), str(self.executable),
            '"x"', '"y"', '"before"', '"after"', '"front"', '"clut"', '"tpage"',
        ):
            self.assertNotIn(forbidden, public)

    def test_replayed_process_receipt_rejects_post_exit_native_vram_swap(self):
        proc = self.spawn()
        self.assertTrue(proc["capture_verified"])
        snapshot = self.native / "gpu-0003-vram.bin"
        changed = bytearray(snapshot.read_bytes())
        changed[0] ^= 1
        snapshot.write_bytes(changed)
        with self.assertRaises(ValueError):
            self.cross_audit()

    def test_cross_audit_rejects_source_ft4_change_after_real_process_exit(self):
        proc = self.spawn()
        self.assertTrue(proc["capture_verified"])
        source_log = self.source / "gpu-events.jsonl"
        source_log.write_bytes(source_log.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.cross_audit()

    def test_zero_exit_without_native_capture_remains_unverified(self):
        proc = self.spawn("--empty")
        self.assertTrue(proc["process_started"])
        self.assertEqual(proc["process_exit_code"], 0)
        self.assertFalse(proc["capture_verified"])
        self.assertEqual(proc["failure_category"],
                         "incomplete_or_invalid_private_capture")
        with self.assertRaises(ValueError):
            self.cross_audit()


if __name__ == "__main__":
    unittest.main()
