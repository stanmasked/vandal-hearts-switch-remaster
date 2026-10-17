"""Synthetic native-GPU capture terminal receipt consistency regressions.

Receipt is a self-reported counter, NOT a retail game authenticity proof.
"""
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_map02_native_gpu_capture import (
    STATUS, verify_capture_receipt,
)


class NativeGpuReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.events = [
            {"operation": "draw", "phase": "before"},
            {"operation": "draw", "phase": "after"},
            {"operation": "draw", "phase": "before"},
            {"operation": "draw", "phase": "after"},
        ]
        self.status = dict(
            schema="vh.map02.native-capture-status.v1",
            gpu_draw_frame=7, observed_hooks=4, before_hooks=2,
            after_hooks=2, draw_before_hooks=2, transfer_before_hooks=0,
            indexed_hooks=4, written_hooks=4, limit_reached=False,
            walk_finished=True, hooks_balanced=True,
            observed_window_closed_without_detected_loss=True,
        )
        self.save()

    def save(self):
        (self.directory / STATUS).write_text(
            json.dumps(self.status) + "\n", encoding="utf-8")

    def check(self):
        return verify_capture_receipt(
            self.directory, target_frame=7, events=self.events)

    def test_balanced_small_capture_accepted_as_structural_only(self):
        report = self.check()
        self.assertEqual(report["native_gpu_draw_pairs_accounted"], 2)
        self.assertFalse(report["full_original_gameplay_frame_proven"])

    def test_rejects_absent_receipt_and_frame_mismatch(self):
        (self.directory / STATUS).unlink()
        with self.assertRaises(ValueError):
            self.check()
        self.status["gpu_draw_frame"] = 8
        self.save()
        with self.assertRaisesRegex(ValueError, "frame mismatch"):
            self.check()

    def test_rejects_cap_even_when_exactly_full(self):
        self.events = (
            [{"operation": "draw", "phase": "before"},
             {"operation": "draw", "phase": "after"}] * 32
        )
        self.status.update(
            observed_hooks=64, before_hooks=32, after_hooks=32,
            draw_before_hooks=32, indexed_hooks=64, written_hooks=64,
            limit_reached=True, hooks_balanced=True,
            observed_window_closed_without_detected_loss=False)
        self.save()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.check()

    def test_rejects_truncated_overflow_and_missing_write(self):
        for update in (
            dict(observed_hooks=6, before_hooks=3, after_hooks=3,
                 draw_before_hooks=3, limit_reached=True),
            dict(indexed_hooks=4, written_hooks=3),
            dict(before_hooks=1),
            dict(walk_finished=False,
                 observed_window_closed_without_detected_loss=False),
            dict(hooks_balanced=False),
            dict(observed_window_closed_without_detected_loss=False),
            dict(observed_hooks=True),
            dict(limit_reached=1),
        ):
            status = dict(self.status, **update)
            self.status = status
            self.save()
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.check()
            self.status = dict(
                schema="vh.map02.native-capture-status.v1",
                gpu_draw_frame=7, observed_hooks=4, before_hooks=2,
                after_hooks=2, draw_before_hooks=2, transfer_before_hooks=0,
                indexed_hooks=4, written_hooks=4, limit_reached=False,
                walk_finished=True, hooks_balanced=True,
                observed_window_closed_without_detected_loss=True)

    def test_requires_transfer_count_separate_from_draws(self):
        self.events[0]["operation"] = self.events[1]["operation"] = "load"
        self.status.update(draw_before_hooks=1, transfer_before_hooks=1)
        self.save()
        self.assertEqual(self.check()["native_gpu_draw_pairs_accounted"], 1)
        self.status.update(draw_before_hooks=2, transfer_before_hooks=0)
        self.save()
        with self.assertRaisesRegex(ValueError, "count/log divergence"):
            self.check()

    def test_refuses_duplicate_json_fields_and_symlink(self):
        path = self.directory / STATUS
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'"gpu_draw_frame": 7',
                                     b'"gpu_draw_frame": 7, "gpu_draw_frame": 7'))
        with self.assertRaises(ValueError):
            self.check()
        path.unlink()
        target = self.directory / "target"
        target.write_bytes(b"anything")
        path.symlink_to(target)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
