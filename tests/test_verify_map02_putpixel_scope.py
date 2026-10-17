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
        self.assertEqual(result["observed_bit15_unset_to_set_calls"],1)
        self.assertEqual(result["observed_bit15_set_to_unset_calls"],1)
        self.assertEqual(result["source_ft4_sampled_changed_word_draws"],2)
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
        self.assertEqual(result["source_ft4_sampled_color_only_changes"],0)
        self.assertEqual(result["source_ft4_sampled_color_and_bit15_changes"],0)
        self.assertTrue(
            result["source_ft4_sampled_first_changed_pre_equals_last_changed_post"])
        self.assertEqual(result["observed_bit15_unset_to_set_calls"],1)
        self.assertEqual(result["observed_bit15_set_to_unset_calls"],1)
        self.assertEqual(result["calls_attributed_to_source_keyed_ft4"],2)

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
        self.assertTrue(original.endswith(b"\\n"))
        for mutated in (
            original[:-1],
            original.replace(b"\\n",b"\\r\\n"),
            original.replace(b"\\n",b"\\x00\\n",1),
        ):
            with self.subTest(tail=repr(mutated[-15:])):
                self.save()
                path.write_bytes(mutated)
                m=json.loads(manifest.read_text())
                m["putpixel_events_sha256"]=sha(mutated)
                manifest.write_text(json.dumps(m,sort_keys=True))
                with self.assertRaisesRegex(ValueError,"noncanonical scoped PutPixel"):
                    verify_pixel_ot(self.root,self.native)

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
