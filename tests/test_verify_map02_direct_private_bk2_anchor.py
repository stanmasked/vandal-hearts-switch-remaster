"""Fictional 933949-frame Octoshock BK2 with synthetic button-event totals.

No owner BK2, disc, BIOS, screenshot or actual gameplay bytes.
"""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib

from tools.verify_map02_direct_private_bk2_anchor import source_anchor, verify


ORDER = ("Up", "Down", "Left", "Right", "Select", "Start", "Square",
         "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2",
         "L3", "R3", "MODE")
SYMBOLS = "UDLRsSQTOXlrLRxyz"
LOGKEY = ("LogKey:#Disc Select|Open|Close|Reset|#P1 LStick X|P1 LStick Y|"
          "P1 RStick X|P1 RStick Y|P1 Up|P1 Down|P1 Left|P1 Right|"
          "P1 Select|P1 Start|P1 Square|P1 Triangle|P1 Circle|P1 Cross|"
          "P1 L1|P1 R1|P1 L2|P1 R2|P1 L3|P1 R3|P1 MODE|\n")
HEADER = "MovieVersion FakeForSyntheticUnitTests\nPlatform PSX\nGameName Vandal Hearts (USA)\nCore Octoshock\n"
SYNC = json.dumps({"o": {"FIOConfig": {
    "Devices8": [2, 0, 0, 0, 0, 0, 0, 0],
    "Memcards": [False, False],
    "Multitaps": [False, False],
}}})


def frame(buttons=()):
    digital = "".join(SYMBOLS[i] if name in buttons else "."
                      for i, name in enumerate(ORDER))
    return "|    1,...|  128,  128,  128,  128,%s|\n" % digital


def make_synthetic_source(path, *, short=False, bad_header=False):
    neutral = frame()
    if short:
        frames = neutral * 5
    else:
        # Exact but wholly fabricated aggregate, independent of user data:
        # 10,076 press frames alternating with 10,076 release frames.
        # 3,074 of those press frames include an extra pressed button:
        # 20,152 state changes and 13,150 button-press onsets.
        parts = [neutral * 1661]
        for i in range(10076):
            pressed = (("Start", "Up") if i == 0 else
                       ("Circle", "Up") if i < 3074 else ("Circle",))
            parts.extend((frame(pressed), neutral))
        parts.append(neutral * (933949 - 1661 - 20152))
        frames = "".join(parts)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("Header.txt", HEADER.replace("Octoshock", "Other") if bad_header else HEADER)
        z.writestr("SyncSettings.json", SYNC)
        z.writestr("Input Log.txt", "[Input]\n" + LOGKEY + frames + "[/Input]\n")


def png_chunk(kind, value):
    return (struct.pack(">I", len(value)) + kind + value +
            struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff))


def synthetic_png(value):
    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"\x00" + bytes((value, value, value))))
            + png_chunk(b"IEND", b""))


def capture_log(states=(False, True, False)):
    lines = ["mock console startup"]
    for i, (counter, pressed) in enumerate(zip((1661, 1662, 1663), states)):
        lines.append(
            "VH_PRIVATE_START_CAPTURE counter=%d candidate_input=%d "
            "start_pressed=%s mode=PLAY png=written" %
            (counter, 1660 + i, "yes" if pressed else "no"))
    lines.append(
        "VH_PRIVATE_START_CAPTURE_COMPLETE snapshots=3 "
        "movie_input_anchor_1661=yes displayed_frame_offset=unverified")
    return "\n".join(lines) + "\n"


class DirectPrivateBk2AnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.movie = Path(cls.fixture.name) / "synthetic-933949.bk2"
        make_synthetic_source(cls.movie)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.logs = [self.root / "run1.log", self.root / "run2.log"]
        self.directories = [self.root / "run1-png", self.root / "run2-png"]
        for log, directory in zip(self.logs, self.directories):
            log.write_text(capture_log(), encoding="utf-8")
            directory.mkdir()
            for i, counter in enumerate((1661, 1662, 1663)):
                (directory / ("vh_start_anchor_counter_%07d.png" % counter)).write_bytes(
                    synthetic_png(i + 1))

    def call(self, movie=None, **kwargs):
        return verify(movie or self.movie,
                      kwargs.get("log1", self.logs[0]), kwargs.get("dir1", self.directories[0]),
                      kwargs.get("log2", self.logs[1]), kwargs.get("dir2", self.directories[1]))

    def test_full_synthetic_movie_first_start_and_counts(self):
        self.assertEqual(source_anchor(self.movie), (False, True, False))

    def test_direct_full_movie_and_two_screenshot_bundles_match(self):
        report = self.call()
        self.assertTrue(report["bk2_input_stream_read_directly_and_crc_checked"])
        self.assertTrue(report["bk2_frame_and_button_event_aggregate_matches_known_movie"])
        self.assertEqual(report["recorded_capture_counters_one_based"], [1661, 1662, 1663])
        for key in ("original_disc_or_firmware_authenticated",
                    "genuine_emulator_execution_authenticated",
                    "independent_real_replays_authenticated",
                    "actual_ps1_controller_input_delivery_verified",
                    "input_to_displayed_image_offset_verified",
                    "map02_scene_frame_identified", "native_source_gpu_vram_verified",
                    "private_movie_or_images_uploaded"):
            self.assertFalse(report[key])
        self.assertNotIn(str(self.root), str(report))
        self.assertNotIn(str(self.movie), str(report))

    def test_both_logs_same_wrong_third_state_rejected_against_source(self):
        for log in self.logs:
            log.write_text(capture_log((False, True, True)), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call()

    def test_one_log_wrong_third_state_rejected(self):
        self.logs[1].write_text(capture_log((False, True, True)), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call()

    def test_changed_second_run_png_rejected(self):
        (self.directories[1] / "vh_start_anchor_counter_0001662.png").write_bytes(
            synthetic_png(88))
        with self.assertRaises(ValueError):
            self.call()

    def test_different_capture_paths_required(self):
        with self.assertRaises(ValueError):
            self.call(dir2=self.directories[0])
        with self.assertRaises(ValueError):
            self.call(log2=self.logs[0])

    def test_hardlinked_logs_rejected(self):
        other = self.root / "hardlinked.log"
        import os
        os.link(self.logs[0], other)
        with self.assertRaises(ValueError):
            self.call(log2=other)

    def test_movie_symlink_rejected(self):
        other = self.root / "indirect.bk2"
        other.symlink_to(self.movie)
        with self.assertRaises(ValueError):
            source_anchor(other)

    def test_movie_missing_rejected(self):
        with self.assertRaises(ValueError):
            source_anchor(self.root / "missing.bk2")

    def test_malformed_bk2_archive_rejected(self):
        other = self.root / "bad.bk2"
        other.write_bytes(b"not a zip archive")
        with self.assertRaises(zipfile.BadZipFile):
            source_anchor(other)

    def test_mismatched_length_short_movie_rejected(self):
        other = self.root / "short.bk2"
        make_synthetic_source(other, short=True)
        with self.assertRaises(ValueError):
            source_anchor(other)

    def test_wrong_core_metadata_rejected(self):
        other = self.root / "wrong-core.bk2"
        make_synthetic_source(other, short=True, bad_header=True)
        with self.assertRaises(ValueError):
            source_anchor(other)

    def test_symlinked_private_image_rejected(self):
        img = self.directories[1] / "vh_start_anchor_counter_0001661.png"
        img.unlink()
        img.symlink_to(self.directories[0] / img.name)
        with self.assertRaises((OSError, ValueError)):
            self.call()


if __name__ == "__main__":
    unittest.main()
