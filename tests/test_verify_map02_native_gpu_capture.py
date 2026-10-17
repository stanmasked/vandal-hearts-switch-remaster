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
        self.events[0]["rgb"] = [8,129,255]
        self.events[1]["rgb"] = [8,129,255]
        self.save()
        # A change that stays in the same 5-bit bucket is observationally
        # indistinguishable. A change crossing the boundary must fail.
        self.events[0]["rgb"] = [8,136,255]
        self.events[1]["rgb"] = [8,136,255]
        self.save()
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

    def test_same_length_upload_mutation_changes_payload_fingerprint(self):
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,1,1])
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=[0,0,1,1])
        self.save()
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
