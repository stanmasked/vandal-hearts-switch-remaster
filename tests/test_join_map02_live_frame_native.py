"""Cross-replay the actual synthetic ELF pipe and conservative native witness join."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_capture_map02_live_frame_pipe import SOURCE
from tools.capture_map02_live_frame_pipe import capture
from tools import join_map02_live_frame_native as live_join


class LiveFrameNativeDigestJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-join-elf-")
        root = Path(cls.workspace.name)
        cls.source = root / "producer.c"
        cls.executable = root / "producer"
        cls.source.write_text(SOURCE, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise RuntimeError("selected native compiler unavailable")
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(cls.source), "-o", str(cls.executable)], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.workspace_single = tempfile.TemporaryDirectory(
            prefix="vh-map02-live-native-join-")
        self.addCleanup(self.workspace_single.cleanup)
        self.root = Path(self.workspace_single.name)
        self.live = self.root / "pipe"
        self.live.mkdir(mode=0o700)
        capture(self.executable, self.live, frame=123, width=2, height=2,
                executable_sha256=self.digest, timeout=5)
        self.pixels = (self.live / "process-frame.bgr555").read_bytes()
        self.claim = {
            "schema": "vh.map02.private-frame-native-join.v1",
            "frame": 123, "width": 2, "height": 2,
            "candidate_sha256": hashlib.sha256(self.pixels).hexdigest(),
            "reference_sha256": "1" * 64,
            "native_gpu_event_log_sha256": "2" * 64,
            "original_launch_receipt_sha256": "3" * 64,
            "strict_native_elf_probe_replay_verified": True,
            "same_frame_labels_verified": True,
            "private_frame_pair_stable_through_native_replay": True,
            "frame_bytes_causally_bound_to_executed_game": False,
            "pc_port_frame_capture_authenticated": False,
            "hd_replacement_authorized": False,
        }

    def join(self, side_effect=None):
        with patch.object(live_join, "bridge", side_effect=(
                side_effect if side_effect else lambda *a, **k: dict(self.claim))):
            return live_join.join(
                self.root / "pair", self.live,
                self.root / "gpu", self.root / "source",
                launch_receipt=self.root / "launch",
                preflight_report=self.root / "preflight",
                executable=self.executable)

    def test_actual_compiled_elf_pixel_hash_matches_claimed_candidate(self):
        result = self.join()
        self.assertEqual(result["candidate_sha256"],
                         hashlib.sha256(self.pixels).hexdigest())
        self.assertEqual(result["executable_sha256"], self.digest)
        self.assertTrue(result["candidate_pixels_match_replayed_live_pipe"])
        self.assertTrue(result["live_pipe_stable_during_native_replay"])
        self.assertFalse(result["same_process_gpu_event_and_frame_causality_authenticated"])
        self.assertFalse(result["retail_disc_or_ps1_reference_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        raw = json.dumps(result)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn(self.pixels.hex(), raw)

    def test_candidate_hash_mismatch_refused(self):
        self.claim["candidate_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "pixels differ"):
            self.join()

    def test_claimed_frame_mismatch_refused(self):
        self.claim["frame"] = 124
        with self.assertRaisesRegex(ValueError, "labels"):
            self.join()

    def test_claimed_dimensions_mismatch_refused(self):
        self.claim["width"] = 3
        with self.assertRaisesRegex(ValueError, "labels"):
            self.join()

    def test_incomplete_native_probe_refused(self):
        self.claim["strict_native_elf_probe_replay_verified"] = False
        with self.assertRaisesRegex(ValueError, "gate absent"):
            self.join()

    def test_false_native_provenance_refused(self):
        self.claim["pc_port_frame_capture_authenticated"] = True
        with self.assertRaisesRegex(ValueError, "unproven provenance"):
            self.join()

    def test_fake_native_bridge_schema_refused(self):
        self.claim["schema"] = "not-the-native-bridge"
        with self.assertRaisesRegex(ValueError, "schema"):
            self.join()

    def test_live_pipe_changes_during_native_audit_refused(self):
        def replace(*args, **kwargs):
            pixels = b"\x01\x00" * 4
            (self.live / "process-frame.bgr555").write_bytes(pixels)
            receipt = self.live / "process-frame.json"
            item = json.loads(receipt.read_text())
            item["image_sha256"] = hashlib.sha256(pixels).hexdigest()
            receipt.write_text(json.dumps(item, sort_keys=True) + "\n")
            return dict(self.claim)
        with self.assertRaisesRegex(ValueError, "changed through native GPU replay"):
            self.join(side_effect=replace)

    def test_no_genuine_capture_or_hd_claim_even_for_equal_bytes(self):
        report = self.join()
        self.assertNotIn("same_process_verified", report)
        self.assertFalse(report["same_process_gpu_event_and_frame_causality_authenticated"])
        self.assertFalse(report["hd_replacement_authorized"])


if __name__ == "__main__":
    unittest.main()
