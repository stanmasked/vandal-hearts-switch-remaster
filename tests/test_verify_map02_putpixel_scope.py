"""Asset-free scoped native PutPixel ↔ source-keyed DrawOTag correlation tests."""
import hashlib
import json
import struct
import unittest

import test_verify_map02_native_overdraw as fixture
from tools.verify_map02_putpixel_scope import verify_pixel_ot


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pixel(raw, x, y):
    return struct.unpack_from("<H", raw, (y*1024+x)*2)[0]


class PixelToOriginalPrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.NativeOverdrawTests(
            methodName="test_repeated_changed_pixel_words_and_bit15_transitions")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.root = self.base.source
        self.native = self.base.native
        self.coord = (30,30)
        self.pixel_rows = self.make_rows()
        self.save()

    def row(self, i, ordinal, before, front, after, semi=0):
        return {
            "stage":"native_putpixel", "step":i, "frame":12,
            "primitive_ordinal":ordinal, "primitive_type":2,
            "x":self.coord[0],"y":self.coord[1],
            "before":before,"front":front,"after":after,
            "abr":1,"semi":semi,"textured":1,"accurate":1,
        }

    def make_rows(self):
        p1=pixel(self.base.base.bytes_before,*self.coord)
        p2=pixel(self.base.first,*self.coord)
        p3=pixel(self.base.second,*self.coord)
        return [self.row(0,1,p1,p2,p2), self.row(1,2,p2,p3,p3)]

    def save(self):
        self.base.save()
        data=b"".join((json.dumps(e,sort_keys=True)+"\n").encode()
                      for e in self.pixel_rows)
        (self.native/"putpixel-native-events.jsonl").write_bytes(data)
        meta={
          "schema":"vh.map02.native-putpixel-ot.v1",
          "source_frame":411,
          "gpu_draw_frame":12,
          "overdraw_manifest_sha256":sha(
              (self.root/"gpu-native-overdraw.json").read_bytes()),
          "native_events_sha256":sha(
              (self.native/"gpu-native-events.jsonl").read_bytes()),
          "putpixel_events_sha256":sha(data),
        }
        (self.root/"gpu-putpixel-ot.json").write_text(
            json.dumps(meta,sort_keys=True))

    def test_binds_same_coordinate_to_two_distinct_source_draws(self):
        result=verify_pixel_ot(self.root,self.native)
        self.assertEqual(result["native_drawotag_primitives_checked"],3)
        self.assertEqual(result["source_keyed_ft4_draws_checked"],2)
        self.assertEqual(result["source_ft4_draws_with_scoped_calls"],2)
        self.assertEqual(result["calls_attributed_to_source_keyed_ft4"],2)
        self.assertEqual(result["observed_native_putpixel_calls"],2)
        # Preserve both the independent main-branch STP/ABR bins and
        # PR #55's exact source-keyed PC PutPixel accounting.
        self.assertEqual(result["observed_opaque_putpixel_by_accuracy"], [0, 2])
        self.assertEqual(sum(
            bucket["calls"] for mode in
            result["observed_semi_putpixel_by_accuracy_and_abr"]
            for bucket in mode), 0)
        self.assertFalse(result["blendg1_equation_verified"])
        self.assertFalse(result["ps1_hardware_abr_equivalence_verified"])
        self.assertEqual(result["observed_bit15_unset_to_set_calls"],1)
        self.assertEqual(result["observed_bit15_set_to_unset_calls"],1)
        self.assertEqual(result["source_ft4_sampled_changed_word_draws"],2)
        self.assertEqual(result["source_ft4_scoped_changed_putpixel_calls"],2)
        self.assertEqual(result["source_ft4_scoped_unchanged_putpixel_calls"],0)
        self.assertEqual(result["source_ft4_scoped_color_and_bit15_putpixel_calls"],2)
        self.assertEqual(
            result["source_ft4_scoped_transient_draws_invisible_to_vram_delta"],0)
        self.assertEqual(result["source_ft4_sampled_bit15_only_changes"],0)
        self.assertEqual(result["source_ft4_sampled_color_only_changes"],0)
        self.assertEqual(result["source_ft4_sampled_color_and_bit15_changes"],2)
        self.assertFalse(
            result["source_ft4_sampled_first_changed_pre_equals_last_changed_post"])
        self.assertFalse(result["source_ft4_sampled_endpoint_causality_verified"])
        self.assertTrue(result["pixel_to_primitive_frame_ordinal_matched"])
        self.assertTrue(result["native_vram_primitive_bounds_consistent"])
        for key in ("complete_original_pixel_stream_proven",
                    "no_missing_putpixel_calls_proven",
                    "missing_pixel_cause_identified",
                    "physical_ps1_abr_mask_correctness_verified",
                    "original_gameplay_authenticated","raw_game_data_emitted"):
            self.assertFalse(result[key])
        public=json.dumps(result)
        for private in ('"x"','"y"',"front","before","tpage","clut","0x801f"):
            self.assertNotIn(private,public)

    def test_same_color_call_is_credited_but_not_vram_delta(self):
        p0=pixel(self.base.base.bytes_before,*self.coord)
        self.pixel_rows=[
            self.row(0,1,p0,p0,p0),
            self.row(1,1,p0,0x801f,0x801f),
            self.row(2,2,0x801f,0x7c00,0x7c00),
        ]
        self.save()
        result=verify_pixel_ot(self.root,self.native)
        self.assertEqual(result["actual_same_color_calls_invisible_to_vram_delta"],1)
        self.assertEqual(result["calls_attributed_to_source_keyed_ft4"],3)
        self.assertEqual(result["source_ft4_scoped_changed_putpixel_calls"],2)
        self.assertEqual(result["source_ft4_scoped_unchanged_putpixel_calls"],1)
        self.assertEqual(
            result["source_ft4_scoped_transient_draws_invisible_to_vram_delta"],0)

    def test_two_real_putpixel_changes_can_cancel_inside_one_ft4(self):
        # First MAP02-matched FT4 performs two observed writes at this
        # coordinate: 0 -> bit15 -> 0. Its entire PRE/POST VRAM is
        # identical, while the second FT4 visibly changes the word.
        # Count both calls; do not infer a raster skip from the delta.
        original = bytes(self.base.base.bytes_before)
        self.base.base.override_snapshots = {
            3: original, 4: original, 5: self.base.second,
        }
        self.pixel_rows = [
            self.row(0,1,0,0x8000,0x8000),
            self.row(1,1,0x8000,0,0),
            self.row(2,2,0,0x7c00,0x7c00),
        ]
        self.save()
        result = verify_pixel_ot(self.root,self.native)
        self.assertEqual(result["source_ft4_sampled_changed_word_draws"],1)
        self.assertEqual(result["source_ft4_draws_without_observable_word_change"],1)
        self.assertEqual(result["source_ft4_scoped_changed_putpixel_calls"],3)
        self.assertEqual(result["source_ft4_scoped_unchanged_putpixel_calls"],0)
        self.assertEqual(result["source_ft4_scoped_bit15_only_putpixel_calls"],2)
        self.assertEqual(result["source_ft4_scoped_color_only_putpixel_calls"],1)
        self.assertEqual(result["source_ft4_scoped_color_and_bit15_putpixel_calls"],0)
        self.assertEqual(
            result["source_ft4_scoped_transient_draws_invisible_to_vram_delta"],1)
        self.assertEqual(result["calls_attributed_to_source_keyed_ft4"],3)
        self.assertFalse(result["no_missing_putpixel_calls_proven"])

    def test_source_ft4_two_accurate_semi_blends_same_word_abrs_1_and_2(self):
        # The same source-matched primitive performs two real accurate
        # BlendG1 calls. A BGR555 endpoint delta alone cannot reveal
        # which ABR requests generated the intermediate 0x801f word.
        original = bytes(self.base.base.bytes_before)
        first = bytearray(original)
        struct.pack_into("<H", first, (30*1024+30)*2, 0x801e)
        self.base.base.override_snapshots = {
            3:bytes(first), 4:bytes(first), 5:self.base.second,
        }
        self.pixel_rows = [
            self.row(0,1,0,0x001f,0x801f,semi=1),
            self.row(1,1,0x801f,0x8001,0x801e,semi=1),
            self.row(2,2,0x801e,0x7c00,0x7c00),
        ]
        self.pixel_rows[1]["abr"]=2
        self.save()
        report=verify_pixel_ot(self.root,self.native)
        self.assertEqual(report["semi_transparent_putpixel_requests"],2)
        self.assertEqual(report["accurate_pc_blend_results_checked"],2)
        self.assertEqual(report["source_ft4_scoped_semitransparent_blend_calls"],2)
        bins = report["observed_semi_putpixel_by_accuracy_and_abr"]
        self.assertEqual(bins[1][1]["calls"], 1)
        self.assertEqual(bins[1][2]["calls"], 1)
        self.assertEqual(sum(bucket["calls"] for bucket in bins[0]), 0)
        self.assertEqual(report["observed_opaque_putpixel_by_accuracy"], [0, 1])
        self.assertFalse(report["blendg1_equation_verified"])
        self.assertFalse(report["ps1_hardware_abr_equivalence_verified"])
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr0_calls"],0)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr1_calls"],1)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr2_calls"],1)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr3_calls"],0)
        self.assertEqual(report["source_ft4_scoped_accurate_semi_blend_calls"],2)
        self.assertEqual(report["source_ft4_scoped_legacy_semi_blend_calls"],0)
        self.assertEqual(report["source_ft4_scoped_draws_with_multiple_semi_blends"],1)
        self.assertEqual(report["source_ft4_scoped_changed_putpixel_calls"],3)
        self.assertEqual(report["source_ft4_sampled_changed_word_draws"],2)

        # A forged ABR is rejected even when the claimed final value,
        # per-primitive endpoints and all SHA digests are recomputed.
        self.pixel_rows[1]["abr"]=0
        self.save()
        with self.assertRaisesRegex(ValueError, "semi-transparent PutPixel"):
            verify_pixel_ot(self.root,self.native)

    def test_source_ft4_semi_blend_abrs_0_and_3_on_adjacent_draws(self):
        original = bytes(self.base.base.bytes_before)
        first = bytearray(original)
        second = bytearray(first)
        struct.pack_into("<H", first, (30*1024+30)*2, 0xbc00)
        second[:] = first
        struct.pack_into("<H", second, (30*1024+30)*2, 0xbc07)
        self.base.base.override_snapshots = {
            3:bytes(first),4:bytes(first),5:bytes(second),
        }
        self.pixel_rows = [
            self.row(0,1,0,0x7c00,0xbc00,semi=1),
            self.row(1,2,0xbc00,0x001f,0xbc07,semi=1),
        ]
        self.pixel_rows[0]["abr"]=0
        self.pixel_rows[1]["abr"]=3
        self.save()
        report=verify_pixel_ot(self.root,self.native)
        self.assertEqual(report["source_ft4_scoped_semitransparent_blend_calls"],2)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr0_calls"],1)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr3_calls"],1)
        self.assertEqual(report["source_ft4_scoped_draws_with_multiple_semi_blends"],0)
        self.assertEqual(report["source_ft4_scoped_accurate_semi_blend_calls"],2)
        self.assertEqual(report["source_ft4_scoped_color_and_bit15_putpixel_calls"],1)
        self.assertEqual(report["source_ft4_scoped_color_only_putpixel_calls"],1)

    def test_two_scoped_ft4_bit15_changes_cancel_at_temporal_endpoints(self):
        # Two observed PutPixel calls (0 -> bit15 -> 0) leave the
        # sampled VRAM word unchanged at the first PRE / final POST.
        # Neither individual FT4 draw is itself a zero-change event.
        original = bytes(self.base.base.bytes_before)
        first = bytearray(original)
        struct.pack_into("<H", first, (30*1024+30)*2, 0x8000)
        self.base.base.override_snapshots = {
            3: bytes(first), 4: bytes(first), 5: original,
        }
        self.pixel_rows = [
            self.row(0,1,0,0x8000,0x8000),
            self.row(1,2,0x8000,0,0),
        ]
        self.save()
        result = verify_pixel_ot(self.root,self.native)
        self.assertEqual(result["source_ft4_sampled_changed_word_draws"],2)
        self.assertEqual(result["source_ft4_sampled_bit15_only_changes"],2)
        self.assertEqual(result["source_ft4_scoped_changed_putpixel_calls"],2)
        self.assertEqual(result["source_ft4_scoped_bit15_only_putpixel_calls"],2)
        self.assertEqual(
            result["source_ft4_scoped_transient_draws_invisible_to_vram_delta"],0)
        self.assertEqual(result["source_ft4_sampled_color_only_changes"],0)
        self.assertEqual(result["source_ft4_sampled_color_and_bit15_changes"],0)
        self.assertTrue(
            result["source_ft4_sampled_first_changed_pre_equals_last_changed_post"])
        self.assertEqual(result["observed_bit15_unset_to_set_calls"],1)
        self.assertEqual(result["observed_bit15_set_to_unset_calls"],1)
        self.assertEqual(result["calls_attributed_to_source_keyed_ft4"],2)

    def test_unmatched_ft4_can_change_sampled_word_between_matched_faces(self):
        # Three native PutPixel calls, but only the first and last
        # belong to the two source-keyed MAP02 FT4s. The intermediate
        # DrawOTag FT4 is deliberately absent from the source bundle.
        unrelated = self.base.base.event(6, "draw", {
            "tpage": 3, "clut": 10,
            "xy": [20,20,70,20,20,70,70,70],
            "uv": [0,0,4,0,0,4,4,4],
        })
        self.base.base.entries.insert(2, unrelated)
        original = bytes(self.base.base.bytes_before)
        first = bytearray(original)
        middle = bytearray(original)
        struct.pack_into("<H", first, (30*1024+30)*2, 0x801f)
        struct.pack_into("<H", middle, (30*1024+30)*2, 0x03e0)
        self.base.base.override_snapshots = {
            3:bytes(first), 4:bytes(first),
            5:bytes(middle), 6:bytes(middle), 7:original,
        }
        self.pixel_rows = [
            self.row(0,1,0,0x801f,0x801f),
            self.row(1,2,0x801f,0x03e0,0x03e0),
            self.row(2,3,0x03e0,0,0),
        ]
        self.save()
        result = verify_pixel_ot(self.root,self.native)
        self.assertEqual(result["native_drawotag_primitives_checked"],4)
        self.assertEqual(result["observed_native_putpixel_calls"],3)
        self.assertEqual(result["calls_attributed_to_source_keyed_ft4"],2)
        self.assertEqual(result["source_ft4_scoped_changed_putpixel_calls"],2)
        self.assertEqual(result["source_ft4_scoped_unchanged_putpixel_calls"],0)
        self.assertEqual(result["source_ft4_scoped_bit15_only_putpixel_calls"],0)
        self.assertEqual(result["source_ft4_scoped_color_only_putpixel_calls"],1)
        self.assertEqual(result["source_ft4_scoped_color_and_bit15_putpixel_calls"],1)
        self.assertEqual(result["source_ft4_sampled_changed_word_draws"],2)
        self.assertTrue(
            result["source_ft4_sampled_first_changed_pre_equals_last_changed_post"])
        self.assertFalse(result["source_ft4_sampled_endpoint_causality_verified"])

    def test_source_ft4_repeated_legacy_semi_blends_do_not_mix_modes(self):
        # Pinned legacy WritePixel: ABR0 halves 0x001f red to 0x000f;
        # ABR3 adds one quarter of front red, yielding 0x0016.
        # AccurateEnabled remains 0 throughout this same native stream.
        original = bytes(self.base.base.bytes_before)
        first = bytearray(original)
        struct.pack_into("<H", first, (30*1024+30)*2, 0x0016)
        self.base.base.override_snapshots = {
            3:bytes(first),4:bytes(first),5:self.base.second,
        }
        self.pixel_rows = [
            self.row(0,1,0,0x001f,0x000f,semi=1),
            self.row(1,1,0x000f,0x001f,0x0016,semi=1),
            self.row(2,2,0x0016,0x7c00,0x7c00),
        ]
        for row in self.pixel_rows:
            row["accurate"]=0
        self.pixel_rows[0]["abr"]=0
        self.pixel_rows[1]["abr"]=3
        self.save()
        report=verify_pixel_ot(self.root,self.native)
        self.assertEqual(report["accurate_pc_blend_results_checked"],0)
        self.assertEqual(report["legacy_pc_blend_results_checked"],2)
        self.assertEqual(report["source_ft4_scoped_legacy_semi_blend_calls"],2)
        self.assertEqual(report["source_ft4_scoped_accurate_semi_blend_calls"],0)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr0_calls"],1)
        self.assertEqual(report["source_ft4_scoped_semi_blend_abr3_calls"],1)
        self.assertEqual(report["source_ft4_scoped_draws_with_multiple_semi_blends"],1)
        self.assertTrue(report["single_runtime_accurate_mode_consistent"])
        self.pixel_rows[1]["after"]=0x0017
        self.save()
        with self.assertRaisesRegex(ValueError,"semi-transparent PutPixel"):
            verify_pixel_ot(self.root,self.native)

    def test_unmatched_semi_blend_is_not_counted_as_source_ft4(self):
        unrelated = self.base.base.event(6, "draw", {
            "tpage":3, "clut":10,
            "xy":[1,1,5,1,1,5,5,5],
            "uv":[0,0,4,0,0,4,4,4],
        })
        self.base.base.entries.insert(2,unrelated)
        self.base.base.override_snapshots = {
            3:self.base.first,4:self.base.first,
            5:self.base.first,6:self.base.first,7:self.base.second,
        }
        # Original PC ABR1: BGR555 0x801f + transparent-front 0
        # makes a legitimate same-value semi-transparent WritePixel.
        self.pixel_rows = [
            self.row(0,1,0,0x801f,0x801f),
            self.row(1,2,0x801f,0,0x801f,semi=1),
            self.row(2,3,0x801f,0x7c00,0x7c00),
        ]
        self.save()
        report=verify_pixel_ot(self.root,self.native)
        self.assertEqual(report["observed_native_putpixel_calls"],3)
        self.assertEqual(report["semi_transparent_putpixel_requests"],1)
        self.assertEqual(report["accurate_pc_blend_results_checked"],1)
        self.assertEqual(report["source_ft4_scoped_semitransparent_blend_calls"],0)
        self.assertEqual(report["source_ft4_scoped_accurate_semi_blend_calls"],0)
        self.assertEqual(report["source_ft4_scoped_draws_with_multiple_semi_blends"],0)
        self.assertEqual(report["calls_attributed_to_source_keyed_ft4"],2)
        self.assertEqual(report["source_ft4_scoped_changed_putpixel_calls"],2)

    def test_same_color_calls_do_not_claim_a_changed_ft4_word(self):
        original = bytes(self.base.base.bytes_before)
        self.base.base.override_snapshots = {3:original,4:original,5:original}
        self.pixel_rows=[self.row(0,1,0,0,0),self.row(1,2,0,0,0)]
        self.save()
        result=verify_pixel_ot(self.root,self.native)
        self.assertEqual(result["source_ft4_sampled_changed_word_draws"],0)
        self.assertIsNone(
            result["source_ft4_sampled_first_changed_pre_equals_last_changed_post"])
        self.assertEqual(result["actual_same_color_calls_invisible_to_vram_delta"],2)
        self.assertEqual(result["source_ft4_scoped_unchanged_putpixel_calls"],2)
        self.assertEqual(result["source_ft4_scoped_changed_putpixel_calls"],0)
        self.assertEqual(
            result["source_ft4_scoped_transient_draws_invisible_to_vram_delta"],0)
        self.assertEqual(result["source_ft4_draws_without_observable_word_change"],2)

    def test_dr_mode_cannot_emit_even_a_same_value_putpixel_call(self):
        # The pinned DR_MODE dispatcher never enters WritePixel. Native
        # VRAM snapshots alone would not detect this forged no-op call.
        mode = self.base.base.event(6,"draw",None)
        self.assertEqual(mode["primitive_type"],5)
        self.base.base.entries.insert(2,mode)
        self.base.base.override_snapshots = {
            3:self.base.first, 4:self.base.first, 5:self.base.first,
            6:self.base.first, 7:self.base.second,
        }
        self.pixel_rows = [
            self.row(0,1,0,0x801f,0x801f),
            self.row(1,2,0x801f,0x801f,0x801f),
            self.row(2,3,0x801f,0x7c00,0x7c00),
        ]
        self.pixel_rows[1]["primitive_type"]=5
        self.save()
        with self.assertRaisesRegex(ValueError,"DR_MODE.*cannot call PutPixel"):
            verify_pixel_ot(self.root,self.native)

    def test_scoped_pixel_jsonl_rejects_rehashed_truncation_crlf_and_nul(self):
        path=self.native/"putpixel-native-events.jsonl"
        manifest=self.root/"gpu-putpixel-ot.json"
        original=path.read_bytes()
        self.assertTrue(original.endswith(b"\n"))
        for mutated in (
            original[:-1],
            original.replace(b"\n",b"\r\n"),
            original.replace(b"\n",b"\x00\n",1),
        ):
            with self.subTest(tail=repr(mutated[-15:])):
                self.save()
                path.write_bytes(mutated)
                m=json.loads(manifest.read_text())
                m["putpixel_events_sha256"]=sha(mutated)
                manifest.write_text(json.dumps(m,sort_keys=True))
                with self.assertRaisesRegex(ValueError,"noncanonical scoped PutPixel"):
                    verify_pixel_ot(self.root,self.native)

    def test_accurate_semitransparent_pc_blend_and_tamper_rejected(self):
        # Keep the native snapshots untouched and forge only the claimed
        # input to WritePixel. The previously checked primitive endpoints
        # remain coherent but the actual PC BlendG1 result must differ.
        self.pixel_rows[0]["semi"] = 1
        self.pixel_rows[0]["front"] = 0x001f
        self.save()
        report = verify_pixel_ot(self.root, self.native)
        self.assertEqual(report["accurate_pc_blend_results_checked"], 1)
        self.assertEqual(report["legacy_pc_blend_results_checked"], 0)
        self.assertTrue(report["source_pinned_pc_writepixel_effects_verified"])
        self.assertTrue(report["single_runtime_accurate_mode_consistent"])
        self.pixel_rows[0]["front"] = 0x0001
        self.save()
        with self.assertRaisesRegex(ValueError, "semi-transparent PutPixel"):
            verify_pixel_ot(self.root, self.native)

    def test_legacy_semitransparent_pc_blend_and_tamper_rejected(self):
        # Legacy PackColor clears bit15 even when the input texel sets it.
        original = bytes(self.base.base.bytes_before)
        first = bytearray(original)
        second = bytearray(first)
        struct.pack_into("<H", first, (30*1024+30)*2, 0x001f)
        second[:] = first
        struct.pack_into("<H", second, (30*1024+30)*2, 0x7c00)
        self.base.base.override_snapshots = {
            3:bytes(first), 4:bytes(first), 5:bytes(second),
        }
        self.pixel_rows = [
            self.row(0,1,0,0x801f,0x001f,semi=1),
            self.row(1,2,0x001f,0x7c00,0x7c00),
        ]
        self.pixel_rows[0]["accurate"] = 0
        self.pixel_rows[1]["accurate"] = 0
        self.save()
        report = verify_pixel_ot(self.root,self.native)
        self.assertEqual(report["legacy_pc_blend_results_checked"],1)
        self.assertEqual(report["accurate_pc_blend_results_checked"],0)
        self.pixel_rows[0]["after"] = 0x801f
        self.save()
        with self.assertRaisesRegex(ValueError,"semi-transparent PutPixel"):
            verify_pixel_ot(self.root,self.native)

    def test_mixed_runtime_accurate_mode_rejected_even_with_opaque_calls(self):
        # AccurateEnabled() is process-static in pinned original raster.
        # Recomputing the JSONL digest must not legitimize an impossible
        # accurate/legacy algorithm change between consecutive calls.
        self.pixel_rows[1]["accurate"] = 0
        self.save()
        with self.assertRaisesRegex(ValueError, "inconsistent native AccurateEnabled"):
            verify_pixel_ot(self.root, self.native)

    def test_wrong_frame_scope_or_primitive_type_refused(self):
        self.pixel_rows[0]["frame"]=13
        self.save()
        with self.assertRaisesRegex(ValueError,"different DrawOTag frame"):
            verify_pixel_ot(self.root,self.native)
        self.pixel_rows[0]["frame"]=12
        self.pixel_rows[0]["primitive_type"]=5
        self.save()
        with self.assertRaisesRegex(ValueError,"type disagrees"):
            verify_pixel_ot(self.root,self.native)

    def test_wrong_native_ordinal_or_reordering_refused(self):
        self.pixel_rows[0]["primitive_ordinal"]=3
        self.save()
        with self.assertRaisesRegex(ValueError,"expected integer"):
            verify_pixel_ot(self.root,self.native)
        self.pixel_rows[0]["primitive_ordinal"]=2
        self.pixel_rows[1]["primitive_ordinal"]=1
        self.save()
        with self.assertRaisesRegex(ValueError,"moves backward"):
            verify_pixel_ot(self.root,self.native)

    def test_missing_call_cannot_explain_changed_ft4_pixel(self):
        self.pixel_rows=self.pixel_rows[1:]
        self.pixel_rows[0]["step"]=0
        self.save()
        with self.assertRaisesRegex(ValueError,"unexplained pixel change"):
            verify_pixel_ot(self.root,self.native)

    def test_within_one_primitive_hidden_change_rejected(self):
        first=self.pixel_rows[0]
        third=self.pixel_rows[1]
        self.pixel_rows=[
            self.row(0,1,first["before"],first["before"],first["before"]),
            self.row(1,1,0x1234,0x801f,0x801f),
            self.row(2,2,third["before"],third["front"],third["after"]),
        ]
        self.save()
        with self.assertRaisesRegex(ValueError,"within-primitive.*continuity"):
            verify_pixel_ot(self.root,self.native)

    def test_manifest_log_mutation_invalid_and_record_cap_refused(self):
        p=self.native/"putpixel-native-events.jsonl"
        p.write_bytes(p.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"scoped PutPixel event log: SHA-256 mismatch"):
            verify_pixel_ot(self.root,self.native)
        self.pixel_rows=[
            self.row(i,1,0,0,0) for i in range(64)
        ]
        self.save()
        with self.assertRaisesRegex(ValueError,"truncation cap"):
            verify_pixel_ot(self.root,self.native)

    def test_opaque_copy_invariant_and_duplicate_field_rejected(self):
        self.pixel_rows[1]["front"]=0x1
        self.save()
        with self.assertRaisesRegex(ValueError,"opaque PutPixel"):
            verify_pixel_ot(self.root,self.native)
        self.save()
        p=self.native/"putpixel-native-events.jsonl"
        p.write_text('{"step":0,"step":1}\n')
        # Wrong file is SHA-bound, so reject tampering before JSON.
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            verify_pixel_ot(self.root,self.native)

if __name__=="__main__":
    unittest.main()
