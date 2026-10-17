"""Synthetic checker for bounded native GPU command/VRAM capture files."""
import json
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
        self.data[0]=31
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
        self.assertEqual(result["changed_native_draw_vram_words"],1)
        self.assertEqual(result["changed_transfer_vram_words"],1)
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

    def test_load_image_payload_name_and_length(self):
        payload=b"\x1f\x00"
        self.events=self.events[:2]
        self.events[0]=self.make(0,"before","load","",rect=[0,0,1,1])
        self.events[1]=self.make(1,"after","load","gpu-0001-upload.bin",rect=[0,0,1,1])
        self.save()
        (self.root/"gpu-0001-upload.bin").write_bytes(payload)
        self.assertEqual(verify_capture(self.root,target_frame=12)["load_image_pairs"],1)
        (self.root/"gpu-0001-upload.bin").write_bytes(b"\x00")
        with self.assertRaisesRegex(ValueError,"wrong file size"):
            verify_capture(self.root,target_frame=12)

if __name__=="__main__":
    unittest.main()
