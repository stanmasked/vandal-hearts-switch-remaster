"""Asset-free multi-coordinate private native PC PutPixel audit regressions.

These independent captures MUST NOT claim a simultaneous replay of a MAP02
raster frame. End-to-end positives recheck the complete synthetic native
GPU/source FT4/OT/PutPixel chain, not mocked color arithmetic.
"""
import json
import unittest
from unittest.mock import patch

import test_verify_map02_putpixel_scope as scope_fixture
from tools.audit_map02_putpixel_samples import audit_samples


class IndependentPixelSamplesTests(unittest.TestCase):
    def setUp(self):
        self.first = scope_fixture.PixelToOriginalPrimitiveTests(
            methodName="test_binds_same_coordinate_to_two_distinct_source_draws")
        self.first.setUp()
        self.addCleanup(self.first.doCleanups)
        self.second = scope_fixture.PixelToOriginalPrimitiveTests(
            methodName="test_binds_same_coordinate_to_two_distinct_source_draws")
        self.second.setUp()
        self.addCleanup(self.second.doCleanups)
        # Both legitimate scoped PC probes capture the same *claimed*
        # frames but select different one-word private VRAM coordinates.
        # Position (31,31) is unchanged by either synthetic source FT4.
        self.second.coord = (31, 31)
        self.second.pixel_rows = [
            self.second.row(0, 1, 0, 0, 0),
            self.second.row(1, 2, 0, 0, 0),
        ]
        self.second.save()

    def pairs(self):
        return [
            (self.first.root, self.first.native),
            (self.second.root, self.second.native),
        ]

    def test_two_distinct_private_words_aggregate_without_origin_claims(self):
        report = audit_samples(self.pairs())
        self.assertEqual(report["independent_capture_pairs_verified"], 2)
        self.assertEqual(report["distinct_private_vram_words_sampled"], 2)
        self.assertEqual(report["source_frame"], 411)
        self.assertEqual(report["native_gpu_frame"], 12)
        self.assertEqual(report["observed_native_putpixel_calls"], 4)
        self.assertEqual(report["source_keyed_ft4_draws_checked"], 4)
        self.assertEqual(report["source_ft4_draws_with_scoped_calls"], 4)
        self.assertEqual(report["source_ft4_draws_without_observable_word_change"], 2)
        self.assertEqual(report["calls_attributed_to_source_keyed_ft4"], 4)
        self.assertEqual(report["source_ft4_scoped_changed_putpixel_calls"], 2)
        self.assertEqual(report["source_ft4_scoped_unchanged_putpixel_calls"], 2)
        self.assertEqual(report["source_ft4_sampled_changed_word_draws"], 2)
        self.assertEqual(report["source_ft4_scoped_semitransparent_blend_calls"], 0)
        for key in (
            "same_native_capture_session_authenticated",
            "simultaneous_multi_word_observation_proven",
            "complete_putpixel_write_stream_proven",
            "ft4_actual_pixel_coverage_verified",
            "original_map02_gameplay_authenticated",
            "ps1_hardware_pixel_equivalence_verified",
            "raw_pixel_coordinates_or_colors_emitted",
        ):
            self.assertFalse(report[key])
        public = json.dumps(report, sort_keys=True)
        for secret in ('"x"', '"y"', '"before"', '"front"', '"after"',
                       '"snapshot"', '"tpage"', '"clut"', '0x801f'):
            self.assertNotIn(secret, public)

    def test_second_capture_same_word_rejected_without_double_counting(self):
        self.second.coord = self.first.coord
        self.second.pixel_rows = self.second.make_rows()
        self.second.save()
        with self.assertRaisesRegex(ValueError, "duplicate sampled VRAM word"):
            audit_samples(self.pairs())

    def test_missing_or_tampered_private_source_is_not_silently_skipped(self):
        path = self.second.native / "putpixel-native-events.jsonl"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            audit_samples(self.pairs())

    def test_multi_capture_frame_labels_must_agree(self):
        # Isolate the *aggregate* frame-binding gate from the deeper
        # one-capture validator (which already checks its own metadata).
        from tools.verify_map02_putpixel_scope import verify_pixel_ot
        a, b = [verify_pixel_ot(*pair) for pair in self.pairs()]
        b["source_frame"] += 1
        with patch("tools.audit_map02_putpixel_samples.verify_pixel_ot",
                   side_effect=[a, b]):
            with self.assertRaisesRegex(ValueError, "different frame labels"):
                audit_samples(self.pairs())

    def test_capture_count_and_duplicate_directory_limits(self):
        with self.assertRaisesRegex(ValueError, "expected 2 to 8"):
            audit_samples(self.pairs()[:1])
        with self.assertRaisesRegex(ValueError, "expected 2 to 8"):
            audit_samples(self.pairs() * 5)
        with self.assertRaisesRegex(ValueError, "duplicate sampled VRAM word"):
            audit_samples([self.pairs()[0]] * 2)


if __name__ == "__main__":
    unittest.main()
