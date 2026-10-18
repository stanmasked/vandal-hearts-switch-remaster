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
    _ft4_audited_crop_classes, _ft4_palette_state,
    _ft4_provably_outside_drawenv,
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
        # Both CLUT palettes coexist by the time DrawOTag starts. GPU OT
        # draws must not jump back to the earlier source upload snapshot.
        self.packets = [self.packet(1), self.packet(0)]
        self.native_vrams = [self.base.vrams[1]] * 2
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
        self.native_snapshots[1:4] = [bytes(after)] * 3
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 2)
        self.assertEqual(
            report["matched_ft4_draw_changed_texture_or_clut_words"], 1)
        self.assertEqual(report["matched_ft4_draws_without_vram_change"], 1)

        # Changing only bit15 of BGR555 still counts as a VRAM write.
        after = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(after, 690, 499, 0x83e0)
        self.native_snapshots[1:4] = [bytes(after)] * 3
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 2)
        self.assertEqual(
            report["matched_ft4_draw_changed_texture_or_clut_words"], 1)

    def test_conservative_ft4_geometry_guard_at_clip_boundary(self):
        xy = [10, 10, 20, 10, 10, 20, 20, 20]
        self.assertIsNone(_ft4_provably_outside_drawenv(None, xy))
        self.assertTrue(_ft4_provably_outside_drawenv(
            [30, 0, 10, 50, 0, 0], xy))  # 20+8 < 30
        self.assertFalse(_ft4_provably_outside_drawenv(
            [28, 0, 10, 50, 0, 0], xy))  # 20+8 touches edge: unknown
        self.assertFalse(_ft4_provably_outside_drawenv(
            [0, 0, 40, 40, 0, 0], xy))
        self.assertTrue(_ft4_provably_outside_drawenv(
            [0, 0, 10, 50, 150, -150], xy))
        self.assertTrue(_ft4_provably_outside_drawenv(
            [0, 0, 0, 512, 0, 0], xy))
        with self.assertRaisesRegex(ValueError, "DRAWENV"):
            _ft4_provably_outside_drawenv([1, 2, 3], xy)
        with self.assertRaisesRegex(ValueError, "vertex"):
            _ft4_provably_outside_drawenv([0, 0, 8, 8, 0, 0], [1, 2])

    def test_all_zero_clut_proves_transparent_ft4_and_rejects_pixel_write(self):
        # The first source face uses CLUT #31978, index 1 = 0x801f.
        # Remove its only nonzero entry in BOTH independently SHA-bound
        # timeline snapshots and correct the observed PC texture probes.
        for i in range(2):
            raw = bytearray(self.base.vrams[i])
            timeline_fixture.fixture.word(raw, 673, 499, 0)
            self.base.vrams[i] = bytes(raw)
        for probe in self.base.events[0]["texture"]["probes"]:
            probe["bgr555"] = 0
        self.native_vrams = [self.base.vrams[1]] * 2
        self.save()
        result = self.verify()
        self.assertEqual(
            result["matched_ft4_draws_zero_delta_full_4bpp_clut_transparent"], 1)
        self.assertEqual(result["matched_ft4_draws_zero_delta_cause_unknown"], 1)
        self.assertEqual(result["matched_ft4_draws_proven_no_coverage"], 0)

        # A native FT4 cannot draw any pixel if its entire indexed CLUT
        # was zero before the primitive; reject contradictory post-snapshots.
        after = bytearray(self.native_snapshots[3])
        timeline_fixture.fixture.word(after, 0, 0, 0x001f)
        self.native_snapshots[3] = bytes(after)
        self.write_native()
        with self.assertRaisesRegex(ValueError, "entirely zero 4-bpp CLUT"):
            self.verify()

    def test_crop_stp_uses_sampled_index_not_unused_palette_entries(self):
        # Source face 0 uses page5 + CLUT31978. Force index1 opaque while
        # leaving a valid, but unreachable, STP entry at palette index15.
        for i in range(2):
            raw = bytearray(self.base.vrams[i])
            timeline_fixture.fixture.word(raw, 673, 499, 0x001f)
            timeline_fixture.fixture.word(raw, 687, 499, 0x8000)
            self.base.vrams[i] = bytes(raw)
        for probe in self.base.events[0]["texture"]["probes"]:
            probe["bgr555"] = 0x001f
        self.native_vrams = [self.base.vrams[1]] * 2
        self.save()
        for native_event in self.native_events[2:4]:
            native_event["semi"] = 1
        self.write_native()
        # Coarse CLUT inspection sees index15's STP, but it is absent in
        # the independently verified 16x16 texture crop.
        self.assertTrue(_ft4_palette_state(
            self.native_snapshots[2], self.native_events[2])[1])
        z, stp, opaque = _ft4_audited_crop_classes(
            self.base.events[0], self.native_snapshots[2],
            self.native_events[2])
        self.assertEqual(stp, 0)
        self.assertGreater(opaque, 0)
        report = self.verify()
        self.assertEqual(
            report["matched_ft4_draws_zero_delta_unknown_with_stp_blend_possible"], 0)
        self.assertEqual(report["matched_ft4_zero_delta_stp_candidate_abr0"], 0)
        self.assertFalse(report["native_dda_texel_sampling_path_observed"])

        # Change a non-probe texel from index1 to index15 within the 4-bpp
        # crop. Both source and native images change, probes stay truthful.
        # Page5 word for u=240..243 v=192 is (x=380,y=192).
        for i in range(2):
            raw = bytearray(self.base.vrams[i])
            timeline_fixture.fixture.word(raw, 380, 192, 0x1f11)
            self.base.vrams[i] = bytes(raw)
        self.native_vrams = [self.base.vrams[1]] * 2
        self.save()
        for native_event in self.native_events[2:4]:
            native_event["semi"] = 1
        self.write_native()
        report = self.verify()
        self.assertEqual(
            report["matched_ft4_draws_zero_delta_unknown_with_stp_blend_possible"], 1)
        self.assertGreater(report["matched_ft4_audited_crop_stp_texels"], 0)
        self.assertGreater(report["matched_ft4_audited_crop_opaque_texels"], 0)

    def test_windowed_crop_classifies_bgr555_zero_and_bit15(self):
        # Probe the *same* texture nibble with and without an E2 texture
        # window. No geometry or rasterized pixel path is asserted.
        raw = bytearray(1024 * 512 * 2)
        clut = 31978
        timeline_fixture.fixture.word(raw, 673, 499, 0x8000)
        timeline_fixture.fixture.word(raw, 674, 499, 0x001f)
        texture = {"u": 0, "v": 0, "w": 0, "h": 0}
        source_event = {"texture": texture}
        native_event = {"ft4": {"tpage": 5, "clut": clut},
                        "window": [0, 0, 0, 0]}
        # At the page origin, zero index->zero CLUT produces transparency.
        self.assertEqual(
            _ft4_audited_crop_classes(source_event, raw, native_event),
            (1, 0, 0))
        # Texture-window masks and offsets re-target this UV to u=8.
        timeline_fixture.fixture.word(raw, 322, 0, 0x2222)
        native_event["window"] = [1, 0, 1, 0]
        self.assertEqual(
            _ft4_audited_crop_classes(source_event, raw, native_event),
            (0, 0, 1))
        # Replacing texel index2 with 1 selects BGR555=0x8000 (STP),
        # which is NOT transparent 0000h.
        timeline_fixture.fixture.word(raw, 322, 0, 0x1111)
        self.assertEqual(
            _ft4_audited_crop_classes(source_event, raw, native_event),
            (0, 1, 0))

    def test_full_clut_requires_all_sixteen_zero_and_stp_abr_is_only_possible(self):
        raw = bytearray(1024 * 512 * 2)
        clut = 31978
        base = (((clut >> 6) & 511) * 1024 + (clut & 63) * 16) * 2
        event = {"ft4": {"tpage": 5, "clut": clut}, "semi": 0}
        self.assertEqual(_ft4_palette_state(raw, event), (True, False, 0))
        # One nonzero CLUT entry suffices to invalidate full transparency.
        raw[base + 2] = 0x00
        raw[base + 3] = 0x80
        self.assertEqual(_ft4_palette_state(raw, event), (False, False, 0))
        event["semi"] = 1
        for abr in range(4):
            event["ft4"]["tpage"] = 5 | (abr << 5)
            self.assertEqual(_ft4_palette_state(raw, event),
                             (False, True, abr))
        # 8-bpp mode cannot reuse the limited 16-entry CLUT proof.
        event["ft4"]["tpage"] = 5 | (1 << 7)
        self.assertEqual(_ft4_palette_state(raw, event),
                         (False, False, 0))

    def test_bgr555_bit15_is_not_transparency_and_stp_does_not_explain_zero(self):
        # Existing source face zero delta has an STP red CLUT entry, but no
        # automatic classification as blend-cancelled is permissible.
        for event in self.native_events[2:4]:
            event["semi"] = 1
        self.write_native()
        report = self.verify()
        self.assertEqual(
            report["matched_ft4_draws_zero_delta_unknown_with_stp_blend_possible"], 1)
        self.assertEqual(report["matched_ft4_zero_delta_stp_candidate_abr0"], 1)
        self.assertEqual(sum(
            report[f"matched_ft4_zero_delta_stp_candidate_abr{i}"]
            for i in range(4)), 1)
        self.assertEqual(report["matched_ft4_draws_zero_delta_cause_unknown"], 2)
        self.assertEqual(
            report["matched_ft4_draws_zero_delta_full_4bpp_clut_transparent"], 0)

        # 0x8000 is NOT a zero/transparent texel in the pinned PC raster.
        # Update the same CLUT entry and its independently captured probes.
        for i in range(2):
            raw = bytearray(self.base.vrams[i])
            timeline_fixture.fixture.word(raw, 673, 499, 0x8000)
            self.base.vrams[i] = bytes(raw)
        for probe in self.base.events[0]["texture"]["probes"]:
            probe["bgr555"] = 0x8000
        self.native_vrams = [self.base.vrams[1]] * 2
        self.save()
        for event in self.native_events[2:4]:
            event["semi"] = 1
        self.write_native()
        report = self.verify()
        self.assertEqual(
            report["matched_ft4_draws_zero_delta_full_4bpp_clut_transparent"], 0)
        self.assertEqual(
            report["matched_ft4_draws_zero_delta_unknown_with_stp_blend_possible"], 1)
        self.assertEqual(report["matched_ft4_zero_delta_stp_candidate_abr0"], 1)
        self.assertEqual(sum(
            report[f"matched_ft4_zero_delta_stp_candidate_abr{i}"]
            for i in range(4)), 1)

    def test_zero_draw_delta_has_separate_proven_clipping_and_unknown_causes(self):
        # Two source-matched native FT4s initially have no pixel delta.
        # With old captures we cannot attribute either zero to clipping.
        report = self.verify()
        self.assertEqual(report["matched_ft4_draws_without_vram_change"], 2)
        self.assertEqual(report["matched_ft4_draws_proven_no_coverage"], 0)
        self.assertEqual(report["matched_ft4_draws_zero_delta_cause_unknown"], 2)

        # Draw area is legal but geometry shifted thousands of pixels away:
        # the first packet cannot possibly write a pixel in this clip.
        for event in self.native_events[:2]:
            event["draw_env"] = [0, 0, 1024, 512, 1500, 1500]
        for event in self.native_events[2:]:
            event["draw_env"] = [0, 0, 1024, 512, 0, 0]
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draws_proven_no_coverage"], 1)
        self.assertEqual(report["matched_ft4_draws_zero_delta_cause_unknown"], 1)
        self.assertEqual(report["matched_ft4_draws_without_vram_change"], 2)

        # Write inside DRAWENV but far away from all shifted FT4 corners
        # contradicts the PC rasterizer even though the clip alone permits it.
        altered = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(altered, 0, 0, 0x801f)
        self.native_snapshots[1:4] = [bytes(altered)] * 3
        self.write_native()
        with self.assertRaisesRegex(ValueError, "geometry entirely outside"):
            self.verify()

    def test_zero_area_drawenv_proves_no_writes_without_guessing_alpha(self):
        for event in self.native_events[:2]:
            event["draw_env"] = [20, 20, 0, 128, 0, 0]
        self.write_native()
        self.assertEqual(
            self.verify()["matched_ft4_draws_proven_no_coverage"], 1)
        changed = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(changed, 20, 20, 0x7fff)
        self.native_snapshots[1:4] = [bytes(changed)] * 3
        self.write_native()
        with self.assertRaisesRegex(ValueError, "outside captured DRAWENV"):
            self.verify()

    def test_captured_ft4_drawenv_clip_proves_write_bounds(self):
        # Old captures remain valid, but cannot claim coverage proof.
        self.assertEqual(
            self.verify()["matched_ft4_draws_with_drawenv_clip_checked"], 0)
        # Align the first FT4's minimum vertex with the clip origin:
        # the subsequent in-clip pixel mutation is geometrically possible.
        xy = self.native_events[0]["ft4"]["xy"]
        ofs_x = -min(xy[::2])
        ofs_y = -min(xy[1::2])
        for i, event in enumerate(self.native_events):
            event["draw_env"] = ([0, 0, 4, 4, ofs_x, ofs_y]
                                  if i < 2 else
                                  [0, 0, 1024, 512, 0, 0])
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draws_with_drawenv_clip_checked"], 2)

        # Actual changes inside the captured draw clip pass, independently
        # of the shifted FT4 vertex coordinates.
        after = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(after, 2, 2, 0x801f)
        self.native_snapshots[1:4] = [bytes(after)] * 3
        self.write_native()
        report = self.verify()
        self.assertEqual(report["matched_ft4_draw_changed_vram_words"], 1)

        # Same event and valid SHA mapping, but a second pixel outside the
        # recorded draw clip is an impossible native PC FT4 delta.
        after = bytearray(self.native_snapshots[1])
        timeline_fixture.fixture.word(after, 5, 2, 0x7c00)
        self.native_snapshots[1:4] = [bytes(after)] * 3
        self.write_native()
        with self.assertRaisesRegex(ValueError, "outside captured DRAWENV"):
            self.verify()

    def test_optional_ft4_drawenv_invalid_or_pair_drift_rejected(self):
        self.native_events[0]["draw_env"] = [0, 0, 20, 20, 0, 0]
        self.write_native()
        with self.assertRaisesRegex(ValueError, "before/after metadata diverges"):
            self.verify()
        self.native_events[1]["draw_env"] = [0, 0, 20, 20, 0, 0]
        self.native_events[0]["draw_env"] = [0, 0, -1, 20, 0, 0]
        self.native_events[1]["draw_env"] = [0, 0, -1, 20, 0, 0]
        self.write_native()
        with self.assertRaisesRegex(ValueError, "DRAWENV"):
            self.verify()
        for event in self.native_events[:2]:
            event["draw_env"] = [0, 0, 0, 0, 0, 0]
        self.write_native()
        # A zero drawing-area is legal metadata, and does not itself make
        # an otherwise unchanged FT4 write pixels.
        self.assertEqual(
            self.verify()["matched_ft4_draws_with_drawenv_clip_checked"], 1)

    def test_changed_current_face_clut_detected_at_native_draw(self):
        damaged = bytearray(self.native_snapshots[0])
        timeline_fixture.fixture.word(damaged, 690, 499, 0x7c00)
        # Keep the native GPU draw sequence continuous so this failure
        # is a source/CLUT mismatch, not an unrelated missing GPU event.
        self.native_snapshots[:] = [bytes(damaged)] * 4
        self.write_native()
        with self.assertRaisesRegex(ValueError, "texture or CLUT words differ"):
            self.verify()

    def test_stale_pre_upload_native_vram_not_accepted(self):
        # A continuous native GPU trace cannot substitute an earlier
        # source-state image that lacks the second face's CLUT upload.
        self.native_snapshots[:] = [self.base.vrams[0]] * 4
        self.write_native()
        with self.assertRaisesRegex(ValueError, "texture or CLUT words differ"):
            self.verify()

    def test_unrelated_native_render_target_change_allowed(self):
        raw = bytearray(self.native_snapshots[0])
        timeline_fixture.fixture.word(raw, 0, 0, 0xffff)
        self.native_snapshots[:] = [bytes(raw)] * 4
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
