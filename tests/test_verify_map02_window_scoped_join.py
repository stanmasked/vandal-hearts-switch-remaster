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
    NativeGpuWindowEvidenceTests, jsonline, private_bytes,
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

    def test_state_only_dr_mode_has_no_selected_pixel_edge_or_ordinal(self):
        # Synthetic source order: DR_MODE, F4, F4. The mode pair
        # counts in the strict native GPU receipt but must not become
        # a raster primitive ordinal in PutPixel/BlendG1/VRAM edges.
        from tools.verify_map02_native_gpu_capture import VRAM_BYTES
        events = []
        mode_before = dict(self.fixture.events[0], step=0, phase="before",
                           snapshot="gpu-0000-vram.bin", primitive_type=5,
                           draw_mode=[0, 0, 0])
        mode_after = dict(mode_before, step=1, phase="after",
                          snapshot="gpu-0001-vram.bin",
                          draw_mode=[1, 0, 0])
        events.extend((mode_before, mode_after))
        for idx, original in enumerate(self.fixture.events):
            event = dict(original, step=idx + 2,
                         snapshot=f"gpu-{idx + 2:04d}-vram.bin",
                         draw_mode=[1, 0, 0])
            events.append(event)
        for idx, payload in enumerate(
                (bytes(VRAM_BYTES), bytes(VRAM_BYTES),
                 *self.fixture.snapshots)):
            private_bytes(self.fixture.window / f"gpu-{idx:04d}-vram.bin", payload)
        self.fixture.events = events
        private_bytes(self.fixture.window / "gpu-native-events.jsonl", 
            b"".join(jsonline(e) for e in events))
        self.fixture.status.update(
            observed_hooks=6, before_hooks=3, after_hooks=3,
            draw_before_hooks=3, indexed_hooks=6, written_hooks=6)
        self.fixture.save_status()
        report = self.check()
        self.assertEqual(report["global_draw_ordinals_checked"], 2)
        self.assertEqual(report["global_event_indices_of_first_and_last_draw"],
                         [2, 4])
        self.assertEqual(report["unchanged_draws_at_selected_pixel"], 0)
        self.assertFalse(report["whole_original_gameplay_frame_proven"])

        # A DR_MODE transition is allowed to change draw_mode, but must
        # NEVER change even one VRAM byte; the independent native checker
        # must reject such a forgery before the scoped evidence joins.
        changed = bytearray(VRAM_BYTES)
        changed[4] = 1
        private_bytes(self.fixture.window / "gpu-0001-vram.bin", changed)
        with self.assertRaisesRegex(ValueError,
                                    "DR_MODE DrawOTag primitive modified VRAM"):
            self.check()

    def test_midstream_dr_mode_does_not_advance_raster_ordinals(self):
        # F4, DR_MODE, F4: state-only mode is between two raster draws.
        # Strict VRAM before/after continuity is unchanged and neither
        # PutPixel nor direct VRAM-edge ordinal may acquire a gap.
        from tools.verify_map02_native_gpu_capture import VRAM_BYTES
        first, first_after, last, last_after = self.fixture.events
        mode_pre = dict(last, step=2, primitive_type=5,
                        snapshot="gpu-0002-vram.bin", draw_mode=[0, 0, 0])
        mode_post = dict(last_after, step=3, primitive_type=5,
                         snapshot="gpu-0003-vram.bin", draw_mode=[1, 0, 0])
        last = dict(last, step=4, snapshot="gpu-0004-vram.bin",
                    draw_mode=[1, 0, 0])
        last_after = dict(last_after, step=5,
                          snapshot="gpu-0005-vram.bin",
                          draw_mode=[1, 0, 0])
        events = [first, first_after, mode_pre, mode_post, last, last_after]
        self.fixture.events = events
        same_at_mode_boundary = bytearray(VRAM_BYTES)
        same_at_mode_boundary[:2] = (1).to_bytes(2, "little")
        for idx, payload in enumerate((
                *self.fixture.snapshots[:2],
                bytes(same_at_mode_boundary), bytes(same_at_mode_boundary),
                *self.fixture.snapshots[2:],
        )):
            private_bytes(self.fixture.window / f"gpu-{idx:04d}-vram.bin", payload)
        private_bytes(self.fixture.window / "gpu-native-events.jsonl", 
            b"".join(jsonline(e) for e in events))
        self.fixture.status.update(observed_hooks=6, before_hooks=3,
                                   after_hooks=3, draw_before_hooks=3,
                                   indexed_hooks=6, written_hooks=6)
        self.fixture.save_status()
        result = self.check()
        self.assertEqual(result["global_draw_ordinals_checked"], 2)
        self.assertEqual(result["global_event_indices_of_first_and_last_draw"],
                         [0, 4])
        self.assertEqual(result["independently_sampled_draw_edges"], 2)
        self.assertFalse(result["whole_original_gameplay_frame_proven"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])

        # Forge an unreported GPU-state transition across a raster packet.
        # The native validator must fail instead of masking the evidence
        # as if DR_MODE were merely a skipped edge.
        events[4]["draw_mode"] = [0, 0, 0]
        private_bytes(self.fixture.window / "gpu-native-events.jsonl", 
            b"".join(jsonline(e) for e in events))
        with self.assertRaisesRegex(ValueError, "discontinuous GPU state"):
            self.check()

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
