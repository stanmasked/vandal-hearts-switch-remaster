"""Asset-free end-to-end source-map/GTE -> actual-format native GPU FT4 matching."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_verify_map02_frame_bundle as fixture
from tools.verify_map02_source_native_ft4_join import verify_join

def digest(data):
    return hashlib.sha256(data).hexdigest()

class SourceToNativeFt4JoinTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.FrameBundleTests(
            methodName="test_two_source_faces_and_compiled_gte_vram_probes")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        temp=tempfile.TemporaryDirectory(prefix="map02-gpu-join-")
        self.addCleanup(temp.cleanup)
        self.native=Path(temp.name)
        self.source=self.base.folder
        self.frame_gpu=12
        self.entries=[
            self.event(0,"draw",None),   # Sprite/tile/other draw packet, not a terrain FT4
            self.event(2,"draw",self.packet(1)),  # GPU OT order reversed on purpose
            self.event(4,"draw",self.packet(0))
        ]
        self.bytes_before=bytes(self.base.vram_bytes)
        self.override_snapshots={}
        self.save()

    def packet(self,index):
        event=self.base.events[index]
        g=event["gte"]["perimeter_xy"]
        t=event["texture"]
        xys=[c for i in (0,1,3,2) for c in g[i]]
        u,v,w,h=t["u"],t["v"],t["w"],t["h"]
        return {"tpage":t["tpage"],"clut":t["clut"],
                "xy":xys,"uv":[u,v,u+w,v,u,v+h,u+w,v+h]}

    def event(self,step,operation,packet):
        return {
            "stage":"native_vram","step":step,"frame":self.frame_gpu,
            "phase":"before","operation":operation,
            "snapshot":f"gpu-{step:04d}-vram.bin",
            "rect":None,"dest":[0,0],"rgb":[0,0,0],
            "primitive_type":2 if packet is not None else 5,
            "semi":0,"window":[0,0,0,0],
            "draw_mode":[5,0,0],"upload":"","ft4":packet,
        }

    def save(self):
        self.base.write()
        seq=[]
        for item in self.entries:
            before=copy.deepcopy(item)
            after=copy.deepcopy(item)
            after["step"]=before["step"]+1
            after["phase"]="after"
            after["snapshot"]=f"gpu-{after['step']:04d}-vram.bin"
            seq.extend((before,after))
        for i,event in enumerate(seq):
            event["step"]=i
            event["snapshot"]=f"gpu-{i:04d}-vram.bin"
        stream=b"".join((json.dumps(e,sort_keys=True)+"\n").encode() for e in seq)
        (self.native/"gpu-native-events.jsonl").write_bytes(stream)
        for i,event in enumerate(seq):
            raw=self.override_snapshots.get(i,self.bytes_before)
            (self.native/event["snapshot"]).write_bytes(raw)
        data={
            "schema":"vh.map02.source-native-ft4-join.v1",
            "source_frame":fixture.FRAME,
            "gpu_draw_frame":self.frame_gpu,
            "bundle_manifest_sha256":digest((self.source/"bundle.json").read_bytes()),
            "native_events_sha256":digest(stream),
        }
        (self.source/"gpu-face-join.json").write_text(
            json.dumps(data,sort_keys=True),encoding="utf-8")

    def test_two_source_faces_join_in_reversed_ot_order_with_other_draw(self):
        report=verify_join(self.source,self.native)
        self.assertEqual(report["source_frame"],411)
        self.assertEqual(report["native_gpu_frame"],12)
        self.assertEqual(report["source_face_count"],2)
        self.assertEqual(report["native_gpu_ft4_packets"],2)
        self.assertEqual(report["uniquely_matched_source_faces"],2)
        self.assertGreater(report["material_vram_words_compared"],0)
        self.assertTrue(report["screen_corners_uv_page_clut_window_exact"])
        self.assertTrue(report["source_gte_verified_by_compiled_reference"])
        self.assertTrue(report["native_before_after_capture_verified"])
        for key in ("source_to_gpu_frame_binding_authenticated",
                    "retail_gameplay_authenticated",
                    "ps1_hardware_raster_pixels_verified",
                    "raw_game_data_emitted"):
            self.assertFalse(report[key])
        result=json.dumps(report)
        for secret in ("perimeter_xy","vertices","xy","240,","31978","801f"):
            self.assertNotIn(secret,result)

    def test_single_frame_distinguishes_proven_clip_from_unknown_zero_delta(self):
        legacy = verify_join(self.source, self.native)
        self.assertEqual(legacy["matched_ft4_draws_proven_no_coverage"], 0)
        self.assertEqual(legacy["matched_ft4_draws_zero_delta_cause_unknown"], 2)
        # Native FT4 pairs occur at steps 2/3 and 4/5, with different
        # DRAWENV clip state. No execution-order/source-order guess.
        for entry in self.entries:
            entry["draw_env"] = ([0, 0, 1024, 512, 1500, 1500]
                                  if entry["step"] == 2 else
                                  [0, 0, 1024, 512, 0, 0])
        self.save()
        report = verify_join(self.source, self.native)
        self.assertEqual(report["matched_ft4_draws_proven_no_coverage"], 1)
        self.assertEqual(report["matched_ft4_draws_zero_delta_cause_unknown"], 1)

        # This write stays inside the GPU drawing area, but the FT4
        # vertices are far outside it after the captured draw offset.
        changed = bytearray(self.bytes_before)
        fixture.word(changed, 0, 0, 0x801f)
        self.override_snapshots[3] = bytes(changed)
        self.override_snapshots[4] = bytes(changed)
        self.save()
        with self.assertRaisesRegex(ValueError, "geometry entirely outside"):
            verify_join(self.source, self.native)

    def test_single_frame_native_ft4_post_draw_pixel_delta(self):
        report = verify_join(self.source, self.native)
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 0)
        self.assertEqual(report["matched_ft4_draws_without_vram_change"], 2)
        self.assertFalse(report["native_ft4_pixels_bit_exact_to_ps1"])

        # Per-source draw at step 4 has a separate post-draw snapshot at 5.
        # A framebuffer write outside the texture crop is not a mismatch.
        after = bytearray(self.bytes_before)
        fixture.word(after, 0, 0, 0x8001)
        self.override_snapshots[5] = bytes(after)
        self.save()
        report = verify_join(self.source, self.native)
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 1)
        self.assertEqual(
            report["matched_ft4_draw_changed_texture_or_clut_words"], 0)
        self.assertEqual(report["matched_ft4_draws_without_vram_change"], 1)

    def test_uv_corner_page_clut_and_window_mismatch_rejected(self):
        edits=[
            ("uv",0,241),("xy",0,21),("tpage",None,6),
            ("clut",None,31977),
        ]
        for field,index,value in edits:
            with self.subTest(field=field):
                orig=copy.deepcopy(self.entries[2]["ft4"])
                if index is None:
                    self.entries[2]["ft4"][field]=value
                else:
                    self.entries[2]["ft4"][field][index]=value
                self.save()
                with self.assertRaisesRegex(ValueError,"no exact GPU FT4"):
                    verify_join(self.source,self.native)
                self.entries[2]["ft4"]=orig
        self.entries[2]["window"]=[1,0,0,0]
        self.save()
        with self.assertRaisesRegex(ValueError,"no exact GPU FT4"):
            verify_join(self.source,self.native)

    def test_indistinguishable_duplicate_gpu_packets_rejected(self):
        self.entries.insert(2,self.event(6,"draw",copy.deepcopy(self.packet(0))))
        self.save()
        with self.assertRaisesRegex(ValueError,"ambiguous GPU FT4 packets"):
            verify_join(self.source,self.native)

    def test_two_distinct_source_cells_with_same_packet_not_guessed(self):
        # Prove original face identity isn't guessed from matching GFX alone.
        # Both source records intentionally share GTE, UV, and CLUT here.
        self.base.events[1]["texture"]=copy.deepcopy(self.base.events[0]["texture"])
        self.entries[1]["ft4"]=self.packet(0)
        self.save()
        with self.assertRaisesRegex(ValueError,"ambiguous GPU FT4|matches multiple source"):
            verify_join(self.source,self.native)

    def test_different_material_vram_texel_rejected_even_when_ft4_matches(self):
        modified=bytearray(self.bytes_before)
        fixture.word(modified,380,192,0x2222)  # used by source face 0
        # GPU state entering this draw must equal the previous draw's
        # output; keep the bridge valid to test material mismatch itself.
        self.override_snapshots[3]=bytes(modified)
        self.override_snapshots[4]=bytes(modified)
        self.save()
        with self.assertRaisesRegex(ValueError,"texture or CLUT words differ"):
            verify_join(self.source,self.native)

    def test_unrelated_render_target_vram_mutation_allowed(self):
        modified=bytearray(self.bytes_before)
        fixture.word(modified,0,0,0xffff)
        # An unrelated render-target write must still be recorded by an
        # adjacent draw before it becomes the next draw's initial VRAM.
        self.override_snapshots[3]=bytes(modified)
        self.override_snapshots[4]=bytes(modified)
        self.override_snapshots[5]=bytes(modified)
        self.save()
        report=verify_join(self.source,self.native)
        self.assertEqual(report["uniquely_matched_source_faces"],2)

    def test_mutated_native_capture_log_digest_and_frame_mapping_rejected(self):
        path=self.native/"gpu-native-events.jsonl"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"native GPU event log: SHA-256 mismatch"):
            verify_join(self.source,self.native)
        self.save()
        manifest=self.source/"gpu-face-join.json"
        meta=json.loads(manifest.read_text())
        meta["gpu_draw_frame"]=13
        manifest.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError,"different native GPU frame"):
            verify_join(self.source,self.native)

    def test_source_bundle_hash_tampering_rejected(self):
        path=self.source/"bundle.json"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"source manifest: SHA-256 mismatch"):
            verify_join(self.source,self.native)

    def test_non_ft4_and_missing_terrain_packets_rejected(self):
        self.entries=self.entries[:1]
        self.save()
        with self.assertRaisesRegex(ValueError,"no FT4 draw packets"):
            verify_join(self.source,self.native)
        self.entries=[self.event(0,"draw",self.packet(0))]
        self.save()
        with self.assertRaisesRegex(ValueError,"no exact GPU FT4"):
            verify_join(self.source,self.native)

if __name__=="__main__":
    unittest.main()
