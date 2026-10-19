"""Synthetic checker for bounded native GPU command/VRAM capture files."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.verify_map02_native_gpu_capture import verify_capture, VRAM_BYTES

class NativeGpuCaptureValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.data=bytearray(VRAM_BYTES)
        self.pre=self.data[:]
        # ClearImage RGB [160,0,0] packs as 0x0014, not 0x001f.
        self.data[0]=160>>3
        self.data[1]=0
        self.mid=self.data[:]
        self.data[2]=255
        self.data[3]=127
        self.post=self.data[:]
        self.events=[
          self.make(0,"before","clear","",rect=[0,0,1,1]),
          self.make(1,"after","clear","",rect=[0,0,1,1]),
          self.make(2,"before","draw","",ft4={
            "tpage":5,"clut":31978,"xy":[0,0,16,0,0,16,16,16],
            "uv":[0,0,15,0,0,15,15,15]}),
          self.make(3,"after","draw","",ft4={
            "tpage":5,"clut":31978,"xy":[0,0,16,0,0,16,16,16],
            "uv":[0,0,15,0,0,15,15,15]})
        ]
        self.save()

    def make(self,i,phase,op,upload,rect=None,ft4=None):
        return {
            "stage":"native_vram","step":i,"frame":12 if op=="draw" else 11,
            "phase":phase,"operation":op,
            "snapshot":f"gpu-{i:04d}-vram.bin",
            "rect":rect,"dest":[0,0],"rgb":[160,0,0],
            "primitive_type":2 if op=="draw" else 0,
            "semi":0,"window":[0,0,0,0],"draw_mode":[5,0,0],
            "upload":upload,"ft4":ft4,
        }
    def save(self):
        for i,payload in enumerate((self.pre,self.mid,self.mid,self.post)):
            (self.root/f"gpu-{i:04d}-vram.bin").write_bytes(payload)
        (self.root/"gpu-native-events.jsonl").write_text(
            "".join(json.dumps(e,sort_keys=True)+"\n" for e in self.events))

    def test_two_native_pairs_and_hashes(self):
        result=verify_capture(self.root,target_frame=12)
        self.assertEqual(result["native_gpu_pairs_verified"],2)
        self.assertEqual(result["draw_otag_primitive_pairs"],1)
        self.assertEqual(result["clear_image_pairs"],1)
        self.assertEqual(result["clear_pairs_with_verified_vram_effect"],1)
        self.assertEqual(result["changed_native_draw_vram_words"],1)
        self.assertEqual(result["changed_transfer_vram_words"],1)
        self.assertIsNone(result["upload_payload_sha256_list_sha256"])
        self.assertEqual(result["load_pairs_with_verified_payload"],0)
        self.assertEqual(result["load_pairs_without_payload"],0)
        for flag in ("real_gameplay_authenticated","gpu_write_stream_complete",
                     "source_keyed_map02_faces_matched","ps1_hardware_pixels_verified",
                     "game_bytes_in_report"):
            self.assertFalse(result[flag])
        summary=json.dumps(result)
        self.assertNotIn("31978",summary)
        self.assertNotIn("xy",summary)

    def test_main_terminal_receipt_api_preserves_strict_pr_vram_checks(self):
        # Reconciling main's hook accounting must not replace PR #55's
        # independent VRAM transfer and DrawOTag validation.
        from tools.verify_map02_native_gpu_capture import (
            STATUS, verify_capture_receipt,
        )
        baseline = verify_capture(self.root, target_frame=12)
        self.assertFalse(baseline["capture_receipt_supplied"])
        self.assertFalse(baseline["capture_window_closed_without_detected_loss"])
        self.assertEqual(baseline["clear_pairs_with_verified_vram_effect"], 1)
        receipt = {
            "schema": "vh.map02.native-capture-status.v1",
            "gpu_draw_frame": 12,
            "observed_hooks": 4,
            "before_hooks": 2,
            "after_hooks": 2,
            "draw_before_hooks": 1,
            "transfer_before_hooks": 1,
            "indexed_hooks": 4,
            "written_hooks": 4,
            "limit_reached": False,
            "walk_finished": True,
            "hooks_balanced": True,
            "observed_window_closed_without_detected_loss": True,
        }
        path = self.root / STATUS
        path.write_text(json.dumps(receipt), encoding="utf-8")
        checked = verify_capture_receipt(
            self.root, target_frame=12, events=self.events)
        self.assertTrue(checked["capture_receipt_supplied"])
        self.assertFalse(checked["full_original_gameplay_frame_proven"])
        validated = verify_capture(self.root, target_frame=12)
        self.assertTrue(validated["capture_window_closed_without_detected_loss"])
        self.assertFalse(validated["gpu_write_stream_complete"])
        self.assertEqual(validated["changed_transfer_vram_words"], 1)
        self.assertEqual(validated["clear_pairs_with_verified_vram_effect"], 1)
        self.assertFalse(validated["real_gameplay_authenticated"])

        for name, changed in (
            ("invented-hook", {"observed_hooks": 5}),
            ("lost-index", {"indexed_hooks": 3}),
            ("false-balanced", {"hooks_balanced": False}),
            ("unfinished-walk", {"walk_finished": False}),
            ("truncation-cap", {"limit_reached": True}),
            ("false-closed-window",
             {"observed_window_closed_without_detected_loss": False}),
            ("wrong-frame", {"gpu_draw_frame": 13}),
            ("bad-schema", {"schema": "invented"}),
        ):
            with self.subTest(name=name):
                path.write_text(json.dumps({**receipt, **changed}),
                                encoding="utf-8")
                with self.assertRaises(ValueError):
                    verify_capture(self.root, target_frame=12)
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.events[0]["rgb"][0] = 248
        self.events[1]["rgb"][0] = 248
        self.save()
        with self.assertRaisesRegex(ValueError,
                                    "ClearImage post-VRAM"):
            verify_capture(self.root, target_frame=12)

    def test_missing_drawenv_on_both_phases_is_legacy_not_corruption(self):
        # Historic native logs have no DRAWENV, but their original
        # source-keyed VRAM and FT4 replay must still validate. A mixed
        # before/after schema, however, is never a valid single GPU event.
        self.assertTrue(all("draw_env" not in event for event in self.events))
        report = verify_capture(self.root, target_frame=12)
        self.assertEqual(report["native_gpu_pairs_verified"], 2)
        self.assertFalse(report["real_gameplay_authenticated"])
        self.assertFalse(report["ps1_hardware_pixels_verified"])

        clip = [0, 0, 1024, 512, 0, 0]
        self.events[2]["draw_env"] = clip[:]
        self.save()
        with self.assertRaisesRegex(ValueError,
                                    r"before/after metadata diverges \\(draw_env\\)"):
            verify_capture(self.root, target_frame=12)

        self.events[3]["draw_env"] = clip[:]
        self.save()
        self.assertEqual(verify_capture(self.root, target_frame=12)[
            "draw_otag_primitive_pairs"], 1)

        del self.events[2]["draw_env"]
        self.save()
        with self.assertRaisesRegex(ValueError,
                                    r"before/after metadata diverges \\(draw_env\\)"):
            verify_capture(self.root, target_frame=12)

    def test_main_drawenv_metadata_checked_without_dropping_ft4_checks(self):
        for event in self.events:
            event["draw_env"] = [0, 0, 1024, 512, -30, 25]
        self.save()
        self.assertEqual(verify_capture(self.root, target_frame=12)[
            "draw_otag_primitive_pairs"], 1)
        self.events[3]["draw_env"][4] = -31
        self.save()
        with self.assertRaisesRegex(ValueError,
                                    "before/after metadata diverges"):
            verify_capture(self.root, target_frame=12)
        self.events[3]["draw_env"][4] = -30
        self.events[2]["draw_env"][2] = -1
        self.save()
        with self.assertRaisesRegex(ValueError, "DRAWENV"):
            verify_capture(self.root, target_frame=12)
        self.events[2]["draw_env"] = [0, 0, 1024, 512, -30, 25]
        del self.events[3]["draw_env"]
        self.save()
        with self.assertRaisesRegex(ValueError,
                                    "before/after metadata diverges"):
            verify_capture(self.root, target_frame=12)

    def test_adjacent_draw_pairs_have_exact_vram_continuity(self):
        # The first captured draw may start with changes from an
        # unobserved preceding frame. Two draws within target DrawOTag
        # cannot have an unrecorded intervening native VRAM write.
        extra = [dict(self.events[2]), dict(self.events[3])]
        for step, event in enumerate(extra, start=4):
            event["step"] = step
            event["snapshot"] = f"gpu-{step:04d}-vram.bin"
        self.events.extend(extra)
        self.save()
        (self.root / "gpu-0004-vram.bin").write_bytes(self.post)
        (self.root / "gpu-0005-vram.bin").write_bytes(self.post)
        report = verify_capture(self.root, target_frame=12)
        self.assertEqual(report["draw_otag_primitive_pairs"], 2)
        self.assertEqual(report["draw_boundary_vram_checks"], 1)
        self.assertEqual(report["draw_boundary_gpu_state_checks"], 1)
        # Keep the local before/after pair coherent; only the boundary
        # between successive recorded DrawOTag primitives is forged.
        mutated = bytearray(self.post)
        mutated[8:10] = b"\x77\x00"
        (self.root / "gpu-0004-vram.bin").write_bytes(mutated)
        (self.root / "gpu-0005-vram.bin").write_bytes(mutated)
        with self.assertRaisesRegex(ValueError, "discontinuous VRAM"):
            verify_capture(self.root, target_frame=12)

    def test_preframe_transfer_boundary_is_not_claimed_continuous(self):
        # A whole *unrecorded* preceding DrawOTag may occur after the
        # capture's last preframe transfer, before the target frame.
        (self.root / "gpu-0002-vram.bin").write_bytes(self.post)
        (self.root / "gpu-0003-vram.bin").write_bytes(self.post)
        report = verify_capture(self.root, target_frame=12)
        self.assertEqual(report["draw_boundary_vram_checks"], 0)

    def test_non_dr_mode_draw_must_preserve_gpu_state(self):
        self.events[3]["draw_mode"] = [9, 0, 0]
        self.save()
        with self.assertRaisesRegex(ValueError, "non-DR_MODE"):
            verify_capture(self.root, target_frame=12)
        self.events[3]["draw_mode"] = [5, 0, 0]
        self.events[3]["window"] = [1, 0, 0, 0]
        self.save()
        with self.assertRaisesRegex(ValueError, "non-DR_MODE"):
            verify_capture(self.root, target_frame=12)

    def test_dr_mode_state_transition_to_following_ft4(self):
        self.events = [
            self.make(0, "before", "draw", ""),
            self.make(1, "after", "draw", ""),
            self.make(2, "before", "draw", "", ft4=dict(self.events[2]["ft4"])),
            self.make(3, "after", "draw", "", ft4=dict(self.events[3]["ft4"])),
        ]
        for event in self.events[:2]:
            event["primitive_type"] = 5  # PC_GPU_PRIM_DR_MODE
        self.events[1]["draw_mode"] = [11, 1, 1]
        self.events[1]["window"] = [2, 3, 4, 5]
        for event in self.events[2:]:
            event["draw_mode"] = [11, 1, 1]
            event["window"] = [2, 3, 4, 5]
        self.save()
        for step in range(4):
            (self.root / f"gpu-{step:04d}-vram.bin").write_bytes(self.pre)
        result = verify_capture(self.root, target_frame=12)
        self.assertEqual(result["draw_boundary_vram_checks"], 1)
        self.assertEqual(result["draw_boundary_gpu_state_checks"], 1)
        self.events[2]["window"] = [3, 3, 4, 5]
        self.save()
        # save() regenerates the default clear/draw VRAM snapshots.
        # DR_MODE does not write VRAM; restore the deliberately uniform
        # snapshots so this mutation isolates an illegal GPU state gap,
        # not an unrelated DR_MODE VRAM-write violation.
        for step in range(4):
            (self.root / f"gpu-{step:04d}-vram.bin").write_bytes(self.pre)
        with self.assertRaisesRegex(ValueError, "discontinuous GPU state"):
            verify_capture(self.root, target_frame=12)

    def test_dr_mode_cannot_write_vram_even_if_next_ft4_sees_same_bytes(self):
        # Source-pinned PC_GPU_PRIM_DR_MODE only changes persistent GPU
        # state. Forge an internally continuous stream where it also
        # changes a VRAM word; the next FT4 starts from that same value.
        packet = dict(self.events[2]["ft4"])
        self.events = [
            self.make(0, "before", "draw", ""),
            self.make(1, "after", "draw", ""),
            self.make(2, "before", "draw", "", ft4=packet),
            self.make(3, "after", "draw", "", ft4=packet),
        ]
        for event in self.events[:2]:
            event["primitive_type"] = 5
        for event in self.events[1:]:
            event["draw_mode"] = [11, 1, 1]
            event["window"] = [2, 3, 4, 5]
        self.save()
        forged = bytearray(self.pre)
        forged[2:4] = b"\x01\x00"
        for step in range(4):
            raw = self.pre if step == 0 else forged
            (self.root / f"gpu-{step:04d}-vram.bin").write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "DR_MODE.*modified VRAM"):
            verify_capture(self.root, target_frame=12)

    def test_pinned_ft4_type_requires_real_packet_metadata(self):
        # Source C supplies an FT4 pointer iff the DrawOTag type is 2.
        self.events[2]["ft4"] = None
        self.save()
        with self.assertRaisesRegex(ValueError, "FT4 payload presence"):
            verify_capture(self.root, target_frame=12)
        self.events[2]["ft4"] = dict(self.events[3]["ft4"])
        self.events[2]["primitive_type"] = 4
        self.events[3]["primitive_type"] = 4
        self.save()
        with self.assertRaisesRegex(ValueError, "FT4 payload presence"):
            verify_capture(self.root, target_frame=12)

    def test_gpu_transfer_type_must_be_zero(self):
        # Generated original transfer hooks explicitly pass type=0.
        self.events[0]["primitive_type"] = 2
        self.events[1]["primitive_type"] = 2
        self.save()
        with self.assertRaisesRegex(ValueError, "native transfer cannot claim"):
            verify_capture(self.root, target_frame=12)

    def test_mixed_frames_wrong_snapshot_and_missing_pair(self):
        self.events[2]["frame"]=11
        self.save()
        with self.assertRaisesRegex(ValueError,"different native GPU frame"):
            verify_capture(self.root,target_frame=12)
        self.events[2]["frame"]=12
        self.events[3]["snapshot"]="gpu-0002-vram.bin"
        self.save()
        with self.assertRaisesRegex(ValueError,"snapshot name/index"):
            verify_capture(self.root,target_frame=12)
        self.events[3]["snapshot"]="gpu-0003-vram.bin"
        self.events.pop()
        self.save()
        with self.assertRaisesRegex(ValueError,"incomplete"):
            verify_capture(self.root,target_frame=12)

    def test_native_gpu_jsonl_requires_canonical_complete_binary_records(self):
        journal = self.root / "gpu-native-events.jsonl"
        original = journal.read_bytes()
        self.assertTrue(original.endswith(b"\n"))
        for corrupt in (original.rstrip(b"\n"),
                        original.replace(b"\n", b"\r\n"),
                        original.replace(b"\n", b"\x00\n", 1)):
            with self.subTest(tail=repr(corrupt[-12:])):
                journal.write_bytes(corrupt)
                with self.assertRaisesRegex(ValueError, "noncanonical"):
                    verify_capture(self.root, target_frame=12)
        journal.write_bytes(original)
        self.assertEqual(verify_capture(self.root, target_frame=12)[
            "native_gpu_pairs_verified"], 2)

    def test_transfer_after_target_draw_is_not_a_valid_native_capture(self):
        # The original capture probes transfers at drawFrame + 1, but
        # primitives at drawFrame. Reversing the pairs is impossible for
        # the monotonically progressing target DrawOTag frame.
        self.events = self.events[2:4] + self.events[0:2]
        for step, event in enumerate(self.events):
            event["step"] = step
            event["snapshot"] = f"gpu-{step:04d}-vram.bin"
        self.save()
        with self.assertRaisesRegex(ValueError, "transfer appears after"):
            verify_capture(self.root, target_frame=12)

    def test_missing_snapshot_symlink_invalid_size(self):
        path=self.root/"gpu-0003-vram.bin"
        path.unlink()
        with self.assertRaisesRegex(ValueError,"missing, symlinked"):
            verify_capture(self.root,target_frame=12)
        path.symlink_to(self.root/"gpu-0002-vram.bin")
        with self.assertRaisesRegex(ValueError,"missing, symlinked"):
            verify_capture(self.root,target_frame=12)
        path.unlink()
        path.write_bytes(b"\0\0")
        with self.assertRaisesRegex(ValueError,"wrong file size"):
            verify_capture(self.root,target_frame=12)

    def test_source_key_not_fabricated_and_invalid_packet_rejected(self):
        self.events[3]["ft4"]["xy"][0]=2
        self.save()
        with self.assertRaisesRegex(ValueError,"before/after metadata diverges"):
            verify_capture(self.root,target_frame=12)
        self.events[3]["ft4"]["xy"][0]=0
        self.events[2]["window"]=[99,0,0,0]
        self.save()
        with self.assertRaisesRegex(ValueError,"expected integer"):
            verify_capture(self.root,target_frame=12)

    def move_fixture(self, rect, dest, before, after):
        self.events = [
            self.make(0, "before", "move", "", rect=rect),
            self.make(1, "after", "move", "", rect=rect),
        ]
        for event in self.events:
            event["dest"] = dest[:]
        self.save()
        (self.root / "gpu-0000-vram.bin").write_bytes(before)
        (self.root / "gpu-0001-vram.bin").write_bytes(after)
        return verify_capture(self.root, target_frame=12)

    def clear_fixture(self, rect, rgb, before, after):
        self.events = [
            self.make(0, "before", "clear", "", rect=rect),
            self.make(1, "after", "clear", "", rect=rect),
        ]
        for event in self.events:
            event["rgb"] = list(rgb)
        self.save()
        (self.root / "gpu-0000-vram.bin").write_bytes(before)
        (self.root / "gpu-0001-vram.bin").write_bytes(after)
        return verify_capture(self.root, target_frame=12)

    def test_clearimage_raw_bgr555_truncation_no_mask_bit(self):
        before = bytearray(VRAM_BYTES)
        before[:6] = b"\xff\xff" * 3
        after = bytearray(before)
        # r=255,g=127,b=8 => packed 0x05ff (bit15 remains clear).
        packed = ((8 >> 3) << 10) | ((127 >> 3) << 5) | (255 >> 3)
        after[:4] = packed.to_bytes(2, "little") * 2
        result = self.clear_fixture([0, 0, 2, 1], [255, 127, 8],
                                    before, after)
        self.assertEqual(result["clear_image_pairs"], 1)
        self.assertEqual(result["clear_pairs_with_verified_vram_effect"], 1)
        after[:4] = b"\xff\xff" * 2
        (self.root / "gpu-0001-vram.bin").write_bytes(after)
        with self.assertRaisesRegex(ValueError, "ClearImage post-VRAM differs"):
            verify_capture(self.root, target_frame=12)

    def test_clearimage_negative_origin_clips_and_checks_outside(self):
        before = bytearray(VRAM_BYTES)
        before[:8] = b"\x11\x80" * 4
        after = bytearray(before)
        # [-1,-1,3,3] intersects at (0..1, 0..1); bit15 cleared.
        for y in (0, 1):
            start = y * 1024 * 2
            after[start:start+4] = b"\x1f\x00" * 2
        report = self.clear_fixture([-1,-1,3,3], [248,0,0], before, after)
        self.assertEqual(report["clear_pairs_with_verified_vram_effect"], 1)
        after[-2:] = b"\x42\x00"
        (self.root / "gpu-0001-vram.bin").write_bytes(after)
        with self.assertRaisesRegex(ValueError, "ClearImage post-VRAM differs"):
            verify_capture(self.root, target_frame=12)

    def test_clearimage_offscreen_and_zero_dimensions_do_not_change_vram(self):
        before = bytearray(VRAM_BYTES)
        before[:2] = b"\x99\x7f"
        for rect in ([32000, 31000, 32767, 32767],
                     [0, 0, 0, 3], [0, 0, 3, -2]):
            with self.subTest(rect=rect):
                result = self.clear_fixture(rect, [255,255,255],
                                            before, before)
                self.assertEqual(result["clear_pairs_with_verified_vram_effect"], 1)

    def test_clearimage_bottom_right_clipping_and_wrong_rgb(self):
        before = bytearray(VRAM_BYTES)
        after = bytearray(before)
        # (1023,511) is the only on-screen word for 3x3 RECT.
        packed = ((255 >> 3) << 10) | ((128 >> 3) << 5) | (8 >> 3)
        after[-2:] = packed.to_bytes(2, "little")
        self.clear_fixture([1023,511,3,3], [8,128,255], before, after)
        # Modify only JSON metadata; retain exactly the same VRAM files.
        self.events[0]["rgb"] = [8,129,255]
        self.events[1]["rgb"] = [8,129,255]
        journal=self.root/"gpu-native-events.jsonl"
        journal.write_text("".join(json.dumps(e,sort_keys=True)+"\n"
                                   for e in self.events))
        self.assertEqual(verify_capture(self.root, target_frame=12)[
            "clear_pairs_with_verified_vram_effect"], 1)
        # A change crossing the 5-bit truncation boundary must fail.
        self.events[0]["rgb"] = [8,136,255]
        self.events[1]["rgb"] = [8,136,255]
        journal.write_text("".join(json.dumps(e,sort_keys=True)+"\n"
                                   for e in self.events))
        with self.assertRaisesRegex(ValueError, "ClearImage post-VRAM differs"):
            verify_capture(self.root, target_frame=12)

    def test_moveimage_forward_horizontal_overlap_not_memmove(self):
        before = bytearray(VRAM_BYTES)
        before[:8] = b"\x11\x00\x22\x00\x33\x00\x44\x00"
        after = bytearray(before)
        after[:8] = b"\x11\x00" * 4
        result = self.move_fixture([0, 0, 3, 1], [1, 0], before, after)
        self.assertEqual(result["move_image_pairs"], 1)
        self.assertEqual(result["move_pairs_with_verified_vram_effect"], 1)
        self.assertEqual(result["changed_transfer_vram_words"], 3)
        wrong_memmove = bytearray(before)
        wrong_memmove[:8] = b"\x11\x00\x11\x00\x22\x00\x33\x00"
        (self.root / "gpu-0001-vram.bin").write_bytes(wrong_memmove)
        with self.assertRaisesRegex(ValueError, "MoveImage post-VRAM differs"):
            verify_capture(self.root, target_frame=12)

    def test_moveimage_downward_overlap_reads_mutable_rows(self):
        before = bytearray(VRAM_BYTES)
        for y, value in enumerate((1, 2, 3, 4)):
            before[y*1024*2:y*1024*2+2] = bytes((value, 0))
        after = bytearray(before)
        for y in (1, 2, 3):
            after[y*1024*2:y*1024*2+2] = b"\x01\x00"
        result = self.move_fixture([0, 0, 1, 3], [0, 1], before, after)
        self.assertEqual(result["move_pairs_with_verified_vram_effect"], 1)

    def test_moveimage_negative_source_and_destination_are_clipped(self):
        before = bytearray(VRAM_BYTES)
        before[:6] = b"\x11\x00\x22\x00\x33\x00"
        after = bytearray(before)
        after[:6] = b"\x11\x00" * 3
        self.assertEqual(self.move_fixture([-1, 0, 3, 1], [0, 0],
                                            before, after)[
            "move_pairs_with_verified_vram_effect"], 1)
        # Nonoverlapping x/y bounds: only one word at the bottom-right
        # destination exists. Every other byte must stay unchanged.
        rect = [0, 0, 2, 2]
        after = bytearray(before)
        after[-2:] = b"\x11\x00"
        self.assertEqual(self.move_fixture(rect, [1023, 511],
                                            before, after)[
            "move_pairs_with_verified_vram_effect"], 1)
        after[-4:-2] = b"\x42\x00"
        (self.root / "gpu-0001-vram.bin").write_bytes(after)
        with self.assertRaisesRegex(ValueError, "MoveImage post-VRAM differs"):
            verify_capture(self.root, target_frame=12)

    def test_moveimage_huge_offscreen_or_negative_rect_is_noop(self):
        before = bytearray(VRAM_BYTES)
        before[:2] = b"\x10\x01"
        self.assertEqual(self.move_fixture([32000, 31000, 32767, 32767],
                                            [32000, 31000], before, before)[
            "move_pairs_with_verified_vram_effect"], 1)
        self.assertEqual(self.move_fixture([0, 0, -2, 2],
                                            [10, 10], before, before)[
            "move_pairs_with_verified_vram_effect"], 1)

    def test_load_image_payload_name_and_length(self):
        payload=b"\x1f\x00"
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,1,1])
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=[0,0,1,1])
        self.save()
        correct_post=bytearray(self.pre)
        correct_post[:2]=bytes((31,0))
        (self.root/"gpu-0001-vram.bin").write_bytes(correct_post)
        (self.root/"gpu-0001-upload.bin").write_bytes(payload)
        first=verify_capture(self.root,target_frame=12)
        self.assertEqual(first["load_image_pairs"],1)
        self.assertEqual(first["load_pairs_with_verified_payload"],1)
        self.assertEqual(first["load_pairs_with_verified_vram_effect"],1)
        self.assertEqual(first["load_pairs_without_payload"],0)
        self.assertEqual(first["upload_payload_sha256_list_sha256"],
                         hashlib.sha256(hashlib.sha256(payload).hexdigest().encode("ascii")).hexdigest())
        (self.root/"gpu-0001-upload.bin").write_bytes(b"\x00")
        with self.assertRaisesRegex(ValueError,"wrong file size"):
            verify_capture(self.root,target_frame=12)

    def test_second_capture_window_loadimage_uses_local_upload_step(self):
        # A real two-window recorder uses global event indices 64/65,
        # but the second journal restarts at local steps 0/1. It must
        # name both snapshots and the AFTER upload using the local index.
        self.events = [
            self.make(0, "before", "load", "", rect=[0,0,1,1]),
            self.make(1, "after", "load", "gpu-0001-upload.bin",
                      rect=[0,0,1,1]),
        ]
        self.save()
        corrected = bytearray(self.pre)
        corrected[:2] = b"\x1f\x00"
        (self.root/"gpu-0001-vram.bin").write_bytes(corrected)
        (self.root/"gpu-0001-upload.bin").write_bytes(b"\x1f\x00")
        window = self.root/"window-001"
        window.mkdir(mode=0o700)
        for name in ("gpu-0000-vram.bin", "gpu-0001-vram.bin",
                     "gpu-0001-upload.bin", "gpu-native-events.jsonl"):
            (window/name).write_bytes((self.root/name).read_bytes())
        result = verify_capture(window, target_frame=12)
        self.assertEqual(result["native_gpu_pairs_verified"], 1)
        self.assertEqual(result["load_pairs_with_verified_payload"], 1)
        self.assertEqual(result["load_pairs_with_verified_vram_effect"], 1)
        self.assertFalse(result["real_gameplay_authenticated"])

        # Old buggy recorder named the upload by global step 65,
        # but falsely declared an otherwise valid local step 1.
        self.events[1]["upload"] = "gpu-0065-upload.bin"
        (window/"gpu-0065-upload.bin").write_bytes(b"\x1f\x00")
        (window/"gpu-native-events.jsonl").write_text(
            "".join(json.dumps(e,sort_keys=True)+"\n"
                    for e in self.events), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected upload filename"):
            verify_capture(window, target_frame=12)

    def test_same_length_upload_mutation_changes_payload_fingerprint(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,1,1])
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=[0,0,1,1])
        self.save()
        correct_post=bytearray(self.pre)
        correct_post[:2]=bytes((31,0))
        (self.root/"gpu-0001-vram.bin").write_bytes(correct_post)
        path=self.root/"gpu-0001-upload.bin"
        path.write_bytes(b"\x1f\x00")
        first=verify_capture(self.root,target_frame=12)
        path.write_bytes(b"\x1e\x00")  # same byte length, but stale post-VRAM
        with self.assertRaisesRegex(ValueError, "post-VRAM differs"):
            verify_capture(self.root,target_frame=12)
        # Once the native AFTER snapshot reflects the changed source,
        # the updated content is valid but carries a different fingerprint.
        corrected=bytearray((self.root/"gpu-0001-vram.bin").read_bytes())
        corrected[:2]=b"\x1e\x00"
        (self.root/"gpu-0001-vram.bin").write_bytes(corrected)
        second=verify_capture(self.root,target_frame=12)
        self.assertNotEqual(first["upload_payload_sha256_list_sha256"],
                            second["upload_payload_sha256_list_sha256"])
        self.assertEqual(first["native_gpu_events_sha256"],
                         second["native_gpu_events_sha256"])
        self.assertNotEqual(first["vram_snapshot_sha256_list_sha256"],
                            second["vram_snapshot_sha256_list_sha256"])

    def test_unrecorded_load_payload_is_explicitly_unobserved(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,256,256])
        self.events[1]=self.make(1,"after","load","",rect=[0,0,256,256])
        self.save()
        result=verify_capture(self.root,target_frame=12)
        self.assertEqual(result["load_image_pairs"],1)
        self.assertEqual(result["load_pairs_without_payload"],1)
        self.assertEqual(result["load_pairs_with_verified_payload"],0)
        self.assertIsNone(result["upload_payload_sha256_list_sha256"])

    def test_bounded_loadimage_missing_payload_is_not_merely_unobserved(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,1,1])
        self.events[1]=self.make(1,"after","load","",rect=[0,0,1,1])
        self.save()
        with self.assertRaisesRegex(ValueError,"missing mandatory upload"):
            verify_capture(self.root,target_frame=12)

    def test_source_hook_dimension_bounds_are_not_just_area_bounds(self):
        # 129*1 is < 16384 words but C deliberately does not
        # capture it: its width exceeds the 128-word dimension cap.
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,129,1])
        self.events[1]=self.make(1,"after","load","",rect=[0,0,129,1])
        self.save()
        result=verify_capture(self.root,target_frame=12)
        self.assertEqual(result["load_pairs_without_payload"],1)
        self.assertIsNone(result["upload_payload_sha256_list_sha256"])
        # A fabricated payload name cannot turn omitted source data
        # into evidence of a real C recorder upload.
        self.events[1]["upload"]="gpu-0001-upload.bin"
        self.save()
        (self.root/"gpu-0001-upload.bin").write_bytes(bytes(258))
        with self.assertRaisesRegex(ValueError,"out-of-range LoadImage"):
            verify_capture(self.root,target_frame=12)

    def test_maximum_bounded_loadimage_payload_is_accepted(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,128,128])
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=[0,0,128,128])
        self.save()
        correct_post=bytearray(self.pre)
        correct_post[:2]=bytes((31,0))
        (self.root/"gpu-0001-vram.bin").write_bytes(correct_post)
        (self.root/"gpu-0001-upload.bin").write_bytes(
            b"\x1f\x00" + bytes(128*128*2-2)
        )
        result=verify_capture(self.root,target_frame=12)
        self.assertEqual(result["load_pairs_with_verified_payload"],1)
        self.assertEqual(result["load_pairs_without_payload"],0)

    def test_bounded_loadimage_checks_every_pixel_and_unchanged_outside(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[1,1,2,2])
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=[1,1,2,2])
        self.save()
        payload=b"\x11\x00\x22\x00\x33\x00\x44\x00"
        (self.root/"gpu-0001-upload.bin").write_bytes(payload)
        before=self.pre
        after=bytearray(before)
        for row in range(2):
            start=((1+row)*1024+1)*2
            after[start:start+4]=payload[row*4:row*4+4]
        (self.root/"gpu-0001-vram.bin").write_bytes(after)
        self.assertEqual(verify_capture(self.root,target_frame=12)[
            "load_pairs_with_verified_vram_effect"],1)
        # A corrupted word far outside the load footprint must fail too.
        after[-2:]=b"\x40\x00"
        (self.root/"gpu-0001-vram.bin").write_bytes(after)
        with self.assertRaisesRegex(ValueError,"post-VRAM differs"):
            verify_capture(self.root,target_frame=12)

    def test_negative_origin_clips_source_offsets_exactly(self):
        self.events=self.events[:2]
        rect=[-1,-1,2,2]
        self.events[0]=self.make(0,"before","load","",rect=rect)
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=rect)
        self.save()
        payload=b"\x01\x00\x02\x00\x03\x00\x04\x00"
        (self.root/"gpu-0001-upload.bin").write_bytes(payload)
        post=bytearray(self.pre)
        post[:2]=b"\x04\x00"  # only source (1,1) maps to VRAM (0,0)
        (self.root/"gpu-0001-vram.bin").write_bytes(post)
        self.assertEqual(verify_capture(self.root,target_frame=12)[
            "load_pairs_with_verified_vram_effect"],1)
        post[:2]=b"\x01\x00"  # wrong source offset despite correct pixel size
        (self.root/"gpu-0001-vram.bin").write_bytes(post)
        with self.assertRaisesRegex(ValueError,"post-VRAM differs"):
            verify_capture(self.root,target_frame=12)

    def test_before_load_cannot_claim_payload(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","gpu-0000-upload.bin",rect=[0,0,1,1])
        self.events[1]=self.make(1,"after","load","",rect=[0,0,1,1])
        self.save()
        with self.assertRaisesRegex(ValueError,"before event must not"):
            verify_capture(self.root,target_frame=12)

if __name__=="__main__":
    unittest.main()
