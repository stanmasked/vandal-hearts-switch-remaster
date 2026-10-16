"""Synthetic OT/depth/LIFO parity from source-keyed faces to native DrawOTag."""
import copy
import hashlib
import json
import unittest

import test_verify_map02_source_native_ft4_join as fixture
from tools.verify_map02_source_native_ot_order import (
    expected_addprim_draw_indices, verify_ot_join,
)

def sha(data):
    return hashlib.sha256(data).hexdigest()


class NativeOtOrderingTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.SourceToNativeFt4JoinTests(
            methodName="test_two_source_faces_join_in_reversed_ot_order_with_other_draw")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.source = self.base.source
        self.native = self.base.native
        self.save()

    def save(self):
        self.base.save()
        meta = {
            "schema": "vh.map02.source-native-ot-order.v1",
            "source_frame": 411,
            "gpu_draw_frame": 12,
            "face_join_manifest_sha256": sha(
                (self.source/"gpu-face-join.json").read_bytes()),
            "source_events_sha256": sha(
                (self.source/"gpu-events.jsonl").read_bytes()),
            "native_events_sha256": sha(
                (self.native/"gpu-native-events.jsonl").read_bytes()),
            "source_events_in_addprim_order": True,
            "one_clear_otag_one_draw_otag": True,
        }
        (self.source/"gpu-ot-order-join.json").write_text(
            json.dumps(meta, sort_keys=True))

    def test_same_bucket_lifo_with_nonterrain_packets(self):
        report=verify_ot_join(self.source,self.native)
        self.assertEqual(report["terrain_faces_with_verified_relative_ot_order"],2)
        self.assertEqual(report["same_ot_bucket_order_pairs_checked"],1)
        self.assertEqual(report["different_ot_bucket_order_pairs_checked"],0)
        self.assertEqual(report["screen_aabb_overlap_candidates"],1)
        self.assertEqual(report["same_ot_bucket_aabb_overlap_candidates"],1)
        self.assertEqual(report["intervening_unmatched_ft4_packets"],0)
        self.assertTrue(report["source_to_gpu_ft4_and_vram_join_verified"])
        self.assertTrue(report["pc_ot_bucket_forward_lifo_model_applied"])
        for name in ("source_addprim_order_authenticated","single_ot_pass_authenticated",
                     "all_drawotag_packets_source_keyed","exact_pixel_overdraw_verified",
                     "retail_gameplay_authenticated","ps1_hardware_pixels_verified",
                     "raw_game_data_emitted"):
            self.assertFalse(report[name])
        published=json.dumps(report)
        for private in ("perimeter_xy","vertices","clut","8191","31978"):
            self.assertNotIn(private,published)

    def test_native_gpu_order_matching_ft4_but_not_lifo_is_rejected(self):
        self.base.entries[1], self.base.entries[2] = (
            self.base.entries[2], self.base.entries[1])
        self.save()
        with self.assertRaisesRegex(ValueError,"violates.*OT depth/LIFO"):
            verify_ot_join(self.source,self.native)

    def test_gpu_order_with_unrelated_ft4_interleaved_still_valid(self):
        e=self.base.event(6,"draw",{
            "tpage":3, "clut":10,
            "xy":[1,1,5,1,1,5,5,5],
            "uv":[0,0,4,0,0,4,4,4],
        })
        self.base.entries.insert(2,e)
        self.save()
        report=verify_ot_join(self.source,self.native)
        self.assertEqual(report["intervening_unmatched_ft4_packets"],1)

    def test_depth_slot_and_reverse_submit_independent_reference(self):
        # Source submissions at three buckets and two ties. Expected OT
        # traversal 0..n-1, with head insertion within each bucket.
        events=[{"gte":{"raw_otz":z}} for z in (128,192,128,4,192)]
        self.assertEqual(expected_addprim_draw_indices(events,1024),
                         [4,1,2,0,3])
        with self.assertRaisesRegex(ValueError,"outside ordering table"):
            expected_addprim_draw_indices([{"gte":{"raw_otz":1200}}],1024)
        with self.assertRaisesRegex(ValueError,"expected integer"):
            expected_addprim_draw_indices([{"gte":{"raw_otz":True}}],1024)

    def test_source_order_and_single_ot_pass_must_be_asserted(self):
        path=self.source/"gpu-ot-order-join.json"
        for key in ("source_events_in_addprim_order","one_clear_otag_one_draw_otag"):
            for bad in (False, 1, "true"):
                self.save()
                manifest=json.loads(path.read_text())
                manifest[key]=bad
                path.write_text(json.dumps(manifest))
                with self.subTest(key=key,bad=bad):
                    with self.assertRaisesRegex(ValueError,"must be asserted explicitly"):
                        verify_ot_join(self.source,self.native)

    def test_frame_and_original_log_integrity(self):
        path=self.source/"gpu-ot-order-join.json"
        manifest=json.loads(path.read_text())
        manifest["gpu_draw_frame"]=13
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"frame binding differs"):
            verify_ot_join(self.source,self.native)
        self.save()
        (self.native/"gpu-native-events.jsonl").write_bytes(
            (self.native/"gpu-native-events.jsonl").read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"native DrawOTag event log: SHA-256 mismatch"):
            verify_ot_join(self.source,self.native)

    def test_duplicate_gpu_candidate_is_not_silently_sorted(self):
        self.base.entries.append(self.base.event(6,"draw",
                                                 copy.deepcopy(self.base.packet(0))))
        self.save()
        with self.assertRaisesRegex(ValueError,"ambiguous GPU FT4"):
            verify_ot_join(self.source,self.native)

    def test_submitted_source_bundle_mutation_detected(self):
        self.base.events[1]["gte"]["raw_otz"]=192
        self.save()
        with self.assertRaisesRegex(ValueError,"compiled PC GTE mismatch"):
            verify_ot_join(self.source,self.native)


if __name__=="__main__":
    unittest.main()
