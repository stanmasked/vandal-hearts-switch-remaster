"""Negative structural tests for the asset-free same-run GPU window witness."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_map02_native_gpu_windows import (
    INDEX, SCHEMA, verify_native_windows,
)
from tools.verify_map02_vram_timeline import VRAM_BYTES


def jsonline(obj):
    return (json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n").encode()


class NativeGpuWindowEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "capture"
        self.root.mkdir(mode=0o700)
        self.window = self.root / "window-000"
        self.window.mkdir(mode=0o700)
        self.snapshots = []
        for word in (0, 1, 1, 2):
            data = bytearray(VRAM_BYTES)
            data[:2] = word.to_bytes(2, "little")
            self.snapshots.append(bytes(data))
        self.events = []
        for step in range(4):
            event = {
                "stage": "native_vram", "step": step, "frame": 7,
                "phase": "before" if step % 2 == 0 else "after",
                "operation": "draw", "snapshot": f"gpu-{step:04d}-vram.bin",
                "rect": None, "dest": [0, 0], "rgb": [200, 0, 0],
                "primitive_type": 1, "semi": 0,
                "window": [0, 0, 0, 0], "draw_mode": [0, 0, 0],
                "upload": "", "ft4": None,
            }
            self.events.append(event)
            (self.window / event["snapshot"]).write_bytes(self.snapshots[step])
        (self.window / "gpu-native-events.jsonl").write_bytes(
            b"".join(jsonline(e) for e in self.events)
        )
        self.status = {
            "schema": SCHEMA, "gpu_draw_frame": 7,
            "window_capacity_events": 64,
            "configured_windows": 2, "windows_written": 1,
            "observed_hooks": 4, "before_hooks": 2, "after_hooks": 2,
            "draw_before_hooks": 2, "transfer_before_hooks": 0,
            "indexed_hooks": 4, "written_hooks": 4,
            "limit_reached": False, "walk_finished": True,
            "hooks_balanced": True, "write_failed": False,
            "recorded_window_closed_without_detected_loss": True,
        }
        self.save_status()

    def save_status(self):
        (self.root / INDEX).write_bytes(jsonline(self.status))

    def verify(self):
        return verify_native_windows(self.root, target_frame=7)

    def test_small_one_window_is_not_mislabeled_as_complete_gameplay(self):
        result = self.verify()
        self.assertEqual(result["recorded_windows"], 1)
        self.assertEqual(result["globally_ordered_native_gpu_events"], 4)
        self.assertEqual(result["vram_bridge_checks"], 1)
        self.assertEqual(
            result["final_native_vram_sha256"],
            hashlib.sha256(self.snapshots[-1]).hexdigest())
        self.assertFalse(result["whole_original_gameplay_frame_proven"])

    def test_fails_on_unrecorded_vram_mutation_between_draw_pairs(self):
        name = self.window / "gpu-0002-vram.bin"
        data = bytearray(self.snapshots[2])
        data[:2] = (99).to_bytes(2, "little")
        name.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "continuity broken"):
            self.verify()

    def test_rejects_oversubscribed_or_counterfeit_completion(self):
        for change in (
            {"observed_hooks": 6},
            {"written_hooks": 6},
            {"limit_reached": True},
            {"write_failed": True},
            {"recorded_window_closed_without_detected_loss": False},
            {"windows_written": 2},
            {"observed_hooks": True},
            {"configured_windows": 1},
            {"walk_finished": False},
        ):
            old = dict(self.status)
            self.status.update(change)
            self.save_status()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.verify()
            self.status = old
        self.save_status()

    def test_no_mixed_legacy_receipt_or_unlisted_windows(self):
        (self.root / "gpu-native-capture-status.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "legacy"):
            self.verify()
        (self.root / "gpu-native-capture-status.json").unlink()
        extra = self.root / "window-001"
        extra.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "unlisted"):
            self.verify()

    def test_invalid_log_and_snapshot_link_rejected(self):
        log = self.window / "gpu-native-events.jsonl"
        original = log.read_bytes()
        log.write_bytes(original[:-1])
        with self.assertRaises(ValueError):
            self.verify()
        log.write_bytes(original)
        snapshot = self.window / "gpu-0003-vram.bin"
        snapshot.unlink()
        snapshot.symlink_to(self.window / "gpu-0001-vram.bin")
        with self.assertRaises(ValueError):
            self.verify()

    def test_root_and_windows_must_be_private_directories(self):
        self.window.chmod(0o755)
        with self.assertRaises(ValueError):
            self.verify()
        self.window.chmod(0o700)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
