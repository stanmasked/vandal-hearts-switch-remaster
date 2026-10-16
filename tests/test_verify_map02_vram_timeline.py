"""Synthetic per-submission VRAM changes, hashes, source/GTE and security gates.

The fixture comes from the already pinned private single-frame validator.
No game image, original VRAM or proprietary data is used in these tests.
"""
import hashlib
import json
import unittest

import test_verify_map02_frame_bundle as fixture
from tools.verify_map02_vram_timeline import verify_timeline

def digest(data):
    return hashlib.sha256(data).hexdigest()


class Map02TimelineTests(unittest.TestCase):
    def setUp(self):
        # Reuse the independently audited synthetic MAP02 camera/source
        # record rather than constructing another unreviewed GTE example.
        self.base = fixture.FrameBundleTests(
            methodName="test_two_source_faces_and_compiled_gte_vram_probes")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.root = self.base.folder
        self.frame = fixture.FRAME
        self.events = self.base.events
        self.map_bytes = self.base.map_bytes
        self.vrams = [self.base.vram_bytes, self.base.vram_bytes]
        second = bytearray(self.vrams[1])
        fixture.word(second, 690, 499, 0x03e0)  # second face's indexed CLUT
        fixture.word(second, 0, 0, 0x1234)       # unrelated VRAM location
        self.vrams[1] = bytes(second)
        for probe in self.events[1]["texture"]["probes"]:
            probe["bgr555"] = 0x03e0
        self.manifest = {
            "schema":"vh.map02.vram.timeline.v1",
            "frame":self.frame,
            "ot_size":1024,
            "pc_source_commit":fixture.PINNED_PC_SOURCE,
            "decoded_map_sha256":digest(self.map_bytes),
        }
        self.save()

    def save(self):
        for i, event in enumerate(self.events):
            event["submission_index"] = i
            event["vram_snapshot_index"] = i
        log = b"".join((json.dumps(e,sort_keys=True)+"\n").encode()
                       for e in self.events)
        self.manifest["events_sha256"] = digest(log)
        self.manifest["snapshots"] = [
            {"index":i,"frame":self.frame,"sha256":digest(raw)}
            for i,raw in enumerate(self.vrams)
        ]
        (self.root/"gpu-events.jsonl").write_bytes(log)
        (self.root/"map02.decoded.bin").write_bytes(self.map_bytes)
        for i,raw in enumerate(self.vrams):
            (self.root/f"gpu-vram-{i:03d}.bin").write_bytes(raw)
        (self.root/"timeline.json").write_text(
            json.dumps(self.manifest,sort_keys=True),encoding="utf-8")

    def test_two_original_source_keys_and_independent_changed_clut(self):
        report = verify_timeline(self.root)
        self.assertEqual(report["submitted_faces_checked"], 2)
        self.assertEqual(report["snapshots_sha256_verified"], 2)
        self.assertEqual(report["compiled_pc_gte_matches"], 2)
        self.assertEqual(report["observed_color_probes_checked"], 4)
        self.assertEqual(report["vram_4bpp_crop_texels_checked"], 512)
        self.assertEqual(report["snapshot_transitions_checked"], 1)
        self.assertEqual(report["snapshot_transitions_with_vram_changes"], 1)
        self.assertEqual(report["changed_vram_words_across_snapshots"], 2)
        self.assertEqual(report["changed_current_face_clut_words"], 1)
        self.assertEqual(report["changed_current_face_texture_words"], 0)
        self.assertEqual(report["transitions_affecting_current_face_texture_or_clut"], 1)
        for marker in (
            "frame_capture_authenticated",
            "continuous_vram_write_monitoring",
            "unobserved_intervening_vram_writes_excluded",
            "retail_ps1_pixels_verified",
            "raw_game_data_emitted"):
            self.assertFalse(report[marker])
        public = json.dumps(report,sort_keys=True)
        for secret in ("perimeter_xy","vertex_xyz","bgr555","camera","texture.probes"):
            self.assertNotIn(secret,public)

    def test_same_snapshot_is_not_reported_as_mutation(self):
        self.vrams[1] = self.vrams[0]
        for probe in self.events[1]["texture"]["probes"]:
            probe["bgr555"] = 0x7c00
        self.save()
        report=verify_timeline(self.root)
        self.assertEqual(report["snapshot_transitions_with_vram_changes"],0)
        self.assertEqual(report["changed_vram_words_across_snapshots"],0)
        self.assertEqual(report["transitions_affecting_current_face_texture_or_clut"],0)

    def test_unrelated_change_does_not_claim_texture_or_clut_change(self):
        second=bytearray(self.vrams[0])
        fixture.word(second,0,0,0x1234)
        self.vrams[1]=bytes(second)
        for probe in self.events[1]["texture"]["probes"]:
            probe["bgr555"]=0x7c00
        self.save()
        report=verify_timeline(self.root)
        self.assertEqual(report["changed_vram_words_across_snapshots"],1)
        self.assertEqual(report["changed_current_face_texture_words"],0)
        self.assertEqual(report["changed_current_face_clut_words"],0)

    def test_modified_current_texel_word_is_localized(self):
        second=bytearray(self.vrams[1])
        fixture.word(second,508,192,0x1111)  # local 240..243 for page7
        self.vrams[1]=bytes(second)
        # The new index is 1, not a separately observed palette reading.
        self.events[1]["texture"].pop("probes")
        self.save()
        report=verify_timeline(self.root)
        self.assertEqual(report["changed_current_face_texture_words"],1)
        self.assertEqual(report["changed_current_face_clut_words"],1)
        self.assertEqual(report["observed_color_probes_checked"],2)

    def test_reject_changed_snapshot_even_with_self_consistent_events(self):
        path=self.root/"gpu-vram-001.bin"
        raw=bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            verify_timeline(self.root)

    def test_wrong_frame_index_or_source_and_bgr555_probes(self):
        self.manifest["snapshots"][1]["frame"]=self.frame+1
        (self.root/"timeline.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,"different frame"):
            verify_timeline(self.root)
        self.save()
        event=self.events[1]
        event["register_frame"]=self.frame+1
        self.save()
        with self.assertRaisesRegex(ValueError,"register_frame disagrees"):
            verify_timeline(self.root)
        event["register_frame"]=self.frame
        event["source"]["local_gfx"] += 1
        self.save()
        with self.assertRaisesRegex(ValueError,"GFX mismatch"):
            verify_timeline(self.root)
        event["source"]["local_gfx"] -= 1
        event["texture"]["probes"][0]["bgr555"]=0x7c00
        self.save()
        with self.assertRaisesRegex(ValueError,"texture probe disagrees"):
            verify_timeline(self.root)

    def test_fail_closed_on_missing_duplicate_linked_and_malformed(self):
        path=self.root/"gpu-vram-001.bin"
        path.unlink()
        with self.assertRaisesRegex(ValueError,"missing, linked or non-regular"):
            verify_timeline(self.root)
        self.save()
        path.unlink()
        path.symlink_to(self.root/"gpu-vram-000.bin")
        with self.assertRaisesRegex(ValueError,"missing, linked or non-regular"):
            verify_timeline(self.root)
        path.unlink()
        self.save()
        self.manifest["snapshots"][1]["index"]=0
        (self.root/"timeline.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,"out-of-order"):
            verify_timeline(self.root)
        self.save()
        self.manifest["snapshots"] = self.manifest["snapshots"][:1]
        (self.root/"timeline.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,"one dedicated"):
            verify_timeline(self.root)
        self.save()
        self.events[1]["source"]=self.events[0]["source"].copy()
        self.save()
        with self.assertRaisesRegex(ValueError,"duplicate submitted source"):
            verify_timeline(self.root)

    def test_reject_duplicate_json_fields_and_reordered_submissions(self):
        path=self.root/"timeline.json"
        path.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(ValueError,"duplicate JSON field"):
            verify_timeline(self.root)
        self.save()
        lines=(self.root/"gpu-events.jsonl").read_bytes().splitlines(keepends=True)
        bad=lines[1]+lines[0]
        (self.root/"gpu-events.jsonl").write_bytes(bad)
        self.manifest["events_sha256"]=digest(bad)
        path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,"nonmonotonic submission"):
            verify_timeline(self.root)


if __name__ == "__main__":
    unittest.main()
