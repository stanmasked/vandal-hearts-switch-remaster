"""Synthetic dual-local private source/native FT4 checks; never retail data."""
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from test_verify_map02_timeline_native_ft4_join import (
    TimelineToNativeFt4JoinTests,
)
from tools.verify_map02_private_pc_native_ft4 import (
    SCHEMA, verify_unified,
)

PUBLIC_RASTER = os.environ.get("MAP02_PINNED_RASTER")


class Map02UnifiedPcNativeFt4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLIC_RASTER:
            raise RuntimeError("MAP02_PINNED_RASTER must name pinned PUBLIC raster source")

    def setUp(self):
        self.base = TimelineToNativeFt4JoinTests(
            methodName="test_different_clocks_reversed_ot_order_and_per_face_clut",
        )
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.source = self.base.base.root
        self.native = self.base.native
        self.assertNotEqual(self.base.base.frame, self.base.native_frame)

    def check(self):
        return verify_unified(
            self.source, self.native, Path(PUBLIC_RASTER),
            compiler=os.environ.get("CC", "gcc"),
        )

    def test_two_different_clocks_and_reversed_order_pass(self):
        result = self.check()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["source_submissions_checked"], 2)
        self.assertEqual(result["source_native_ft4_unique_matches"], 2)
        self.assertEqual(result["per_ft4_vram_snapshots_compared"], 2)
        self.assertEqual(result["compiled_pc_sampletexture_texels_checked"], 131072)
        self.assertTrue(result["source_gpu_frame_mapping_explicit_and_hash_bound"])
        self.assertTrue(
            result["full_source_native_inputs_rechecked_after_both_validators"]
        )
        for key in ("native_draw_order_assumed_same_as_source",
                    "retail_gameplay_authenticated",
                    "ps1_hardware_raster_parity_proven",
                    "private_game_bytes_emitted"):
            self.assertFalse(result[key])
        public = json.dumps(result, sort_keys=True)
        for secret in ("gpu-vram-000.bin", "gpu-native-events.jsonl",
                       "perimeter_xy", "bgr555", "camera",
                       str(self.source), str(self.native)):
            self.assertNotIn(secret, public)

    def test_exact_native_ft4_window_or_palette_required(self):
        self.base.packets[0]["window"][0] ^= 1
        self.base.save()
        with self.assertRaisesRegex(ValueError, "no exact GPU FT4"):
            self.check()

    def test_native_gpu_snapshot_replacement_after_join_rejected(self):
        original = verify_unified.__globals__["verify_timeline_join"]

        def mutate_after_join(src, native, *, compiler):
            report = original(src, native, compiler=compiler)
            path = native / "gpu-0000-vram.bin"
            altered = bytearray(path.read_bytes())
            altered[-1] ^= 1  # deliberately unrelated to the FT4 texture crop
            path.write_bytes(altered)
            return report

        with patch(
            "tools.verify_map02_private_pc_native_ft4.verify_timeline_join",
            side_effect=mutate_after_join,
        ):
            with self.assertRaisesRegex(ValueError, "input changed"):
                self.check()

    def test_source_timeline_change_after_pc_pass_rejected(self):
        original = verify_unified.__globals__["verify_private_timeline"]

        def mutate_after_source_pass(src, raster, *, compiler):
            result = original(src, raster, compiler=compiler)
            path = src / "gpu-vram-000.bin"
            raw = bytearray(path.read_bytes())
            raw[-1] ^= 1
            path.write_bytes(raw)
            return result

        with patch(
            "tools.verify_map02_private_pc_native_ft4.verify_private_timeline",
            side_effect=mutate_after_source_pass,
        ):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.check()

    def test_wrong_cross_clock_binding_rejected(self):
        path = self.source / "gpu-face-timeline-join.json"
        claim = json.loads(path.read_text())
        claim["gpu_draw_frame"] += 1
        path.write_text(json.dumps(claim))
        with self.assertRaisesRegex(ValueError, "different native GPU frame"):
            self.check()

    def test_linked_native_snapshot_rejected_before_comparison(self):
        first = self.native / "gpu-0000-vram.bin"
        data = first.read_bytes()
        first.unlink()
        alt = self.native / "other.bin"
        alt.write_bytes(data)
        first.symlink_to(alt)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            self.check()

    def test_non_private_native_folder_refused(self):
        old = stat.S_IMODE(self.native.stat().st_mode)
        self.native.chmod(0o755)
        try:
            with self.assertRaisesRegex(ValueError, "private"):
                self.check()
        finally:
            self.native.chmod(old)


if __name__ == "__main__":
    unittest.main()
