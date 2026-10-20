"""Negative structural tests for the asset-free same-run GPU window witness."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.verify_map02_native_gpu_windows import (
    INDEX, SCHEMA, verify_native_windows,
)
from tools.verify_map02_vram_timeline import VRAM_BYTES


def jsonline(obj):
    return (json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n").encode()


def private_bytes(path, content):
    path.write_bytes(content)
    path.chmod(0o600)


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
            private_bytes(self.window / event["snapshot"], self.snapshots[step])
        private_bytes(self.window / "gpu-native-events.jsonl", 
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
        private_bytes(self.root / INDEX, jsonline(self.status))

    def verify(self):
        return verify_native_windows(self.root, target_frame=7)

    def test_small_one_window_is_not_mislabeled_as_complete_gameplay(self):
        result = self.verify()
        self.assertEqual(result["recorded_windows"], 1)
        self.assertEqual(result["globally_ordered_native_gpu_events"], 4)
        self.assertEqual(result["vram_bridge_checks"], 1)
        self.assertFalse(result["whole_original_gameplay_frame_proven"])

    def test_fails_on_unrecorded_vram_mutation_between_draw_pairs(self):
        name = self.window / "gpu-0002-vram.bin"
        data = bytearray(self.snapshots[2])
        data[:2] = (99).to_bytes(2, "little")
        private_bytes(name, data)
        with self.assertRaisesRegex(ValueError, "discontinuous VRAM|continuity broken"):
            self.verify()

    def test_gpu_mode_cannot_change_silently_across_window_boundary(self):
        # Use four-event synthetic windows, with 4+2=6 total events,
        # STRICTLY BELOW their 2*4=8 capacity. Production cap stays 64.
        # Reuse two validated F4 pairs already in window-000.
        next_window = self.root / "window-001"
        next_window.mkdir(mode=0o700)
        before = dict(self.events[0], step=0, primitive_type=5,
                      snapshot="gpu-0000-vram.bin", draw_mode=[0, 0, 0])
        after = dict(before, step=1, phase="after",
                     snapshot="gpu-0001-vram.bin", draw_mode=[1, 0, 0])
        for event in (before, after):
            private_bytes(next_window / event["snapshot"], self.snapshots[3])
        logfile = next_window / "gpu-native-events.jsonl"
        private_bytes(logfile, jsonline(before) + jsonline(after))
        self.status.update(window_capacity_events=4, windows_written=2,
                           observed_hooks=6, before_hooks=3, after_hooks=3,
                           draw_before_hooks=3, indexed_hooks=6,
                           written_hooks=6)
        self.save_status()
        with patch("tools.verify_map02_native_gpu_windows.MAX_RECORDS", 4):
            report = self.verify()
            self.assertEqual(report["recorded_windows"], 2)
            self.assertEqual(report["native_draw_pairs"], 3)
            self.assertFalse(report["whole_original_gameplay_frame_proven"])
            # Forging both local DR_MODE phases leaves local VRAM/state
            # consistent. Only the cross-window GPU bridge rejects it.
            before["draw_mode"] = [1, 0, 0]
            private_bytes(logfile, jsonline(before) + jsonline(after))
            with self.assertRaisesRegex(
                    ValueError, "GPU state continuity broken"):
                self.verify()

    def test_drawenv_clip_continuity_cannot_be_forged_at_window_boundary(self):
        # Old two-window checks bound draw mode/window and 1 MiB VRAM.
        # A changed clip/offset (or dropped optional DRAWENV) must not
        # inherit the same source-pinned DrawOTag boundary.
        clip = [0, 0, 1024, 512, 0, 0]
        for event in self.events:
            event["draw_env"] = clip[:]
        private_bytes(self.window / "gpu-native-events.jsonl", 
            b"".join(jsonline(e) for e in self.events))

        second = self.root / "window-001"
        second.mkdir(mode=0o700)
        before = dict(self.events[0], step=0, snapshot="gpu-0000-vram.bin")
        after = dict(before, step=1, phase="after",
                     snapshot="gpu-0001-vram.bin")
        for event in (before, after):
            private_bytes(second / event["snapshot"], self.snapshots[3])
        log = second / "gpu-native-events.jsonl"
        private_bytes(log, jsonline(before) + jsonline(after))
        self.status.update(window_capacity_events=4, windows_written=2,
                           observed_hooks=6, before_hooks=3, after_hooks=3,
                           draw_before_hooks=3, indexed_hooks=6,
                           written_hooks=6)
        self.save_status()

        with patch("tools.verify_map02_native_gpu_windows.MAX_RECORDS", 4):
            self.assertEqual(self.verify()["native_draw_pairs"], 3)
            before["draw_env"] = [1, 0, 1023, 512, 0, 0]
            after["draw_env"] = before["draw_env"][:]
            private_bytes(log, jsonline(before) + jsonline(after))
            with self.assertRaisesRegex(ValueError, "DRAWENV continuity broken"):
                self.verify()

            del before["draw_env"]
            del after["draw_env"]
            private_bytes(log, jsonline(before) + jsonline(after))
            with self.assertRaisesRegex(ValueError, "DRAWENV continuity broken"):
                self.verify()

    def test_preframe_transfer_cannot_reappear_after_draw_at_window_boundary(self):
        # All four original window-000 events are valid DrawOTag F4 draws.
        # Window-001 contains a self-consistent, VRAM-neutral ClearImage
        # transfer in the PREVIOUS frame. Per-window checks accept this
        # separately; global frame chronology must reject their order.
        second = self.root / "window-001"
        second.mkdir(mode=0o700)
        before = dict(self.events[0], step=0, frame=6,
                      operation="clear", primitive_type=0, semi=0,
                      rect=[0, 0, 0, 0], snapshot="gpu-0000-vram.bin")
        after = dict(before, step=1, phase="after",
                     snapshot="gpu-0001-vram.bin")
        for event in (before, after):
            private_bytes(second / event["snapshot"], self.snapshots[3])
        private_bytes(second / "gpu-native-events.jsonl", 
            jsonline(before) + jsonline(after))
        self.status.update(window_capacity_events=4, windows_written=2,
                           observed_hooks=6, before_hooks=3, after_hooks=3,
                           draw_before_hooks=2, transfer_before_hooks=1,
                           indexed_hooks=6, written_hooks=6)
        self.save_status()
        with patch("tools.verify_map02_native_gpu_windows.MAX_RECORDS", 4):
            with self.assertRaisesRegex(
                    ValueError,
                    "transfer appears after DrawOTag across window boundary"):
                self.verify()

    def test_preframe_transfers_then_target_draw_may_cross_window_boundary(self):
        # The chronological transition from frame-6 ClearImage operations
        # to a frame-7 F4 DrawOTag is valid even at the rollover. This
        # guards against a validator that indiscriminately rejects all
        # transfer-to-draw window boundaries.
        self.events = [
            dict(event, frame=6, operation="clear", primitive_type=0,
                 rect=[0, 0, 0, 0], semi=0)
            for event in self.events
        ]
        empty = bytes(VRAM_BYTES)
        for step, event in enumerate(self.events):
            private_bytes(self.window / event["snapshot"], empty)
        private_bytes(self.window / "gpu-native-events.jsonl", 
            b"".join(jsonline(event) for event in self.events))
        next_window = self.root / "window-001"
        next_window.mkdir(mode=0o700)
        before = dict(self.events[0], step=0, frame=7,
                      operation="draw", primitive_type=1,
                      rect=None, snapshot="gpu-0000-vram.bin")
        after = dict(before, step=1, phase="after",
                     snapshot="gpu-0001-vram.bin")
        changed = bytearray(VRAM_BYTES)
        changed[0] = 1
        private_bytes(next_window / before["snapshot"], empty)
        private_bytes(next_window / after["snapshot"], changed)
        private_bytes(next_window / "gpu-native-events.jsonl", 
            jsonline(before) + jsonline(after))
        self.status.update(window_capacity_events=4, windows_written=2,
                           observed_hooks=6, before_hooks=3, after_hooks=3,
                           draw_before_hooks=1, transfer_before_hooks=2,
                           indexed_hooks=6, written_hooks=6)
        self.save_status()
        with patch("tools.verify_map02_native_gpu_windows.MAX_RECORDS", 4):
            result = self.verify()
            self.assertEqual(result["globally_ordered_native_gpu_events"], 6)
            self.assertEqual(result["native_draw_pairs"], 1)
            self.assertEqual(result["native_transfer_pairs"], 2)
            self.assertEqual(result["recorded_windows"], 2)
            self.assertEqual(result["vram_bridge_checks"], 2)
            self.assertIsNone(result["capture_session_sha256"])
            self.assertFalse(result["whole_original_gameplay_frame_proven"])
            self.assertFalse(result["physical_ps1_equivalence_proven"])

    def test_transfer_only_window_cannot_certify_target_draw_frame(self):
        # A consistent frame-6 transfer journal with no DrawOTag frame-7
        # event must not pass as a successful target-frame observation.
        self.events = [
            dict(event, frame=6, operation="clear", primitive_type=0,
                 rect=[0, 0, 0, 0], semi=0)
            for event in self.events
        ]
        empty = bytes(VRAM_BYTES)
        for event in self.events:
            private_bytes(self.window / event["snapshot"], empty)
        private_bytes(self.window / "gpu-native-events.jsonl", 
            b"".join(jsonline(event) for event in self.events))
        self.status.update(draw_before_hooks=0, transfer_before_hooks=2)
        self.save_status()
        with self.assertRaisesRegex(ValueError, "no target DrawOTag"):
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
        private_bytes(log, original[:-1])
        with self.assertRaises(ValueError):
            self.verify()
        private_bytes(log, original)
        snapshot = self.window / "gpu-0003-vram.bin"
        snapshot.unlink()
        snapshot.symlink_to(self.window / "gpu-0001-vram.bin")
        with self.assertRaises(ValueError):
            self.verify()

    def test_capture_files_require_0600_and_single_link(self):
        snapshot = self.window / "gpu-0000-vram.bin"
        snapshot.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-only 0600"):
            self.verify()
        snapshot.chmod(0o600)
        self.assertEqual(self.verify()["native_draw_pairs"], 2)

        index = self.root / INDEX
        index.chmod(0o640)
        with self.assertRaisesRegex(ValueError, "owner-only 0600"):
            self.verify()
        index.chmod(0o600)

        alias = Path(self.tmp.name) / "duplicate-snapshot.bin"
        os.link(snapshot, alias)
        with self.assertRaisesRegex(ValueError, "one link"):
            self.verify()
        alias.unlink()
        self.assertEqual(self.verify()["native_draw_pairs"], 2)

    def test_unhashable_event_filename_fails_closed(self):
        event = dict(self.events[0])
        event["snapshot"] = ["unexpected", "list"]
        private_bytes(self.window / "gpu-native-events.jsonl",
                      jsonline(event) +
                      b"".join(jsonline(item) for item in self.events[1:]))
        with self.assertRaisesRegex(ValueError, "nonstring file metadata"):
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
