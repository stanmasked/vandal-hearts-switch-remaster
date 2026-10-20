"""Source-keyed native GPU VRAM before/after word-change overlap regressions.

Entire fixture is invented. The checker counts observable BGR555 changes,
not polygon coverage, pixel-correct blends, mask decisions or gameplay.
"""
import hashlib
import json
import struct
import unittest

import test_verify_map02_source_native_ot_order as ot_fixture
from tools.verify_map02_native_overdraw import verify_native_overdraw


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_word(raw, x, y, value):
    struct.pack_into("<H", raw, 2*(y*1024+x), value)


class NativeOverdrawTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ot_fixture.NativeOtOrderingTests(
            methodName="test_same_bucket_lifo_with_nonterrain_packets")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.source
        self.native = self.fixture.native
        self.base = self.fixture.base
        # Captured native packet order:
        #   index 0/1 unrelated draw,
        #   index 2/3 source face 1,
        #   index 4/5 source face 0.
        # The original FT4 screen bounds are both [20,70] × [20,70].
        original = self.base.bytes_before
        first = bytearray(original)
        write_word(first, 30, 30, 0x801f)
        write_word(first, 35, 35, 0x03e0)
        second = bytearray(first)
        write_word(second, 30, 30, 0x7c00)
        write_word(second, 40, 40, 0x001f)
        self.first = bytes(first)
        self.second = bytes(second)
        self.base.override_snapshots = {
            3: self.first,
            4: self.first,
            5: self.second,
        }
        self.save()

    def save(self):
        self.fixture.save()
        data = {
            "schema": "vh.map02.native-overdraw.v1",
            "source_frame": 411,
            "gpu_draw_frame": 12,
            "ot_order_manifest_sha256": sha(
                (self.source/"gpu-ot-order-join.json").read_bytes()),
            "native_events_sha256": sha(
                (self.native/"gpu-native-events.jsonl").read_bytes()),
        }
        (self.source/"gpu-native-overdraw.json").write_text(
            json.dumps(data,sort_keys=True))

    def test_repeated_changed_pixel_words_and_bit15_transitions(self):
        report=verify_native_overdraw(self.source,self.native)
        self.assertEqual(report["source_keyed_ft4_draw_pairs_checked"],2)
        self.assertEqual(report["all_native_gpu_draw_pairs"],3)
        self.assertTrue(report["consecutive_native_vram_boundaries_exact"])
        self.assertEqual(report["changed_vram_words_on_source_ft4_draws"],4)
        self.assertEqual(report["distinct_vram_words_changed_by_source_ft4"],3)
        self.assertEqual(report["vram_words_changed_by_two_or_more_source_ft4_draws"],1)
        self.assertEqual(report["changed_words_inside_ft4_screen_aabb_proxy"],4)
        self.assertEqual(report["changed_words_outside_ft4_screen_aabb_proxy"],0)
        self.assertEqual(
            report["words_changed_by_two_or_more_ft4_inside_screen_aabb_proxy"],1)
        self.assertEqual(report["bit15_unset_to_set_word_changes"],1)
        self.assertEqual(report["bit15_set_to_unset_word_changes"],1)
        self.assertEqual(report["source_ft4_pairs_without_observable_vram_changes"],0)
        for name in (
            "full_gpu_frame_authenticated",
            "intervening_write_then_restore_excluded",
            "ft4_actual_pixel_coverage_verified",
            "unchanged_pixel_proves_transparency_or_mask_reject",
            "stp_abr_mask_state_correctness_verified",
            "ps1_hardware_pixels_verified",
            "retail_gameplay_authenticated",
            "raw_game_bytes_emitted",
        ):
            self.assertFalse(report[name])
        public=json.dumps(report)
        for secret in ("31978","tpage","clut","vertices","perimeter_xy","0x801f"):
            self.assertNotIn(secret,public)

    def test_unchanged_draw_cannot_prove_transparency_or_gpu_mask(self):
        # Source face 0 processes an identical post-draw snapshot.
        self.base.override_snapshots[5]=self.first
        self.save()
        report=verify_native_overdraw(self.source,self.native)
        self.assertEqual(report["source_ft4_pairs_without_observable_vram_changes"],1)
        self.assertEqual(report["vram_words_changed_by_two_or_more_source_ft4_draws"],0)
        self.assertFalse(report["unchanged_pixel_proves_transparency_or_mask_reject"])

    def test_changed_unrelated_screen_location_is_counted_not_misattributed(self):
        outside=bytearray(self.first)
        write_word(outside,900,400,0x7fff)
        self.base.override_snapshots[3]=bytes(outside)
        self.base.override_snapshots[4]=bytes(outside)
        last=bytearray(outside)
        write_word(last,30,30,0x7c00)
        write_word(last,40,40,0x001f)
        self.base.override_snapshots[5]=bytes(last)
        self.save()
        report=verify_native_overdraw(self.source,self.native)
        self.assertEqual(report["changed_words_outside_ft4_screen_aabb_proxy"],1)
        self.assertEqual(report["vram_words_changed_by_two_or_more_source_ft4_draws"],1)
        self.assertFalse(report["ft4_actual_pixel_coverage_verified"])

    def test_intervening_unaccounted_write_gap_rejected(self):
        pre=bytearray(self.first)
        write_word(pre,31,31,0x7fff)
        self.base.override_snapshots[4]=bytes(pre)
        self.save()
        # The shared 1-MiB native GPU capture validator rejects the
        # unobserved transition before the source-keyed overdraw join.
        with self.assertRaisesRegex(
            ValueError,"native GPU VRAM continuity broken between event pairs"
        ):
            verify_native_overdraw(self.source,self.native)

    def test_unmatched_primitive_does_not_create_spurious_source_overdraw(self):
        # An unrelated DrawOTag primitive changes a word first.
        first_other=bytearray(self.base.bytes_before)
        write_word(first_other,30,30,0x03e0)
        first_source=bytearray(first_other)
        write_word(first_source,30,30,0x801f)
        write_word(first_source,35,35,0x03e0)
        second_source=bytearray(first_source)
        write_word(second_source,30,30,0x7c00)
        write_word(second_source,40,40,0x001f)
        self.base.override_snapshots={
            1:bytes(first_other),2:bytes(first_other),
            3:bytes(first_source),4:bytes(first_source),
            5:bytes(second_source),
        }
        self.save()
        report=verify_native_overdraw(self.source,self.native)
        self.assertEqual(report["source_keyed_ft4_draw_pairs_checked"],2)
        self.assertEqual(report["vram_words_changed_by_two_or_more_source_ft4_draws"],1)
        self.assertEqual(report["all_native_gpu_draw_pairs"],3)

    def test_tampered_manifest_and_short_snapshot_rejected(self):
        mpath=self.source/"gpu-native-overdraw.json"
        m=json.loads(mpath.read_text())
        m["native_events_sha256"]="0"*64
        mpath.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,"native GPU event log: SHA-256 mismatch"):
            verify_native_overdraw(self.source,self.native)
        self.save()
        (self.native/"gpu-0005-vram.bin").write_bytes(b"\0\0")
        with self.assertRaisesRegex(ValueError,"wrong file size"):
            verify_native_overdraw(self.source,self.native)

    def test_reversed_source_ot_order_rejected_before_pixel_analysis(self):
        self.base.entries[1],self.base.entries[2] = (
            self.base.entries[2],self.base.entries[1])
        self.base.override_snapshots.clear()
        self.save()
        with self.assertRaisesRegex(ValueError,"violates.*OT depth/LIFO"):
            verify_native_overdraw(self.source,self.native)


if __name__=="__main__":
    unittest.main()
