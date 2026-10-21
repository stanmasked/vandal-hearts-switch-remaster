"""Entirely invented controller inputs and synthetic BizHawk Lua log samples."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_map02_private_bk2_input_handshake import verify


class Map02PrivateInputHandshakeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.report_path = self.root / "invented-inspection.json"
        self.csv_path = self.root / "invented-changes.csv"
        self.log_path = self.root / "invented-console.txt"
        self.report = {
            "schema": "vh.psx.bizhawk.private-bk2-input-inspection.v1",
            "platform": "PSX",
            "core": "Octoshock",
            "game": "Vandal Hearts (USA)",
            "map02_scene_frame_identified": False,
            "original_ps1_game_image_authenticated": False,
            "input_log_frame_count": 100,
            "window": {"start_frame": 10, "length_requested": 6, "changes_exported": 5},
        }
        self.change_rows = [
            (10, "", "", ""),
            (11, "Start", "", "Start"),
            (13, "", "Start", ""),
            (14, "Circle", "", "Circle"),
            (15, "", "Circle", ""),
        ]
        self.probes = [
            (11, 10, 0), (12, 11, 32), (13, 12, 32),
            (14, 13, 0), (15, 14, 256), (16, 15, 0),
        ]
        self.write_files()

    def write_files(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.csv_path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(("frame_zero_based", "buttons_pressed",
                             "buttons_released", "held_buttons"))
            writer.writerows(self.change_rows)
        self.write_probes()

    def write_probes(self, extra="unrelated private emulator log"):
        lines = [extra] if extra else []
        lines += [
            f"VH_PRIVATE_BK2_SYNC counter={counter} candidate_input={frame} mask={mask} mode=PLAY"
            for counter, frame, mask in self.probes
        ]
        self.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_all_six_frames_match_does_not_prove_map02(self):
        report = verify(self.report_path, self.csv_path, self.log_path)
        self.assertTrue(report["all_movie_input_masks_match"])
        self.assertEqual(report["frames_compared"], 6)
        self.assertEqual(report["start_button_press_onsets_in_reference_window"], 1)
        for key in ("actual_emulated_input_delivery_verified",
                    "emulator_to_bk2_frame_offset_independently_verified",
                    "map02_scene_frame_identified", "original_game_boot_confirmed",
                    "ps1_gpu_or_vram_verified"):
            self.assertFalse(report[key])

    def test_off_by_one_counter_refused(self):
        self.probes[0] = (10, 10, 0)
        self.write_probes()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_mask_mismatch_refused(self):
        self.probes[2] = (13, 12, 0)
        self.write_probes()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_missing_probe_frame_refused(self):
        self.probes.pop(3)
        self.write_probes()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_duplicate_frame_refused(self):
        self.probes.insert(2, self.probes[1])
        self.write_probes()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_non_play_mode_refused(self):
        text = self.log_path.read_text(encoding="utf-8").replace("mode=PLAY", "mode=REC", 1)
        self.log_path.write_text(text, encoding="utf-8")
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_error_marker_refused(self):
        self.write_probes("VH_PRIVATE_BK2_SYNC_ERROR skipped_input_counter")
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_empty_probe_refused(self):
        self.log_path.write_text("unrelated\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_inconsistent_csv_edges_refused(self):
        self.change_rows[2] = (13, "", "Circle", "")
        self.write_files()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_duplicate_controller_change_refused(self):
        self.change_rows[2] = self.change_rows[1]
        self.write_files()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_source_frame_window_mismatch_refused(self):
        self.report["window"]["length_requested"] = 10
        self.write_files()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_wrong_core_or_claimed_verified_scene_refused(self):
        for k, v in (("core", "OtherCore"), ("map02_scene_frame_identified", True)):
            with self.subTest(k=k):
                self.report[k] = v
                self.write_files()
                with self.assertRaises(ValueError):
                    verify(self.report_path, self.csv_path, self.log_path)
                self.report[k] = "Octoshock" if k == "core" else False

    def test_symlinked_private_csv_refused(self):
        link = self.root / "linked.csv"
        link.symlink_to(self.csv_path)
        with self.assertRaises(ValueError):
            verify(self.report_path, link, self.log_path)

    def test_known_first_start_anchor_at_1661_is_required(self):
        self.report["input_log_frame_count"] = 2000
        self.report["window"] = {
            "start_frame": 1650, "length_requested": 41, "changes_exported": 3
        }
        self.change_rows = [
            (1650, "", "", ""),
            (1661, "Start", "", "Start"),
            (1663, "", "Start", ""),
        ]
        self.probes = [(frame + 1, frame, 32 if 1661 <= frame <= 1662 else 0)
                       for frame in range(1650, 1691)]
        self.write_files()
        self.assertEqual(verify(self.report_path, self.csv_path, self.log_path)["frames_compared"], 41)
        # A different first Start onset cannot validate the owner's known anchor,
        # even when a synthetic Lua probe agrees with that wrong event stream.
        self.change_rows[1] = (1662, "Start", "", "Start")
        self.probes = [(frame + 1, frame, 32 if frame == 1662 else 0)
                       for frame in range(1650, 1691)]
        self.write_files()
        with self.assertRaises(ValueError):
            verify(self.report_path, self.csv_path, self.log_path)

    def test_lua_uses_movie_getinput_and_does_not_inject_game_inputs(self):
        lua = (Path(__file__).resolve().parents[1] / "tools" /
               "map02_bizhawk_private_input_handshake.lua").read_text(encoding="utf-8")
        self.assertIn("movie.getinput(candidate, 1)", lua)
        self.assertIn('movie.mode() == "PLAY"', lua)
        self.assertIn("emu.frameadvance()", lua)
        self.assertIn("START_INPUT = 1650", lua)
        self.assertIn("END_INPUT = 1690", lua)
        for forbidden in ("joypad.set", "savestate.save", "memory.write",
                          "io.open", "os.execute", "client.screenshot"):
            self.assertNotIn(forbidden, lua)


if __name__ == "__main__":
    unittest.main()
