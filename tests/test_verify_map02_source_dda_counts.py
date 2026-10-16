"""Entirely synthetic MAP02 source/GTE/OT/native GPU/DDA counter join."""
import hashlib
import json
import struct
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

    def install_scoped_putpixel(self):
        # Only one selected coordinate is observed. Reuse the actual
        # fixture's two consecutive source-FT4 VRAM changes at (30,30).
        def at(raw):
            return struct.unpack_from("<H", raw, 2*(30*1024+30))[0]
        v0 = at(self.baseline.base.bytes_before)
        v1 = at(self.baseline.first)
        v2 = at(self.baseline.base.override_snapshots.get(
            5, self.baseline.second))
        rows = [
            {"stage":"native_putpixel", "step":i, "frame":12,
             "primitive_ordinal":i+1, "primitive_type":2,
             "x":30, "y":30, "before":a, "front":b, "after":b,
             "abr":1, "semi":0, "textured":1, "accurate":1}
            for i, (a,b) in enumerate(((v0,v1),(v1,v2)))
        ]
        raw=b"".join((json.dumps(x,sort_keys=True)+"\n").encode()
                     for x in rows)
        (self.gpu/"putpixel-native-events.jsonl").write_bytes(raw)
        meta={
            "schema":"vh.map02.native-putpixel-ot.v1",
            "source_frame":411, "gpu_draw_frame":12,
            "overdraw_manifest_sha256":sha(
                (self.src/"gpu-native-overdraw.json").read_bytes()),
            "native_events_sha256":sha(
                (self.gpu/"gpu-native-events.jsonl").read_bytes()),
            "putpixel_events_sha256":sha(raw),
        }
        (self.src/"gpu-putpixel-ot.json").write_text(
            json.dumps(meta,sort_keys=True))

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

    def test_optional_same_binary_putpixel_evidence_reverified(self):
        no_pixel = self.verify()
        self.assertFalse(no_pixel["optional_scoped_putpixel_evidence_verified"])
        self.install_scoped_putpixel()
        result = self.verify()
        self.assertTrue(result["optional_scoped_putpixel_evidence_verified"])
        self.assertEqual(result["observed_coordinate_scoped_putpixel_calls"],2)
        self.assertEqual(result["observed_putpixel_calls_on_source_ft4"],2)
        self.assertEqual(result["observed_same_color_putpixel_calls"],0)
        self.assertFalse(result["pixel_writes_equal_to_samples_proven"])

        # SHA-invalid coordinate-scoped evidence cannot be mixed with a
        # separately verified DDA file from the same native DrawOTag run.
        path=self.gpu/"putpixel-native-events.jsonl"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            self.verify()

    def test_half_supplied_putpixel_capture_is_rejected(self):
        (self.gpu/"putpixel-native-events.jsonl").write_bytes(b"\n")
        with self.assertRaisesRegex(ValueError,"evidence is incomplete"):
            self.verify()
        (self.gpu/"putpixel-native-events.jsonl").unlink()
        (self.src/"gpu-putpixel-ot.json").write_text("{}")
        with self.assertRaisesRegex(ValueError,"evidence is incomplete"):
            self.verify()

    def test_nonzero_dda_with_unchanged_vram_and_observed_same_color_putpixel(self):
        # FT4 ordinal 2 selects nonzero texture colors, but its full
        # before/after VRAM images match. This alone proves NO reason:
        # identical blend/copy results, invisible writes and alpha behavior
        # cannot be inferred from DDA aggregate counts.
        self.baseline.base.override_snapshots[5] = self.baseline.first
        self.save()
        uncertain = self.verify()
        self.assertEqual(uncertain["source_ft4_draws_without_vram_change"], 1)
        self.assertEqual(
            uncertain["source_ft4_nonzero_dda_samples_without_vram_change"], 1)
        self.assertEqual(
            uncertain["source_ft4_opaque_dda_samples_without_vram_change"], 1)
        self.assertEqual(
            uncertain["source_ft4_stp_dda_samples_without_vram_change"], 1)
        self.assertEqual(
            uncertain["source_ft4_no_vram_delta_with_direct_same_color_putpixel"], 0)
        self.assertFalse(uncertain["optional_scoped_putpixel_evidence_verified"])

        # Direct same-color PutPixel call at chosen private VRAM coordinate,
        # authenticated by an independent per-primitive before/after gate.
        self.install_scoped_putpixel()
        verified = self.verify()
        self.assertTrue(verified["optional_scoped_putpixel_evidence_verified"])
        self.assertEqual(
            verified["source_ft4_no_vram_delta_with_observed_putpixel_calls"], 1)
        self.assertEqual(
            verified["source_ft4_no_vram_delta_with_direct_same_color_putpixel"], 1)
        self.assertEqual(
            verified["source_ft4_nonzero_dda_no_vram_delta_with_same_color_putpixel"], 1)
        self.assertEqual(
            verified["source_ft4_no_vram_delta_with_direct_transient_putpixel_change"], 0)
        self.assertFalse(verified["pixel_writes_equal_to_samples_proven"])

    def test_putpixel_write_then_restore_hidden_by_final_vram_snapshot(self):
        # Final VRAM equality can hide transient PutPixel changes.
        self.baseline.base.override_snapshots[5] = self.baseline.first
        self.save()
        self.install_scoped_putpixel()
        pixel_file = self.gpu / "putpixel-native-events.jsonl"
        rows = [json.loads(line) for line in pixel_file.read_bytes().splitlines()]
        final_color = rows[1]["before"]
        temporary_color = final_color ^ 0x001f
        self.assertNotEqual(final_color, temporary_color)
        rows[1]["front"] = rows[1]["after"] = temporary_color
        last = dict(rows[1])
        last.update(step=2, before=temporary_color, front=final_color,
                    after=final_color)
        rows.append(last)
        payload = b"".join((json.dumps(x, sort_keys=True)+"\\n").encode()
                           for x in rows)
        pixel_file.write_bytes(payload)
        manifest = self.src/"gpu-putpixel-ot.json"
        data = json.loads(manifest.read_text())
        data["putpixel_events_sha256"] = sha(payload)
        manifest.write_text(json.dumps(data, sort_keys=True))
        evidence = self.verify()
        self.assertEqual(
            evidence["source_ft4_no_vram_delta_with_direct_same_color_putpixel"], 0)
        self.assertEqual(
            evidence["source_ft4_no_vram_delta_with_direct_transient_putpixel_change"], 1)
        self.assertEqual(
            evidence["observed_coordinate_scoped_putpixel_calls"], 3)
        self.assertFalse(evidence["fallback_or_same_color_write_reason_proven"])

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
