"""Public synthetic Octoshock PSX BK2 fixtures — NEVER original user movie."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from tools.inspect_map02_private_bk2 import inspect

HEADER = ("MovieVersion BizHawk v2.0.0\n"
          "Platform PSX\nGameName Vandal Hearts (USA)\nCore Octoshock\n")
SYNC = json.dumps({"o": {"FIOConfig": {
    "Devices8": [2, 0, 0, 0, 0, 0, 0, 0],
    "Memcards": [False, False],
    "Multitaps": [False, False],
}}})
LOGKEY = ("LogKey:#Disc Select|Open|Close|Reset|#P1 LStick X|P1 LStick Y|"
          "P1 RStick X|P1 RStick Y|P1 Up|P1 Down|P1 Left|P1 Right|"
          "P1 Select|P1 Start|P1 Square|P1 Triangle|P1 Circle|P1 Cross|"
          "P1 L1|P1 R1|P1 L2|P1 R2|P1 L3|P1 R3|P1 MODE|\n")
ORDER = ("Up", "Down", "Left", "Right", "Select", "Start", "Square",
         "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2",
         "L3", "R3", "MODE")
SYMBOLS = "UDLRsSQTOXlrLRxyz"


def frame(buttons=(), *, prefix="    1,...", axes=(128, 128, 128, 128)):
    digital = "".join(SYMBOLS[i] if x in buttons else "."
                      for i, x in enumerate(ORDER))
    return "|{}|{},{}|\n".format(
        prefix, ",".join("{:5d}".format(x) for x in axes), digital
    )


def create_movie(path, frames, *, header=HEADER, sync=SYNC, key=LOGKEY,
                 end=True, extra=None):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("Header.txt", header)
        z.writestr("SyncSettings.json", sync)
        z.writestr("Input Log.txt",
                   "[Input]\n" + key + "".join(frames)
                   + ("[/Input]\n" if end else ""))
        if extra is not None:
            z.writestr(*extra)


class PrivateBk2InputInspectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.movie = self.root / "SYNTHETIC-ONLY.bk2"

    def test_exact_zero_based_button_edges_and_frame_count(self):
        create_movie(self.movie, [
            frame(), frame(("Start",)), frame(),
            frame(("Up", "Circle")), frame(("Circle",)),
            frame(), frame(),
        ])
        report = inspect(self.movie)
        self.assertEqual(report["input_log_frame_count"], 7)
        self.assertEqual(report["button_state_change_frames"], 5)
        self.assertEqual(report["button_press_onsets"], 3)
        self.assertEqual(report["pressed_button_counts"],
                         {"Circle": 1, "Start": 1, "Up": 1})
        self.assertEqual(report["longest_no_button_span"],
                         {"start_frame": 5, "frames": 2})
        self.assertFalse(report["original_ps1_game_image_authenticated"])
        self.assertFalse(report["map02_scene_frame_identified"])
        self.assertFalse(report["ps1_gpu_captures_read"])

    def test_private_bounded_csv_only_with_exclusive_0600_permissions(self):
        create_movie(self.movie, [
            frame(), frame(("Start",)), frame(),
            frame(("Circle",)), frame(), frame(),
        ])
        target = self.root / "private-controls.csv"
        report = inspect(self.movie, 1, 4, target)
        self.assertEqual(report["window"]["changes_exported"], 4)
        with target.open(newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual([int(x["frame_zero_based"]) for x in rows], [1, 2, 3, 4])
        self.assertEqual(rows[0]["buttons_pressed"], "Start")
        self.assertEqual(rows[2]["buttons_pressed"], "Circle")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            inspect(self.movie, 1, 4, target)

    def test_export_frame_window_requires_24000_max(self):
        create_movie(self.movie, [frame()])
        for start, size in ((0, 0), (0, 24001), (-1, 1)):
            with self.subTest(start=start, size=size):
                with self.assertRaises(ValueError):
                    inspect(self.movie, start, size, self.root / "private.csv")

    def test_wrong_game_core_platform_refused(self):
        for old, wrong in (
            ("Vandal Hearts (USA)", "Other game"),
            ("Octoshock", "OtherCore"),
            ("Platform PSX", "Platform SNES"),
        ):
            with self.subTest(wrong=wrong):
                create_movie(self.movie, [frame()], header=HEADER.replace(old, wrong))
                with self.assertRaises(ValueError):
                    inspect(self.movie)

    def test_mismatched_input_button_order_refused(self):
        create_movie(self.movie, [frame()],
                     key=LOGKEY.replace("P1 Circle", "P1 Invalid"))
        with self.assertRaisesRegex(ValueError, "button order"):
            inspect(self.movie)

    def test_missing_input_end_refused(self):
        create_movie(self.movie, [frame()], end=False)
        with self.assertRaisesRegex(ValueError, "end marker"):
            inspect(self.movie)

    def test_disc_selection_or_reset_change_needs_playback(self):
        create_movie(self.movie, [frame(prefix="    2,...")])
        with self.assertRaisesRegex(ValueError, "disc/reset"):
            inspect(self.movie)

    def test_analog_non_neutral_is_reported_not_hidden(self):
        create_movie(self.movie, [
            frame(), frame(axes=(128, 130, 128, 128)),
        ])
        self.assertEqual(inspect(self.movie)["nonneutral_analog_frames"], 1)

    def test_unlisted_member_and_duplicate_archive_member_refused(self):
        create_movie(self.movie, [frame()], extra=("game-disc.bin", b"private"))
        with self.assertRaises(ValueError):
            inspect(self.movie)
        create_movie(self.movie, [frame()])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.movie, "a") as z:
                z.writestr("Header.txt", HEADER)
        with self.assertRaises(ValueError):
            inspect(self.movie)

    def test_private_archive_symlink_refused(self):
        create_movie(self.movie, [frame()])
        link = self.root / "linked.bk2"
        link.symlink_to(self.movie)
        with self.assertRaises(ValueError):
            inspect(link)

    def test_nonstandard_memory_card_setup_refused(self):
        bad = json.loads(SYNC)
        bad["o"]["FIOConfig"]["Memcards"] = [True, False]
        create_movie(self.movie, [frame()], sync=json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "differs"):
            inspect(self.movie)

    def test_final_active_frames_do_not_count_as_neutral(self):
        create_movie(self.movie, [
            frame(), frame(), frame(("Start",)),
            frame(("Start",)), frame(("Start",)),
        ])
        self.assertEqual(
            inspect(self.movie)["longest_no_button_span"],
            {"start_frame": 0, "frames": 2},
        )


if __name__ == "__main__":
    unittest.main()
