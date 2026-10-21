"""Entirely invented PNG bytes, logs and movie metadata. No owner data."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.verify_map02_private_start_anchor_reruns import verify


def chunk(name, payload):
    return (struct.pack(">I", len(payload)) + name + payload +
            struct.pack(">I", zlib.crc32(name + payload) & 0xffffffff))


def tiny_invented_png(rgb):
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\x00" + bytes(rgb))) +
            chunk(b"IEND", b""))


class PrivateStartAnchorRerunsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.inspection = self.root / "inspection.json"
        self.inspection.write_text(json.dumps({
            "schema": "vh.psx.bizhawk.private-bk2-input-inspection.v1",
            "game": "Vandal Hearts (USA)", "platform": "PSX", "core": "Octoshock",
            "input_log_frame_count": 933949,
            "map02_scene_frame_identified": False,
            "original_ps1_game_image_authenticated": False,
        }), encoding="utf-8")
        self.images = [self.root / "run-1", self.root / "run-2"]
        self.logs = [self.root / "run-1.log", self.root / "run-2.log"]
        self.png = [tiny_invented_png((i, i + 1, i + 2)) for i in range(3)]
        for directory, logfile in zip(self.images, self.logs):
            directory.mkdir()
            for counter, image in zip((1661, 1662, 1663), self.png):
                (directory / ("vh_start_anchor_counter_%07d.png" % counter)).write_bytes(image)
            logfile.write_text(self.capture_log(), encoding="utf-8")

    @staticmethod
    def capture_log():
        return (
            "some unrelated owner-local log\n"
            "VH_PRIVATE_START_CAPTURE counter=1661 candidate_input=1660 start_pressed=no mode=PLAY png=written\n"
            "VH_PRIVATE_START_CAPTURE counter=1662 candidate_input=1661 start_pressed=yes mode=PLAY png=written\n"
            "VH_PRIVATE_START_CAPTURE counter=1663 candidate_input=1662 start_pressed=no mode=PLAY png=written\n"
            "VH_PRIVATE_START_CAPTURE_COMPLETE snapshots=3 movie_input_anchor_1661=yes displayed_frame_offset=unverified\n"
        )

    def call(self, **kwargs):
        return verify(kwargs.get("inspection", self.inspection),
                      kwargs.get("log_one", self.logs[0]),
                      kwargs.get("folder_one", self.images[0]),
                      kwargs.get("log_two", self.logs[1]),
                      kwargs.get("folder_two", self.images[1]))

    def test_both_runs_repeat_identical_images_without_claiming_real_emulation(self):
        result = self.call()
        self.assertTrue(result["png_sha256_repeats_identically"])
        self.assertEqual(result["capture_counters_one_based"], [1661, 1662, 1663])
        self.assertEqual(result["independent_capture_run_count"], 2)
        for key in ("emulator_playback_executed_authenticated",
                    "screen_pixel_provenance_verified",
                    "input_to_displayed_image_offset_independently_verified",
                    "map02_scene_frame_identified", "ps1_gpu_or_vram_verified",
                    "owner_private_files_uploaded"):
            self.assertFalse(result[key])
        self.assertNotIn(str(self.root), str(result))

    def test_one_changed_screenshot_refused(self):
        path = self.images[1] / "vh_start_anchor_counter_0001662.png"
        path.write_bytes(tiny_invented_png((40, 50, 60)))
        with self.assertRaises(ValueError):
            self.call()

    def test_same_folder_refused_even_if_log_different(self):
        with self.assertRaises(ValueError):
            self.call(folder_two=self.images[0])

    def test_same_log_refused_even_if_folder_different(self):
        with self.assertRaises(ValueError):
            self.call(log_two=self.logs[0])

    def test_wrong_bk2_frame_count_refused(self):
        info = json.loads(self.inspection.read_text())
        info["input_log_frame_count"] = 933948
        self.inspection.write_text(json.dumps(info))
        with self.assertRaises(ValueError):
            self.call()

    def test_source_claimed_map02_scene_refused(self):
        info = json.loads(self.inspection.read_text())
        info["map02_scene_frame_identified"] = True
        self.inspection.write_text(json.dumps(info))
        with self.assertRaises(ValueError):
            self.call()

    def test_first_start_off_by_one_rejected(self):
        self.logs[1].write_text(self.capture_log().replace(
            "counter=1662 candidate_input=1661", "counter=1662 candidate_input=1662"))
        with self.assertRaises(ValueError):
            self.call()

    def test_first_start_event_wrong_state_rejected(self):
        self.logs[1].write_text(self.capture_log().replace(
            "candidate_input=1661 start_pressed=yes", "candidate_input=1661 start_pressed=no"))
        with self.assertRaises(ValueError):
            self.call()

    def test_capture_completion_missing_rejected(self):
        self.logs[1].write_text(self.capture_log().replace("VH_PRIVATE_START_CAPTURE_COMPLETE", "OTHER"))
        with self.assertRaises(ValueError):
            self.call()

    def test_capture_error_record_rejected(self):
        self.logs[1].write_text(self.capture_log() + "VH_PRIVATE_START_CAPTURE_ERROR mode_changed\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_png_structure_corruption_rejected(self):
        path = self.images[1] / "vh_start_anchor_counter_0001661.png"
        path.write_bytes(b"NOT PNG")
        with self.assertRaises(ValueError):
            self.call()

    def test_symlink_png_rejected(self):
        original = self.images[1] / "vh_start_anchor_counter_0001661.png"
        original.unlink()
        original.symlink_to(self.images[0] / original.name)
        with self.assertRaises((ValueError, OSError)):
            self.call()

    def test_wrong_movie_core_rejected(self):
        info = json.loads(self.inspection.read_text())
        info["core"] = "Other"
        self.inspection.write_text(json.dumps(info))
        with self.assertRaises(ValueError):
            self.call()


if __name__ == "__main__":
    unittest.main()
