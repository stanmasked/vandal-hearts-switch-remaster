"""Negative structural tests for the asset-free same-run GPU window witness."""
import hashlib
import io
import json
import os
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tools.verify_map02_native_gpu_windows as window_module

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

    def build_two_windows_across_recorder_capacity(self):
        """66 synthetic hooks: one full 64-record window and one 2-record window.

        A single BGR555 word changes once per pair. Endpoint n of a draw is
        identical to the starting word of draw n+1, including at the split.
        This allocates only locally generated, asset-free 1-MiB VRAM images.
        """
        second = self.root / "window-001"
        second.mkdir(mode=0o700)
        for window_index, count in ((0, 64), (1, 2)):
            directory = self.window if window_index == 0 else second
            events = []
            for step in range(count):
                ordinal = window_index * 32 + step // 2
                phase = "before" if step % 2 == 0 else "after"
                word = ordinal + (step % 2)
                snapshot = f"gpu-{step:04d}-vram.bin"
                data = bytearray(VRAM_BYTES)
                data[:2] = word.to_bytes(2, "little")
                (directory / snapshot).write_bytes(data)
                events.append({
                    "stage": "native_vram", "step": step, "frame": 7,
                    "phase": phase, "operation": "draw", "snapshot": snapshot,
                    "rect": None, "dest": [0, 0], "rgb": [200, 0, 0],
                    "primitive_type": 1, "semi": 0,
                    "window": [0, 0, 0, 0], "draw_mode": [0, 0, 0],
                    "upload": "", "ft4": None,
                })
            (directory / "gpu-native-events.jsonl").write_bytes(
                b"".join(jsonline(e) for e in events))
        self.status.update(
            windows_written=2, observed_hooks=66,
            before_hooks=33, after_hooks=33, draw_before_hooks=33,
            indexed_hooks=66, written_hooks=66)
        self.save_status()
        return second

    def test_two_windows_preserve_exact_64_event_cross_window_bridge(self):
        second = self.build_two_windows_across_recorder_capacity()
        report = self.verify()
        self.assertEqual(report["recorded_windows"], 2)
        self.assertEqual(report["globally_ordered_native_gpu_events"], 66)
        self.assertEqual(report["native_draw_pairs"], 33)
        self.assertEqual(report["native_transfer_pairs"], 0)
        self.assertEqual(report["vram_bridge_checks"], 32)
        final = bytearray(VRAM_BYTES)
        final[:2] = (33).to_bytes(2, "little")
        self.assertEqual(
            report["final_native_vram_sha256"], hashlib.sha256(final).hexdigest())
        self.assertFalse(report["whole_original_gameplay_frame_proven"])
        # Corrupt only the first pre-DRAW snapshot in window 001. The
        # individual pairs and counts remain valid, but the cross-window
        # endpoint is no longer equal to window 000's final VRAM.
        first = second / "gpu-0000-vram.bin"
        changed = bytearray(first.read_bytes())
        changed[:2] = (777).to_bytes(2, "little")
        first.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "continuity broken"):
            self.verify()

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

    def test_rejects_byte_identical_window_inode_swap_after_full_audit(self):
        target = self.window / "gpu-0000-vram.bin"
        previous = self.root / "old-vram-inode"
        original = window_module.verify_capture
        swapped = [False]

        def swap_after_check(*args, **kwargs):
            result = original(*args, **kwargs)
            if not swapped[0]:
                target.replace(previous)
                target.write_bytes(previous.read_bytes())
                swapped[0] = True
            return result

        with patch.object(window_module, "verify_capture",
                          side_effect=swap_after_check):
            with self.assertRaisesRegex(ValueError,
                                        "window evidence changed during audit"):
                self.verify()
        self.assertTrue(swapped[0])

    def test_rejects_byte_identical_index_swap_during_window_audit(self):
        target = self.root / INDEX
        previous = self.root / "old-window-index"
        original = window_module.verify_capture
        swapped = [False]

        def replace_index_after_check(*args, **kwargs):
            result = original(*args, **kwargs)
            if not swapped[0]:
                target.replace(previous)
                target.write_bytes(previous.read_bytes())
                swapped[0] = True
            return result

        with patch.object(window_module, "verify_capture",
                          side_effect=replace_index_after_check):
            with self.assertRaisesRegex(ValueError,
                                        "window index changed during audit"):
                self.verify()
        self.assertTrue(swapped[0])

    def test_rejects_unlisted_window_file_added_during_audit(self):
        extra = self.window / "unlisted-after-hash.bin"
        original = window_module.verify_capture

        def add_after_check(*args, **kwargs):
            result = original(*args, **kwargs)
            extra.write_bytes(b"synthetic-only")
            return result

        with patch.object(window_module, "verify_capture",
                          side_effect=add_after_check):
            with self.assertRaisesRegex(ValueError,
                                        "file set changed during audit"):
                self.verify()
        self.assertTrue(extra.is_file())

    def test_rejects_non_object_window_events_without_type_error(self):
        log = self.window / "gpu-native-events.jsonl"
        baseline = log.read_bytes().splitlines(keepends=True)
        for malformed in (None, [], 23, "not a native GPU event"):
            with self.subTest(event=malformed):
                log.write_bytes(jsonline(malformed) + b"".join(baseline[1:]))
                with self.assertRaisesRegex(ValueError, "not an object"):
                    self.verify()
        log.write_bytes(b"".join(baseline))
        self.assertEqual(self.verify()["globally_ordered_native_gpu_events"], 4)

    def test_rejects_unhashable_and_noncanonical_snapshot_names(self):
        log = self.window / "gpu-native-events.jsonl"
        baseline = log.read_bytes().splitlines(keepends=True)
        for malformed in ([], {"name": "gpu-0000-vram.bin"},
                          "../gpu-0000-vram.bin", "gpu-0001-vram.bin",
                          17, True):
            with self.subTest(snapshot=malformed):
                event = dict(self.events[0], snapshot=malformed)
                log.write_bytes(jsonline(event) + b"".join(baseline[1:]))
                with self.assertRaisesRegex(ValueError, "snapshot name"):
                    self.verify()
        log.write_bytes(b"".join(baseline))
        self.assertEqual(self.verify()["recorded_windows"], 1)

    def test_rejects_unhashable_and_noncanonical_upload_names(self):
        log = self.window / "gpu-native-events.jsonl"
        baseline = log.read_bytes().splitlines(keepends=True)
        for malformed in ([], {"upload": "gpu-0000-upload.bin"},
                          "../gpu-0000-upload.bin", "gpu-0001-upload.bin",
                          None, 12, True):
            with self.subTest(upload=malformed):
                event = dict(self.events[0], upload=malformed)
                log.write_bytes(jsonline(event) + b"".join(baseline[1:]))
                with self.assertRaisesRegex(ValueError, "upload name"):
                    self.verify()
        log.write_bytes(b"".join(baseline))
        self.assertEqual(self.verify()["recorded_windows"], 1)

    def test_cli_redacts_private_paths_in_window_errors(self):
        private_path = "/private/owned-game/MAP02/window-capture.bin"
        argv = ["native-window-audit", str(self.root), "--frame", "7"]
        for error in (OSError(13, "private window unavailable", private_path),
                      ValueError("bad capture event: " + private_path)):
            with self.subTest(kind=type(error).__name__):
                stderr = io.StringIO()
                with (patch("sys.argv", argv),
                      patch.object(window_module, "verify_native_windows",
                                   side_effect=error),
                      redirect_stderr(stderr)):
                    with self.assertRaises(SystemExit) as exit_result:
                        window_module.main()
                self.assertEqual(exit_result.exception.code, 2)
                self.assertIn("private native GPU window verification unavailable",
                              stderr.getvalue())
                self.assertNotIn(private_path, stderr.getvalue())
                self.assertNotIn("window-capture.bin", stderr.getvalue())

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
