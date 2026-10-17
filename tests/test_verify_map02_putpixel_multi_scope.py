"""Asset-free, two-coordinate native DrawOTag/PutPixel provenance regressions."""
import hashlib
import json
import struct
import unittest

import test_verify_map02_putpixel_scope as original_fixture
from tools.verify_map02_putpixel_multi_scope import verify_multi_pixel_ot


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class TwoWordPutPixelTests(unittest.TestCase):
    def setUp(self):
        self.base = original_fixture.PixelToOriginalPrimitiveTests(
            methodName="test_binds_same_coordinate_to_two_distinct_source_draws")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.source, self.native = self.base.root, self.base.native
        # Both native locations are already affected by first FT4 in the
        # independently constructed source-keyed overdraw fixture.
        self.coord_a = (30, 30)
        self.coord_b = (35, 35)
        self.rows = [
            self.base.row(0, 1, 0, 0x801f, 0x801f),
            self.base.row(1, 1, 0, 0x03e0, 0x03e0),
            self.base.row(2, 2, 0x801f, 0x7c00, 0x7c00),
        ]
        self.rows[1]["x"], self.rows[1]["y"] = self.coord_b
        self.save()

    def save(self):
        self.base.pixel_rows = self.rows
        self.base.save()
        raw = (self.native/"putpixel-native-events.jsonl").read_bytes()
        meta = {
            "schema": "vh.map02.native-putpixel-multi-ot.v1",
            "source_frame": 411,
            "gpu_draw_frame": 12,
            "overdraw_manifest_sha256": sha(
                (self.source/"gpu-native-overdraw.json").read_bytes()),
            "native_events_sha256": sha(
                (self.native/"gpu-native-events.jsonl").read_bytes()),
            "putpixel_events_sha256": sha(raw),
        }
        (self.source/"gpu-putpixel-multi-ot.json").write_text(
            json.dumps(meta, sort_keys=True))

    def test_interleaved_two_coordinates_bound_to_same_drawotag(self):
        report = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(report["distinct_private_vram_words_verified"], 2)
        self.assertEqual(report["source_keyed_ft4_draws_checked"], 2)
        self.assertEqual(report["native_drawotag_primitives_checked"], 3)
        self.assertEqual(report["all_native_putpixel_calls_observed"], 3)
        self.assertEqual(report["source_keyed_ft4_putpixel_calls"], 3)
        self.assertEqual(report["source_ft4_changed_putpixel_calls"], 3)
        self.assertEqual(report["source_ft4_changed_word_draw_coordinate_pairs"], 3)
        self.assertEqual(report["source_ft4_draw_coordinate_pairs_with_calls"], 3)
        self.assertEqual(report["source_ft4_draws_with_both_words_observed"], 1)
        self.assertEqual(report["source_ft4_draws_changing_both_sampled_words"], 1)
        self.assertEqual(report["source_ft4_draws_with_both_words_changed_by_putpixel"], 1)
        self.assertEqual(report["source_ft4_draws_with_both_words_changed_but_one_net_delta"], 0)
        self.assertEqual(report["source_ft4_draws_with_both_words_semitransparent"], 0)
        self.assertEqual(report["source_ft4_draws_with_interleaved_word_revisit"], 0)
        self.assertTrue(report["one_interleaved_global_putpixel_step_sequence"])
        self.assertTrue(report["two_coordinates_checked_against_same_native_drawotag_snapshots"])
        for field in (
            "native_capture_process_identity_authenticated",
            "complete_original_putpixel_stream_proven",
            "physical_ps1_pixel_equivalence_verified",
            "real_map02_gameplay_authenticated",
            "raw_pixel_coordinates_or_colors_emitted",
        ):
            self.assertFalse(report[field])
        public = json.dumps(report)
        for leaked in ('"x"', '"y"', '"before"', '"after"', '"front"',
                       "0x801f", '"clut"', '"tpage"'):
            self.assertNotIn(leaked, public)

    def test_two_blends_and_same_value_write_in_one_primitive(self):
        # Actual PC ABR1 on a textured pixel: 0+0x1f -> 0x801f;
        # 0x801f+0 -> unchanged 0x801f, both calls still observable.
        self.rows = [
            self.base.row(0, 1, 0, 0x001f, 0x801f, semi=1),
            self.base.row(1, 1, 0x801f, 0, 0x801f, semi=1),
            self.base.row(2, 1, 0, 0x03e0, 0x03e0),
            self.base.row(3, 2, 0x801f, 0x7c00, 0x7c00),
        ]
        self.rows[2]["x"], self.rows[2]["y"] = self.coord_b
        self.save()
        report = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(report["source_keyed_ft4_putpixel_calls"], 4)
        self.assertEqual(report["source_keyed_ft4_semitransparent_calls"], 2)
        self.assertEqual(report["source_ft4_abr1_calls"], 2)
        self.assertEqual(report["source_ft4_same_value_putpixel_calls"], 1)
        self.assertEqual(report["source_ft4_coordinate_pairs_with_multiple_blends"], 1)
        self.assertEqual(report["source_ft4_draws_with_both_words_observed"], 1)
        self.assertEqual(report["source_ft4_draws_with_interleaved_word_revisit"], 0)
        # At 0x801f, red is already saturated (31/31). Adding
        # another red unit would be a *valid* no-op under ABR1 and
        # cannot prove tampering. Changing green must alter the blend.
        self.rows[1]["front"] = 0x03e0
        self.save()
        with self.assertRaisesRegex(ValueError, "source-pinned PC WritePixel"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_interleaved_a_b_a_and_a_b_b_a_revisit_in_same_ft4(self):
        # One sourced FT4 writes A, then B, then legitimately revisits
        # A with an opaque no-op; the final PRE/POST snapshots still
        # only reveal one net change at each sampled coordinate.
        self.rows = [
            self.base.row(0, 1, 0, 0x801f, 0x801f),
            self.base.row(1, 1, 0, 0x03e0, 0x03e0),
            self.base.row(2, 1, 0x801f, 0x801f, 0x801f),
            self.base.row(3, 2, 0x801f, 0x7c00, 0x7c00),
        ]
        self.rows[1]["x"], self.rows[1]["y"] = self.coord_b
        self.save()
        report = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(report["source_ft4_draws_with_interleaved_word_revisit"],1)
        self.assertEqual(report["source_ft4_draws_with_both_words_observed"],1)
        self.assertEqual(report["source_ft4_changed_putpixel_calls"],3)
        self.assertEqual(report["source_ft4_same_value_putpixel_calls"],1)
        self.assertEqual(report["source_ft4_draws_changing_both_sampled_words"],1)

        # Add another no-op B in between. A,B,B,A must still count as a
        # return, but the event log's global step sequence remains exact.
        self.rows.insert(2,self.base.row(2,1,0x03e0,0x03e0,0x03e0))
        self.rows[2]["x"], self.rows[2]["y"] = self.coord_b
        for i, entry in enumerate(self.rows):
            entry["step"] = i
        self.save()
        report = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(report["source_ft4_draws_with_interleaved_word_revisit"],1)
        self.assertEqual(report["source_ft4_same_value_putpixel_calls"],2)

    def test_same_ft4_semitransparent_blends_at_both_sampled_words(self):
        # Accurate BlendG1 ABR1: textured A retains bit15, while
        # untextured B clears it. Both retain their original PC after
        # words from the real native per-FT4 snapshot.
        self.rows = [
            self.base.row(0,1,0,0x001f,0x801f,semi=1),
            self.base.row(1,1,0,0x03e0,0x03e0,semi=1),
            self.base.row(2,2,0x801f,0x7c00,0x7c00),
        ]
        self.rows[1]["x"], self.rows[1]["y"] = self.coord_b
        self.rows[1]["textured"] = 0
        self.save()
        report = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(report["source_keyed_ft4_semitransparent_calls"],2)
        self.assertEqual(report["source_ft4_abr1_calls"],2)
        self.assertEqual(report["source_ft4_draws_with_both_words_observed"],1)
        self.assertEqual(report["source_ft4_draws_with_both_words_semitransparent"],1)
        self.assertEqual(report["source_ft4_draws_changing_both_sampled_words"],1)
        self.rows[1]["textured"] = 1
        self.save()
        with self.assertRaisesRegex(ValueError,"source-pinned PC WritePixel"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_one_ft4_writes_both_words_but_restores_one_before_snapshot(self):
        # Same source-keyed FT4 makes real writes at A and B, then
        # returns A to its PRE value. Per-draw GPU snapshots only see
        # B change, so an ordinary delta comparison misses the A work.
        original = bytes(self.base.base.base.bytes_before)
        first = bytearray(original)
        struct.pack_into("<H", first, (35*1024+35)*2, 0x03e0)
        second = bytearray(first)
        struct.pack_into("<H", second, (30*1024+30)*2, 0x7c00)
        self.base.base.base.override_snapshots = {
            3: bytes(first), 4: bytes(first), 5: bytes(second),
        }
        self.rows = [
            self.base.row(0, 1, 0, 0x8000, 0x8000),
            self.base.row(1, 1, 0, 0x03e0, 0x03e0),
            self.base.row(2, 1, 0x8000, 0, 0),
            self.base.row(3, 2, 0, 0x7c00, 0x7c00),
        ]
        self.rows[1]["x"], self.rows[1]["y"] = self.coord_b
        self.save()
        report = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(report["source_ft4_draws_with_both_words_observed"], 1)
        self.assertEqual(report["source_ft4_draws_with_both_words_changed_by_putpixel"], 1)
        self.assertEqual(report["source_ft4_draws_with_both_words_changed_but_one_net_delta"], 1)
        self.assertEqual(report["source_ft4_draws_changing_both_sampled_words"], 0)
        self.assertEqual(report["source_ft4_transient_write_restore_pairs"], 1)
        self.assertEqual(report["source_ft4_draws_with_interleaved_word_revisit"], 1)
        self.assertEqual(report["source_ft4_changed_putpixel_calls"], 4)
        self.assertEqual(report["source_ft4_changed_word_draw_coordinate_pairs"], 2)
        self.assertFalse(report["complete_original_putpixel_stream_proven"])

        # A missing restoration changes the claimed final word while
        # preserving the original VRAM snapshot; reject it.
        self.rows[2]["after"] = 0x8000
        self.rows[2]["front"] = 0x8000
        self.save()
        with self.assertRaisesRegex(ValueError, "contradicts native primitive VRAM bounds"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_duplicate_step_and_backward_ordinal_rejected(self):
        self.rows[1]["step"] = 0
        self.save()
        with self.assertRaisesRegex(ValueError, "discontinuous global steps"):
            verify_multi_pixel_ot(self.source, self.native)
        self.rows[1]["step"] = 1
        self.rows[0]["primitive_ordinal"] = 2
        self.save()
        with self.assertRaisesRegex(ValueError, "ordinal goes backward"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_claiming_third_word_or_missing_second_rejected(self):
        self.rows[1]["x"] = 31
        self.rows[1]["y"] = 31
        self.rows.insert(2, self.base.row(2, 1, 0, 0, 0))
        self.rows[2]["x"], self.rows[2]["y"] = self.coord_b
        self.rows[3]["step"] = 3
        self.save()
        with self.assertRaisesRegex(ValueError, "more than two"):
            verify_multi_pixel_ot(self.source, self.native)
        self.rows = [
            self.base.row(0, 1, 0, 0x801f, 0x801f),
            self.base.row(1, 2, 0x801f, 0x7c00, 0x7c00),
        ]
        self.save()
        with self.assertRaisesRegex(ValueError, "exactly two distinct"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_missing_call_for_changed_sample_and_noncanonical_log_rejected(self):
        self.rows = [
            self.base.row(0, 1, 0, 0x801f, 0x801f),
            self.base.row(1, 2, 0x801f, 0x7c00, 0x7c00),
            self.base.row(2, 2, 0x03e0, 0x03e0, 0x03e0),
        ]
        self.rows[2]["x"], self.rows[2]["y"] = self.coord_b
        self.save()
        # The second coordinate has a real native FT4 change at ordinal
        # 1, but its only forged call has been moved to ordinal 2.
        with self.assertRaisesRegex(ValueError, "unexplained sampled word"):
            verify_multi_pixel_ot(self.source, self.native)
        self.rows = [
            self.base.row(0, 1, 0, 0x801f, 0x801f),
            self.base.row(1, 1, 0, 0x03e0, 0x03e0),
            self.base.row(2, 2, 0x801f, 0x7c00, 0x7c00),
        ]
        self.rows[1]["x"], self.rows[1]["y"] = self.coord_b
        self.save()
        pixel_path = self.native/"putpixel-native-events.jsonl"
        modified = pixel_path.read_bytes()[:-1]
        pixel_path.write_bytes(modified)
        meta_path = self.source/"gpu-putpixel-multi-ot.json"
        meta = json.loads(meta_path.read_text())
        meta["putpixel_events_sha256"] = sha(modified)
        meta_path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "noncanonical two-word"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_interleaved_per_coordinate_hidden_gap_rejected(self):
        # Global event step order can be correct while one individual
        # word's WritePixel chain inside a primitive has an impossible gap.
        self.rows.insert(2, self.base.row(2, 1, 0x1234, 0x801f, 0x801f))
        self.rows[3]["step"] = 3
        self.save()
        with self.assertRaisesRegex(ValueError, "per-primitive word continuity broken"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_rehashed_snapshot_bound_mismatch_rejected(self):
        # A forged first call can obey the original opaque PC copy
        # while disagreeing with the actual native PRE snapshot.
        self.rows[0]["before"] = 0x0001
        self.save()
        with self.assertRaisesRegex(ValueError, "contradicts native primitive VRAM bounds"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_frame_disagreement_rejected_before_vram_attribution(self):
        self.rows[1]["frame"] = 13
        self.save()
        with self.assertRaisesRegex(ValueError, "another frame"):
            verify_multi_pixel_ot(self.source, self.native)

    def test_global_shared_cap_rejected(self):
        # 64 total interleaved events is truncated, regardless of how
        # many belong to each coordinate; do not claim completeness.
        self.rows = [self.base.row(i, 1, 0, 0, 0) for i in range(64)]
        for index, item in enumerate(self.rows):
            item["x"], item["y"] = self.coord_a if index % 2 == 0 else self.coord_b
        self.save()
        with self.assertRaisesRegex(ValueError, "truncation cap"):
            verify_multi_pixel_ot(self.source, self.native)


if __name__ == "__main__":
    unittest.main()
