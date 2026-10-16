"""Independent source-keyed FT4/VRAM timeline vs native PC GPU before-draw join.

All captures, camera geometry and VRAM words are synthetic. Real source and
native GPU frames are different clocks (411 vs 12 in this test); the explicit
SHA-bound mapping is mandatory. No proprietary assets are present.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_verify_map02_vram_timeline as timeline_fixture
from tools.verify_map02_source_native_ft4_join import (
    _source_signature, verify_timeline_join,
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class TimelineToNativeFt4JoinTests(unittest.TestCase):
    def setUp(self):
        self.base = timeline_fixture.Map02TimelineTests(
            methodName="test_two_original_source_keys_and_independent_changed_clut")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        temp = tempfile.TemporaryDirectory(prefix="vh-map02-timeline-ft4-")
        self.addCleanup(temp.cleanup)
        self.native = Path(temp.name)
        self.native_frame = 12
        # Deliberately reversed relative to source submission order.
        self.packets = [self.packet(1), self.packet(0)]
        self.native_vrams = [self.base.vrams[1], self.base.vrams[0]]
        self.save()

    def packet(self, source_index):
        xy, uv, tpage, clut, window = _source_signature(
            self.base.events[source_index])
        return {"xy": xy, "uv": uv, "tpage": tpage, "clut": clut,
                "window": window}

    def save(self):
        self.base.save()
        self.native_events = []
        snapshots = []
        for item, raw in zip(self.packets, self.native_vrams):
            for phase in ("before", "after"):
                i = len(self.native_events)
                self.native_events.append({
                    "stage": "native_vram", "step": i,
                    "frame": self.native_frame, "phase": phase,
                    "operation": "draw",
                    "snapshot": f"gpu-{i:04d}-vram.bin",
                    "rect": None, "dest": [0, 0], "rgb": [0, 0, 0],
                    "primitive_type": 2, "semi": 0,
                    "window": copy.deepcopy(item["window"]),
                    "draw_mode": [item["tpage"], 0, 0], "upload": "",
                    "ft4": {k: copy.deepcopy(item[k])
                            for k in ("xy", "uv", "tpage", "clut")},
                })
                snapshots.append(raw)
        self.native_snapshots = snapshots
        self.write_native()

    def write_native(self):
        raw = b"".join((json.dumps(e, sort_keys=True) + "\n").encode()
                       for e in self.native_events)
        (self.native / "gpu-native-events.jsonl").write_bytes(raw)
        for i, img in enumerate(self.native_snapshots):
            (self.native / f"gpu-{i:04d}-vram.bin").write_bytes(img)
        mapping = {
            "schema": "vh.map02.source-native-ft4-timeline-join.v1",
            "source_frame": self.base.frame,
            "gpu_draw_frame": self.native_frame,
            "timeline_manifest_sha256": digest(
                (self.base.root / "timeline.json").read_bytes()),
            "native_events_sha256": digest(raw),
        }
        (self.base.root / "gpu-face-timeline-join.json").write_text(
            json.dumps(mapping, sort_keys=True), encoding="utf-8")

    def verify(self):
        return verify_timeline_join(self.base.root, self.native)

    def test_different_clocks_reversed_ot_order_and_per_face_clut(self):
        result = self.verify()
        self.assertEqual(result["source_frame"], 411)
        self.assertEqual(result["native_gpu_frame"], 12)
        self.assertEqual(result["source_submissions_verified"], 2)
        self.assertEqual(result["uniquely_matched_source_faces"], 2)
        self.assertEqual(result["per_submission_vram_snapshots_compared"], 2)
        self.assertGreater(result["material_vram_words_compared"], 0)
        for flag in ("source_gpu_frames_assumed_same",
                     "draw_execution_order_assumed",
                     "native_stream_authenticated_complete",
                     "retail_gameplay_authenticated",
                     "ps1_hardware_raster_pixels_verified",
                     "raw_game_data_emitted"):
            self.assertFalse(result[flag])
        published = json.dumps(result)
        for secret in ("perimeter_xy", "vertices", "31978", "31979",
                       "bgr555", "camera"):
            self.assertNotIn(secret, published)

    def test_native_ft4_pixel_deltas_include_bgr555_bit15(self):
        baseline = self.verify()
        self.assertEqual(baseline["matched_ft4_draw_changed_vram_words"], 0)
        self.assertEqual(
            baseline["matched_ft4_draw_changed_texture_or_clut_words"], 0)
        self.assertEqual(baseline["matched_ft4_draws_without_vram_change"], 2)
        self.assertFalse(baseline["native_ft4_pixels_bit_exact_to_ps1"])

        # First FT4 writes one unrelated render-target pixel and updates its
        # own CLUT word. Neither write may be invented into the source capture.
        after = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(after, 0, 0, 0x801f)  # bit 15 survives
        timeline_fixture.fixture.word(after, 690, 499, 0x001f)
        self.native_snapshots[1] = bytes(after)
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 2)
        self.assertEqual(
            report["matched_ft4_draw_changed_texture_or_clut_words"], 1)
        self.assertEqual(report["matched_ft4_draws_without_vram_change"], 1)

        # Changing only bit15 of BGR555 still counts as a VRAM write.
        after = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(after, 690, 499, 0x83e0)
        self.native_snapshots[1] = bytes(after)
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 2)
        self.assertEqual(
            report["matched_ft4_draw_changed_texture_or_clut_words"], 1)

    def test_changed_current_face_clut_detected_at_native_draw(self):
        damaged = bytearray(self.native_snapshots[0])
        timeline_fixture.fixture.word(damaged, 690, 499, 0x7c00)
        self.native_snapshots[0] = bytes(damaged)
        self.write_native()
        with self.assertRaisesRegex(ValueError, "texture or CLUT words differ"):
            self.verify()

    def test_swapped_per_submission_vram_not_accepted(self):
        self.native_snapshots[0], self.native_snapshots[2] = (
            self.native_snapshots[2], self.native_snapshots[0])
        self.native_snapshots[1], self.native_snapshots[3] = (
            self.native_snapshots[3], self.native_snapshots[1])
        self.write_native()
        with self.assertRaisesRegex(ValueError, "texture or CLUT words differ"):
            self.verify()

    def test_unrelated_native_render_target_change_allowed(self):
        raw = bytearray(self.native_snapshots[0])
        timeline_fixture.fixture.word(raw, 0, 0, 0xffff)
        self.native_snapshots[0] = bytes(raw)
        self.native_snapshots[1] = bytes(raw)
        self.write_native()
        self.assertEqual(self.verify()["uniquely_matched_source_faces"], 2)

    def test_native_ft4_texture_state_must_not_drift_inside_primitive(self):
        self.native_events[1]["window"][0] = 1
        self.write_native()
        with self.assertRaisesRegex(ValueError, "state changed during primitive"):
            self.verify()
        self.save()
        self.native_events[1]["draw_mode"][0] += 1
        self.write_native()
        with self.assertRaisesRegex(ValueError, "state changed during primitive"):
            self.verify()

    def test_duplicate_packets_and_incorrect_clock_binding(self):
        self.packets.append(copy.deepcopy(self.packets[0]))
        self.native_vrams.append(self.native_vrams[0])
        self.save()
        with self.assertRaisesRegex(ValueError, "ambiguous GPU FT4"):
            self.verify()
        self.packets = self.packets[:2]
        self.native_vrams = self.native_vrams[:2]
        self.save()
        manifest = self.base.root / "gpu-face-timeline-join.json"
        data = json.loads(manifest.read_text())
        data["gpu_draw_frame"] += 1
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different native GPU frame"):
            self.verify()

    def test_source_and_native_hash_tampering_rejected(self):
        manifest = self.base.root / "gpu-face-timeline-join.json"
        data = json.loads(manifest.read_text())
        data["timeline_manifest_sha256"] = "0" * 64
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "timeline manifest: SHA-256 mismatch"):
            self.verify()
        self.save()
        (self.native / "gpu-native-events.jsonl").write_bytes(
            (self.native / "gpu-native-events.jsonl").read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "native GPU log: SHA-256 mismatch"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
