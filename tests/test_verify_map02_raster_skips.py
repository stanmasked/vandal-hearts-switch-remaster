"""Synthetic native MAP02 DDA clip/zero-texel skip events, never original assets."""
import hashlib
import json
from pathlib import Path
import unittest

import test_verify_map02_native_overdraw as fixture
from tools.verify_map02_raster_skips import verify_skips


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NativeRasterSkipAuditTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.NativeOverdrawTests(
            methodName="test_repeated_changed_pixel_words_and_bit15_transitions")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.source=self.base.source
        self.native=self.base.native
        self.rows=[
          self.row(0,1,1),  # GPU FT4 source face 1: DDA transparent BGR555
          self.row(1,1,2),  # horizontal clip for source face 1
          self.row(2,2,3),  # source face 0: legacy texture zero
        ]
        self.save()

    def row(self,step,ordinal,reason):
        return {"stage":"native_raster_skip","step":step,"frame":12,
                "primitive_ordinal":ordinal,"primitive_type":2,
                "x":30,"y":30,"reason":reason}

    def save(self):
        self.base.save()
        stream=b"".join((json.dumps(e,sort_keys=True)+"\n").encode()
                        for e in self.rows)
        (self.native/"putpixel-native-skips.jsonl").write_bytes(stream)
        manifest={
            "schema":"vh.map02.native-raster-skip.v1",
            "source_frame":411,
            "gpu_draw_frame":12,
            "overdraw_manifest_sha256":sha(
                (self.source/"gpu-native-overdraw.json").read_bytes()),
            "native_events_sha256":sha(
                (self.native/"gpu-native-events.jsonl").read_bytes()),
            "raster_skip_events_sha256":sha(stream),
        }
        (self.source/"gpu-raster-skips.json").write_text(
            json.dumps(manifest,sort_keys=True))

    def test_three_exact_original_skip_branches_link_to_two_ft4(self):
        result=verify_skips(self.source,self.native)
        self.assertEqual(result["observed_skip_events"],3)
        self.assertEqual(result["observed_dda_zero_bgr555_texel_events"],1)
        self.assertEqual(result["observed_dda_horizontal_span_clip_events"],1)
        self.assertEqual(result["observed_legacy_zero_bgr555_texel_events"],1)
        self.assertEqual(result["source_keyed_ft4_primitives_with_direct_skip_observation"],2)
        self.assertTrue(result["verified_original_source_to_native_gpu_join"])
        self.assertTrue(result["native_drawotag_frame_and_ordinal_checked"])
        for key in ("all_executed_raster_skip_branches_captured",
                    "unlogged_pixel_cause_inferred",
                    "vertical_clip_per_pixel_confirmed",
                    "triangle_coverage_and_mask_test_verified",
                    "ps1_hardware_stp_abr_mask_equivalence",
                    "original_gameplay_authenticated","raw_game_data_emitted"):
            self.assertFalse(result[key])
        report=json.dumps(result)
        for private in ('"x"','"y"','"primitive_ordinal"',"31978","perimeter_xy"):
            self.assertNotIn(private,report)

    def test_one_draw_may_skip_without_any_putpixel_sample(self):
        # A zero-texel branch is real evidence even if no PutPixel occurred
        # at that coordinate; existing PutPixel correlation does not support
        # this case and is deliberately NOT used as a prerequisite.
        self.rows=[self.row(0,1,1)]
        self.save()
        self.assertEqual(verify_skips(self.source,self.native)
                         ["source_keyed_dda_zero_texel_events"],1)
        self.assertFalse((self.native/"putpixel-native-events.jsonl").exists())

    def test_wrong_frame_packet_type_and_record_order_rejected(self):
        self.rows[0]["frame"]=13
        self.save()
        with self.assertRaisesRegex(ValueError,"another DrawOTag frame"):
            verify_skips(self.source,self.native)
        self.rows[0]["frame"]=12
        self.rows[0]["primitive_type"]=5
        self.save()
        with self.assertRaisesRegex(ValueError,"type disagrees"):
            verify_skips(self.source,self.native)
        self.rows[0]["primitive_type"]=2
        self.rows[0]["primitive_ordinal"]=2
        self.save()
        with self.assertRaisesRegex(ValueError,"primitive order decreased"):
            verify_skips(self.source,self.native)

    def test_nontextured_packet_cannot_claim_zero_texel_branch(self):
        # First native packet is synthetic unrelated nontextured packet.
        self.rows=[self.row(0,0,1)]
        self.rows[0]["primitive_type"]=5
        self.save()
        with self.assertRaisesRegex(ValueError,"nontextured"):
            verify_skips(self.source,self.native)
        self.rows[0]["reason"]=2
        self.save()
        r=verify_skips(self.source,self.native)
        self.assertEqual(r["observed_dda_horizontal_span_clip_events"],1)
        self.assertEqual(r["source_keyed_dda_horizontal_clip_events"],0)

    def test_invalid_reason_coordinates_and_cap_rejected(self):
        for field,value in (("reason",8),("x",1024),("y",-1),
                            ("primitive_ordinal",4),("step",True)):
            with self.subTest(field=field):
                before=self.rows[0][field]
                self.rows[0][field]=value
                self.save()
                with self.assertRaisesRegex(ValueError,"expected integer"):
                    verify_skips(self.source,self.native)
                self.rows[0][field]=before
        self.rows=[self.row(i,1,1) for i in range(64)]
        self.save()
        with self.assertRaisesRegex(ValueError,"record cap"):
            verify_skips(self.source,self.native)

    def test_hash_tampering_missing_log_and_symlink_refused(self):
        p=self.native/"putpixel-native-skips.jsonl"
        p.write_bytes(p.read_bytes()+b"\n")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            verify_skips(self.source,self.native)
        self.save()
        p.unlink()
        with self.assertRaisesRegex(ValueError,"missing, symlinked"):
            verify_skips(self.source,self.native)
        p.symlink_to(self.native/"gpu-native-events.jsonl")
        with self.assertRaisesRegex(ValueError,"missing, symlinked"):
            verify_skips(self.source,self.native)

    def test_original_ot_order_rechecked_before_skip_attribution(self):
        self.base.base.entries[1],self.base.base.entries[2]=(
            self.base.base.entries[2],self.base.base.entries[1])
        self.save()
        with self.assertRaisesRegex(ValueError,"violates.*OT depth/LIFO"):
            verify_skips(self.source,self.native)


if __name__=="__main__":
    unittest.main()
