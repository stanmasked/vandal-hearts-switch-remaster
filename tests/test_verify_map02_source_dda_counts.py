"""Entirely synthetic MAP02 source/GTE/OT/native GPU/DDA counter join."""
import hashlib
import json
import unittest

import test_verify_map02_native_overdraw as fixture
from tools.verify_map02_source_dda_counts import verify_source_dda_counts


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceDdaCountsJoinTests(unittest.TestCase):
    def setUp(self):
        self.baseline = fixture.NativeOverdrawTests(
            methodName="test_repeated_changed_pixel_words_and_bit15_transitions")
        self.baseline.setUp()
        self.addCleanup(self.baseline.doCleanups)
        self.src = self.baseline.source
        self.gpu = self.baseline.native
        # GPU draws: 0 unrelated sprite, 1 source face 1, 2 source face 0.
        self.rows = [self.row(0, 1, 3, 2, 7),
                     self.row(1, 2, 4, 5, 9)]
        self.save()

    def row(self, i, ordinal, zero, stp, opaque):
        return {
            "stage": "native_dda_ft4_texel_counts", "step": i,
            "frame": 12, "primitive_ordinal": ordinal, "primitive_type": 2,
            "zero": zero, "stp": stp, "opaque": opaque,
        }

    def save(self):
        self.baseline.save()
        raw = b"".join((json.dumps(x, sort_keys=True) + "\n").encode()
                       for x in self.rows)
        (self.gpu / "native-dda-ft4-texel-counts.jsonl").write_bytes(raw)
        gpu_log = (self.gpu / "gpu-native-events.jsonl").read_bytes()
        meta = {
            "schema": "vh.map02.native-dda-ft4-texel-counts.v1",
            "gpu_draw_frame": 12,
            "native_events_sha256": sha(gpu_log),
            "texel_counts_sha256": sha(raw),
        }
        (self.gpu / "native-dda-ft4-counts.json").write_text(
            json.dumps(meta, sort_keys=True))
        join = {
            "schema": "vh.map02.source-native-dda-count-join.v1",
            "source_frame": 411, "gpu_draw_frame": 12,
            "overdraw_manifest_sha256": sha(
                (self.src / "gpu-native-overdraw.json").read_bytes()),
            "native_dda_manifest_sha256": sha(
                (self.gpu / "native-dda-ft4-counts.json").read_bytes()),
        }
        (self.src / "gpu-native-dda-count-join.json").write_text(
            json.dumps(join, sort_keys=True))

    def verify(self):
        return verify_source_dda_counts(self.src, self.gpu)

    def test_two_source_faces_reversed_draw_order_and_vram(self):
        r = self.verify()
        self.assertEqual(r["source_frame"], 411)
        self.assertEqual(r["native_gpu_frame"], 12)
        self.assertEqual(r["source_keyed_ft4_draws_correlated"], 2)
        self.assertEqual(r["native_unmatched_ft4_draws"], 0)
        self.assertEqual(r["source_ft4_dda_zero_samples"], 7)
        self.assertEqual(r["source_ft4_dda_nonzero_stp_samples"], 7)
        self.assertEqual(r["source_ft4_dda_nonzero_opaque_samples"], 16)
        self.assertEqual(r["source_ft4_draws_with_no_dda_samples"], 0)
        self.assertTrue(r["source_geometry_gte_and_ot_order_reverified"])
        self.assertTrue(r["native_dda_sample_counters_reverified"])
        for key in ("source_to_native_gpu_frame_provenance_authenticated",
                    "pixel_writes_equal_to_samples_proven",
                    "fallback_or_same_color_write_reason_proven",
                    "physical_ps1_raster_equivalence_proven",
                    "original_gameplay_authenticated", "raw_game_data_emitted"):
            self.assertFalse(r[key])
        public = json.dumps(r)
        for value in ('"xy"', '"clut"', '"tpage"', '"perimeter_xy"',
                      "31978", "0x801f"):
            self.assertNotIn(value, public)

    def test_no_dda_sampling_with_native_vram_change_is_not_falsely_rejected(self):
        self.rows[0]["zero"] = self.rows[0]["stp"] = self.rows[0]["opaque"] = 0
        self.save()
        r = self.verify()
        self.assertEqual(r["source_ft4_draws_with_no_dda_samples"], 1)
        self.assertEqual(
            r["source_ft4_draws_with_no_dda_samples_but_vram_changes"], 1)
        self.assertFalse(r["fallback_or_same_color_write_reason_proven"])

    def test_dda_wrong_ordinal_and_stale_hash_rejected(self):
        self.rows[0]["primitive_ordinal"] = 0
        self.save()
        with self.assertRaisesRegex(ValueError, "ordinal"):
            self.verify()
        self.rows[0]["primitive_ordinal"] = 1
        self.save()
        path = self.gpu / "native-dda-ft4-texel-counts.jsonl"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.verify()

    def test_source_binding_and_ot_order_tampering_rejected(self):
        binding = self.src / "gpu-native-dda-count-join.json"
        m = json.loads(binding.read_text())
        m["source_frame"] = 412
        binding.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "frame binding"):
            self.verify()
        self.save()
        self.baseline.base.entries[1], self.baseline.base.entries[2] = (
            self.baseline.base.entries[2], self.baseline.base.entries[1])
        self.save()
        with self.assertRaisesRegex(ValueError, "violates.*OT depth/LIFO"):
            self.verify()

    def test_empty_samples_or_opaque_only_preserve_distinct_verdicts(self):
        for row in self.rows:
            row["zero"] = row["stp"] = row["opaque"] = 0
        self.save()
        r = self.verify()
        self.assertEqual(r["source_ft4_draws_with_no_dda_samples"], 2)
        self.assertEqual(
            r["source_ft4_draws_with_no_dda_samples_but_vram_changes"], 2)
        for row in self.rows:
            row["opaque"] = 1
        self.save()
        r = self.verify()
        self.assertEqual(r["source_ft4_draws_with_no_dda_samples"], 0)
        self.assertEqual(r["source_ft4_dda_nonzero_opaque_samples"], 2)


if __name__ == "__main__":
    unittest.main()
