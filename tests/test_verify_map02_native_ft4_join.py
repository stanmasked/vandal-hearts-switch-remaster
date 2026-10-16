"""Asset-free native DrawOTag FT4 <> source-keyed MAP02 frame matching tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_verify_map02_vram_timeline as timeline_fixture
from tools.verify_map02_native_ft4_join import (
    signature_source, verify_native_ft4_join,
)
from tools.verify_map02_native_gpu_capture import VRAM_BYTES


class NativeFt4SourceJoinTests(unittest.TestCase):
    def setUp(self):
        self.timeline = timeline_fixture.Map02TimelineTests(
            methodName="test_two_original_source_keys_and_independent_changed_clut")
        self.timeline.setUp()
        self.addCleanup(self.timeline.doCleanups)
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-ft4-join-")
        self.addCleanup(self.tmp.cleanup)
        self.native = Path(self.tmp.name)
        self.frame = self.timeline.frame
        self.snapshots = []
        # Original GPU consumes OT buckets in linked-list order, which may
        # differ from source submission order. Intentionally reverse it.
        self.packets = [
            self.packet(self.timeline.events[1]),
            self.packet(self.timeline.events[0]),
        ]
        self.save()

    def packet(self, src):
        xy, uv, tpage, clut, window = signature_source(src)
        return {
            "tpage": tpage, "clut": clut, "xy": list(xy), "uv": list(uv),
            "window": list(window),
        }

    def save(self):
        events = []
        snapshots = []
        for p in self.packets:
            for phase in ("before", "after"):
                index = len(events)
                events.append({
                    "stage": "native_vram",
                    "step": index, "frame": self.frame,
                    "phase": phase,
                    "operation": "draw",
                    "snapshot": f"gpu-{index:04d}-vram.bin",
                    "rect": None,
                    "dest": [0, 0],
                    "rgb": [0, 0, 0],
                    "primitive_type": 2,
                    "semi": 0,
                    "window": p["window"][:],
                    "draw_mode": [p["tpage"], 0, 0],
                    "upload": "",
                    "ft4": {k: copy.deepcopy(p[k])
                            for k in ("tpage", "clut", "xy", "uv")},
                })
                snapshots.append(bytes(VRAM_BYTES))
        self.native_events = events
        self.snapshots = snapshots
        self.write()

    def write(self):
        for i, raw in enumerate(self.snapshots):
            (self.native / f"gpu-{i:04d}-vram.bin").write_bytes(raw)
        (self.native / "gpu-native-events.jsonl").write_bytes(
            b"".join((json.dumps(e, sort_keys=True) + "\n").encode()
                     for e in self.native_events))

    def verify(self):
        return verify_native_ft4_join(self.timeline.root, self.native)

    def test_exact_packets_join_without_assuming_original_draw_order(self):
        result = self.verify()
        self.assertEqual(result["frame"], self.frame)
        self.assertEqual(result["source_ft4_submissions_checked"], 2)
        self.assertEqual(result["native_ft4_packets_observed"], 2)
        self.assertEqual(result["one_to_one_packets_matched"], 2)
        self.assertEqual(result["unmatched_native_ft4_packets"], 0)
        self.assertFalse(result["native_draw_order_assumed"])
        self.assertFalse(result["source_face_attribution_authenticated"])
        self.assertFalse(result["native_gpu_stream_proven_complete"])
        self.assertFalse(result["retail_ps1_pixels_verified"])
        text = json.dumps(result)
        for forbidden in ("perimeter_xy", "vertex_xyz", "xy", "uv",
                          "31978", "31979", "241", "tpage", "clut"):
            self.assertNotIn(forbidden, text)

    def test_mismatch_xy_uv_tpage_clut_and_window_rejected(self):
        alterations = (
            ("xy", 0, 1), ("uv", 2, 1), ("tpage", None, 1),
            ("clut", None, 1), ("window", 0, 1),
        )
        for key, offset, delta in alterations:
            with self.subTest(key=key):
                self.save()
                event = self.native_events[0]
                for pair_event in self.native_events[:2]:
                    if key == "window":
                        pair_event["window"][offset] += delta
                    elif offset is None:
                        pair_event["ft4"][key] += delta
                    else:
                        pair_event["ft4"][key][offset] += delta
                self.write()
                with self.assertRaisesRegex(ValueError, "absent from native GPU"):
                    self.verify()

    def test_extra_unrelated_native_ft4_not_assumed_source(self):
        third = copy.deepcopy(self.packets[0])
        third["xy"][0] += 3
        self.packets.append(third)
        self.save()
        result = self.verify()
        self.assertEqual(result["native_ft4_packets_observed"], 3)
        self.assertEqual(result["one_to_one_packets_matched"], 2)
        self.assertEqual(result["unmatched_native_ft4_packets"], 1)

    def test_duplicate_native_packet_is_ambiguous(self):
        self.packets.append(copy.deepcopy(self.packets[0]))
        self.save()
        with self.assertRaisesRegex(ValueError, "ambiguous native FT4"):
            self.verify()

    def test_changed_native_draw_state_mid_pair_rejected(self):
        self.native_events[1]["window"][0] += 1
        self.write()
        with self.assertRaisesRegex(ValueError, "texture state changed"):
            self.verify()
        self.save()
        self.native_events[1]["draw_mode"][0] += 1
        self.write()
        with self.assertRaisesRegex(ValueError, "texture state changed"):
            self.verify()

    def test_frame_mismatch_and_corrupted_source_vram_rejected(self):
        self.native_events[0]["frame"] += 1
        self.write()
        with self.assertRaisesRegex(ValueError, "different native GPU frame"):
            self.verify()
        self.save()
        image = self.timeline.root / "gpu-vram-001.bin"
        raw = bytearray(image.read_bytes())
        raw[0] ^= 1
        image.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
