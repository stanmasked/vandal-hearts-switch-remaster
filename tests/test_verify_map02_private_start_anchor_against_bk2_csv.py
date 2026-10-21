"""Entirely fabricated BK2 source CSV, Start logs, and tiny RGB PNG images."""
import csv
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.verify_map02_private_start_anchor_against_bk2_csv import verify


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


def invented_png(v):
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\x00" + bytes((v, v, v)))) +
            chunk(b"IEND", b""))


def capture_log(states):
    lines = ["other console messages are private"]
    for n, (counter, held) in enumerate(zip((1661, 1662, 1663), states)):
        lines.append(
            "VH_PRIVATE_START_CAPTURE counter=%d candidate_input=%d "
            "start_pressed=%s mode=PLAY png=written" %
            (counter, 1660 + n, "yes" if held else "no")
        )
    lines.append(
        "VH_PRIVATE_START_CAPTURE_COMPLETE snapshots=3 "
        "movie_input_anchor_1661=yes displayed_frame_offset=unverified")
    return "\n".join(lines) + "\n"


class StartAnchorCSVTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.report = self.root / "inspection.json"
        self.events = self.root / "events.csv"
        self.logs = [self.root / ("capture-%d.txt" % i) for i in (1, 2)]
        self.images = [self.root / ("captures-%d" % i) for i in (1, 2)]
        self.report_dict = {
            "schema": "vh.psx.bizhawk.private-bk2-input-inspection.v1",
            "platform": "PSX", "game": "Vandal Hearts (USA)", "core": "Octoshock",
            "input_log_frame_count": 933949,
            "map02_scene_frame_identified": False,
            "original_ps1_game_image_authenticated": False,
            "window": {"start_frame": 1659, "length_requested": 5, "changes_exported": 3},
        }
        self.csv_rows = [
            (1659, "", "", ""),
            (1661, "Start", "", "Start"),
            (1662, "", "Start", ""),
        ]
        self.states = (False, True, False)
        self.write_inputs()

    def write_inputs(self):
        self.report.write_text(json.dumps(self.report_dict), encoding="utf-8")
        with self.events.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow((
                "frame_zero_based", "buttons_pressed",
                "buttons_released", "held_buttons"))
            writer.writerows(self.csv_rows)
        for log, folder in zip(self.logs, self.images):
            folder.mkdir(exist_ok=True)
            log.write_text(capture_log(self.states), encoding="utf-8")
            for i, counter in enumerate((1661, 1662, 1663)):
                (folder / ("vh_start_anchor_counter_%07d.png" % counter)).write_bytes(
                    invented_png(i + 1))

    def call(self):
        return verify(self.report, self.events, self.logs[0], self.images[0],
                      self.logs[1], self.images[1])

    def test_source_csv_agrees_with_both_three_frame_logs(self):
        result = self.call()
        self.assertTrue(result["all_three_recorded_start_states_agree_with_private_bk2_csv"])
        self.assertFalse(result["third_frame_start_release_assumed"])
        self.assertEqual(result["first_start_input_index_zero_based"], 1661)
        self.assertEqual(result["separate_capture_bundle_count"], 2)
        for name in ("owner_bk2_read_or_authenticated_by_this_script",
                     "two_real_emulator_runs_authenticated",
                     "ps1_controller_input_delivery_verified",
                     "input_to_displayed_image_offset_verified",
                     "map02_scene_frame_identified", "ps1_gpu_or_vram_verified"):
            self.assertFalse(result[name])
        self.assertNotIn(str(self.root), str(result))

    def test_third_frame_may_continue_holding_start(self):
        # No unsupported assertion that Start is released at index 1662.
        self.csv_rows[2] = (1663, "", "Start", "")
        self.report_dict["window"]["changes_exported"] = 3
        self.states = (False, True, True)
        self.write_inputs()
        self.assertTrue(self.call()["all_three_recorded_start_states_agree_with_private_bk2_csv"])

    def test_single_run_third_frame_mismatch_refused(self):
        self.logs[1].write_text(capture_log((False, True, True)), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call()

    def test_both_runs_forge_third_frame_refused(self):
        for log in self.logs:
            log.write_text(capture_log((False, True, True)), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call()

    def test_source_start_input_frame_shift_refused(self):
        self.csv_rows[1] = (1662, "Start", "", "Start")
        self.csv_rows[2] = (1663, "", "Start", "")
        self.write_inputs()
        with self.assertRaises(ValueError):
            self.call()

    def test_source_start_missing_refused(self):
        self.csv_rows = [(1659, "", "", "")]
        self.report_dict["window"]["changes_exported"] = 1
        self.write_inputs()
        with self.assertRaises(ValueError):
            self.call()

    def test_source_window_missing_frame_1662_refused(self):
        self.report_dict["window"]["length_requested"] = 3
        self.write_inputs()
        with self.assertRaises(ValueError):
            self.call()

    def test_impossible_csv_release_refused(self):
        self.csv_rows[2] = (1662, "", "Circle", "")
        self.write_inputs()
        with self.assertRaises(ValueError):
            self.call()

    def test_duplicate_change_csv_refused(self):
        self.csv_rows[2] = (1661, "", "Start", "")
        self.write_inputs()
        with self.assertRaises(ValueError):
            self.call()

    def test_wrong_bk2_length_refused(self):
        self.report_dict["input_log_frame_count"] = 933950
        self.write_inputs()
        with self.assertRaises(ValueError):
            self.call()

    def test_png_replay_mismatch_refused(self):
        (self.images[1] / "vh_start_anchor_counter_0001662.png").write_bytes(invented_png(199))
        with self.assertRaises(ValueError):
            self.call()

    def test_missing_private_csv_refused(self):
        self.events.unlink()
        # The privacy wrapper deliberately normalizes missing/nonregular input
        # into ValueError without exposing an owner-local path.
        with self.assertRaises(ValueError):
            self.call()

    def test_symlinked_private_source_csv_refused(self):
        external = self.root / "replacement.csv"
        external.write_bytes(self.events.read_bytes())
        self.events.unlink()
        self.events.symlink_to(external)
        with self.assertRaises(ValueError):
            self.call()


if __name__ == "__main__":
    unittest.main()
