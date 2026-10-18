"""Synthetic checker for bounded native GPU command/VRAM capture files."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tools.verify_map02_native_gpu_capture as gpu_module
from tools.verify_map02_native_gpu_capture import private_file, verify_capture, VRAM_BYTES

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

    def test_pinned_private_snapshot_rejects_path_escape(self):
        for name in ("../gpu-0000-vram.bin", "/tmp/foreign-vram.bin",
                     "gpu-0000-vram.bin/extra", "..", True):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "input name"):
                    private_file(self.root, name, expected=VRAM_BYTES)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_pinned_private_snapshot_rejects_fifo_without_blocking(self):
        target = self.root / "gpu-0000-vram.bin"
        target.unlink()
        os.mkfifo(target, mode=0o600)
        original_open = os.open

        def nonblocking_open(path, flags, *args, **kwargs):
            if (os.fspath(path) == os.fspath(target) and
                    not flags & os.O_NONBLOCK):
                raise AssertionError("FIFO open must be nonblocking")
            return original_open(path, flags, *args, **kwargs)

        with patch("tools.verify_map02_native_gpu_capture.os.open",
                   side_effect=nonblocking_open):
            with self.assertRaisesRegex(ValueError, "non-regular file"):
                private_file(self.root, target.name, expected=VRAM_BYTES)

    def test_pinned_snapshot_rejects_identical_inode_swap_during_read(self):
        target = self.root / "gpu-0000-vram.bin"
        backup = self.root / "before-swap"
        original_pread = os.pread
        calls = [0]

        def replace_after_first_pread(fd, size, offset):
            raw = original_pread(fd, size, offset)
            calls[0] += 1
            if calls[0] == 1:
                target.replace(backup)
                target.write_bytes(backup.read_bytes())
            return raw

        with patch("tools.verify_map02_native_gpu_capture.os.pread",
                   side_effect=replace_after_first_pread):
            with self.assertRaisesRegex(ValueError, "changed during private read"):
                private_file(self.root, target.name, expected=VRAM_BYTES)
        self.assertEqual(calls[0], 2)

    def test_pinned_snapshot_rejects_metadata_drift_during_read(self):
        target = self.root / "gpu-0000-vram.bin"
        original_pread = os.pread
        calls = [0]

        def touch_after_first_pread(fd, size, offset):
            raw = original_pread(fd, size, offset)
            calls[0] += 1
            if calls[0] == 1:
                st = target.stat()
                os.utime(target, ns=(st.st_atime_ns,
                                     st.st_mtime_ns + 10**9))
            return raw

        with patch("tools.verify_map02_native_gpu_capture.os.pread",
                   side_effect=touch_after_first_pread):
            with self.assertRaisesRegex(ValueError, "changed during private read"):
                private_file(self.root, target.name, expected=VRAM_BYTES)
        self.assertEqual(calls[0], 2)

    def test_pinned_private_snapshot_rejects_hardlink(self):
        target = self.root / "gpu-0000-vram.bin"
        alias = self.root / "hardlinked-vram"
        os.link(target, alias)
        try:
            with self.assertRaisesRegex(ValueError, "non-regular file"):
                private_file(self.root, target.name, expected=VRAM_BYTES)
        finally:
            alias.unlink()
        self.assertEqual(
            len(private_file(self.root, target.name, expected=VRAM_BYTES)),
            VRAM_BYTES)

    def test_full_audit_rejects_byte_identical_snapshot_swap_after_read(self):
        # All individual reads succeed, and the new file contains the same
        # bytes. The late whole-audit recheck must still reject its new inode.
        target=self.root/"gpu-0000-vram.bin"
        backup=self.root/"old-vram-for-test"
        original=gpu_module.private_file
        replaced=[False]

        def swap_after_last_snapshot(root,name,**kwargs):
            result=original(root,name,**kwargs)
            if (name=="gpu-0003-vram.bin" and kwargs.get("_with_identity")
                    and not replaced[0]):
                target.replace(backup)
                target.write_bytes(backup.read_bytes())
                replaced[0]=True
            return result

        with patch.object(gpu_module,"private_file",
                          side_effect=swap_after_last_snapshot):
            with self.assertRaisesRegex(ValueError,
                                        "evidence changed during full audit"):
                verify_capture(self.root,target_frame=12)
        self.assertTrue(replaced[0])

    def test_full_audit_rejects_snapshot_drift_after_read(self):
        target=self.root/"gpu-0002-vram.bin"
        original=gpu_module.private_file
        changed=[False]

        def mutate_after_last_snapshot(root,name,**kwargs):
            result=original(root,name,**kwargs)
            if (name=="gpu-0003-vram.bin" and kwargs.get("_with_identity")
                    and not changed[0]):
                st=target.stat()
                os.utime(target,ns=(st.st_atime_ns,st.st_mtime_ns+10**9))
                changed[0]=True
            return result

        with patch.object(gpu_module,"private_file",
                          side_effect=mutate_after_last_snapshot):
            with self.assertRaisesRegex(ValueError,
                                        "evidence changed during full audit"):
                verify_capture(self.root,target_frame=12)
        self.assertTrue(changed[0])

    def test_full_audit_rechecks_terminal_receipt_after_validation(self):
        receipt=dict(
            schema="vh.map02.native-capture-status.v1",
            gpu_draw_frame=12,observed_hooks=4,before_hooks=2,after_hooks=2,
            draw_before_hooks=1,transfer_before_hooks=1,indexed_hooks=4,
            written_hooks=4,limit_reached=False,walk_finished=True,
            hooks_balanced=True,observed_window_closed_without_detected_loss=True)
        target=self.root/"gpu-native-capture-status.json"
        target.write_text(json.dumps(receipt)+"\\n",encoding="utf-8")
        original=gpu_module.verify_capture_receipt
        swapped=[False]

        def swap_receipt_after_validation(*args,**kwargs):
            result=original(*args,**kwargs)
            if not swapped[0]:
                backup=self.root/"old-receipt-for-test"
                target.replace(backup)
                target.write_bytes(backup.read_bytes())
                swapped[0]=True
            return result

        with patch.object(gpu_module,"verify_capture_receipt",
                          side_effect=swap_receipt_after_validation):
            with self.assertRaisesRegex(ValueError,
                                        "evidence changed during full audit"):
                verify_capture(self.root,target_frame=12)
        self.assertTrue(swapped[0])

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

    def test_optional_receipt_reconciles_exact_counts_and_rejects_false_claims(self):
        baseline = verify_capture(self.root, target_frame=12)
        self.assertFalse(baseline["capture_receipt_supplied"])
        self.assertFalse(baseline["capture_window_closed_without_detected_loss"])
        receipt = {
            "schema": "vh.map02.native-capture-status.v1",
            "gpu_draw_frame": 12, "observed_hooks": 4,
            "before_hooks": 2, "after_hooks": 2,
            "draw_before_hooks": 1, "transfer_before_hooks": 1,
            "indexed_hooks": 4, "written_hooks": 4,
            "limit_reached": False, "walk_finished": True,
            "hooks_balanced": True,
            "observed_window_closed_without_detected_loss": True,
        }
        path = self.root / "gpu-native-capture-status.json"
        path.write_text(json.dumps(receipt))
        result = verify_capture(self.root, target_frame=12)
        self.assertTrue(result["capture_window_closed_without_detected_loss"])
        self.assertFalse(result["full_original_gameplay_frame_proven"])
        receipt["draw_before_hooks"] = 2
        receipt["transfer_before_hooks"] = 0
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "count/log divergence"):
            verify_capture(self.root, target_frame=12)

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

    def test_optional_drawenv_metadata_is_bounded_and_paired(self):
        # Old probe output omitting DRAWENV remains valid, but newer
        # recorder instances supply exact clip/offset for FT4 checks.
        for event in self.events:
            event["draw_env"]=[0,0,1024,512,-30,25]
        self.save()
        self.assertEqual(verify_capture(self.root,target_frame=12)[
            "draw_otag_primitive_pairs"],1)
        self.events[3]["draw_env"][4] = -31
        self.save()
        with self.assertRaisesRegex(ValueError, "before/after metadata diverges"):
            verify_capture(self.root,target_frame=12)
        self.events[3]["draw_env"][4] = -30
        self.events[2]["draw_env"][2] = -1
        self.save()
        with self.assertRaisesRegex(ValueError, "DRAWENV"):
            verify_capture(self.root,target_frame=12)
        self.events[2]["draw_env"]=[0,0,1024]
        self.save()
        with self.assertRaisesRegex(ValueError, "DRAWENV"):
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
