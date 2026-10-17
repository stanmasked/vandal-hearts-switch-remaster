"""Synthetic private native window ↔ selected-pixel full VRAM join.

All GPU snapshots are real byte buffers from the separately tested window
fixture; this test NEVER asserts original MAP02/PS1 gameplay authenticity.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_verify_map02_native_gpu_windows import (
    NativeGpuWindowEvidenceTests, jsonline,
)
from tools.verify_map02_window_scoped_join import verify_window_scoped_join


class WindowScopedJoinTests(unittest.TestCase):
    def setUp(self):
        fixture = NativeGpuWindowEvidenceTests(
            methodName="test_small_one_window_is_not_mislabeled_as_complete_gameplay")
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        self.fixture = fixture
        self.native = fixture.root
        self.scoped = self.native.parent / "scoped"
        self.scoped.mkdir(mode=0o700)
        self.pixel = []
        self.blend = []
        self.edges = []
        for i, (before, after) in enumerate(((0, 1), (1, 2))):
            event = {
                "stage": "native_putpixel", "step": i, "frame": 7,
                "primitive_ordinal": i, "primitive_type": 1, "x": 0, "y": 0,
                "before": before, "front": after, "after": after, "abr": 1,
                "semi": 1, "textured": 0, "accurate": 1,
            }
            self.pixel.append(event)
            self.blend.append({
                "stage": "native_blendg1", "putpixel_step": i,
                "frame": 7, "primitive_ordinal": i, "primitive_type": 1,
                "x": 0, "y": 0, "accurate": 1, "abr": 1,
                "before": before, "front": after, "after": after,
                "blend_fg": after | 0x8000, "blend_bg": before,
                "blend_result": after,
            })
            self.edges.append({
                "stage": "native_vram_edge", "frame": 7,
                "primitive_ordinal": i, "primitive_type": 1,
                "x": 0, "y": 0, "before": before, "after": after,
            })
        self.save()

    def save(self):
        for name, content in (
            ("putpixel-native-events.pending.jsonl", self.pixel),
            ("blendg1-native-events.pending.jsonl", self.blend),
            ("vram-edges-native-events.pending.jsonl", self.edges),
        ):
            (self.scoped / name).write_bytes(b"".join(jsonline(e) for e in content))

    def check(self, **kwargs):
        return verify_window_scoped_join(
            self.native, self.scoped, target_frame=7, **kwargs)

    def test_observed_selected_pixel_and_global_draw_ordinals_match(self):
        result = self.check()
        self.assertEqual(result["global_draw_ordinals_checked"], 2)
        self.assertEqual(result["global_event_indices_of_first_and_last_draw"],
                         [0, 2])
        self.assertEqual(result["selected_pixel_putpixel_events"], 2)
        self.assertEqual(result["selected_pixel_blendg1_events"], 2)
        self.assertFalse(result["source_gte_subsequence_verified"])
        self.assertFalse(result["whole_original_gameplay_frame_proven"])

    def test_rejects_identically_tampered_pixel_blend_and_edge_vs_native_vram(self):
        # Coordinated mutation still passes all three *mutual* comparators,
        # but must NOT bypass directly captured full-VRAM native snapshots.
        self.pixel[0]["before"] = 7
        self.blend[0]["before"] = 7
        self.blend[0]["blend_bg"] = 7
        self.edges[0]["before"] = 7
        self.save()
        with self.assertRaisesRegex(ValueError, "full VRAM snapshot"):
            self.check()

    def test_rejects_unlisted_or_misframed_scoped_file(self):
        unexpected = self.scoped / "another-session.jsonl"
        unexpected.write_text("x")
        with self.assertRaisesRegex(ValueError, "mixed-session"):
            self.check()
        unexpected.unlink()
        self.edges[0]["frame"] = 8
        self.save()
        with self.assertRaises(ValueError):
            self.check()

    def test_source_claim_is_optional_but_requires_verified_sha_witness(self):
        with patch(
            "tools.verify_map02_window_scoped_join.verify_published_window_source_witness",
            return_value={
                "native_window_file_tree_bound": True,
                "window_source_witness_manifest_sha256": "a" * 64,
            },
        ) as verified:
            result = self.check(source_dir=Path("/private/source"))
            verified.assert_called_once()
            self.assertTrue(result["source_gte_subsequence_verified"])
        with patch(
            "tools.verify_map02_window_scoped_join.verify_published_window_source_witness",
            side_effect=ValueError("source GTE claim absent"),
        ):
            with self.assertRaisesRegex(ValueError, "GTE"):
                self.check(source_dir=Path("/private/source"))


if __name__ == "__main__":
    unittest.main()
