"""Invented BK2 inspection summary and BizHawk console records only."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.validate_map02_private_replay_markers import verify


class PrivateReplayMarkersTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.report = self.root / "synthetic-report.json"
        self.log = self.root / "synthetic-console.txt"
        self.summary = {
            "schema": "vh.psx.bizhawk.private-bk2-input-inspection.v1",
            "game": "Vandal Hearts (USA)", "platform": "PSX", "core": "Octoshock",
            "input_log_frame_count": 100,
            "original_ps1_game_image_authenticated": False,
            "map02_scene_frame_identified": False,
        }
        self.report.write_text(json.dumps(self.summary), encoding="utf-8")

    def mark(self, *lines):
        self.log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_counts_marker_lines_and_preserves_uncertainty(self):
        self.mark("BizHawk internal console line", "VH_PRIVATE_REPLAY_MARKER counter=2 candidate_input=1 mode=PLAY scene=unverified",
                  "VH_PRIVATE_REPLAY_MARKER counter=99 candidate_input=98 mode=PLAY scene=unverified")
        result = verify(self.report, self.log)
        self.assertEqual(result["markers_count"], 2)
        self.assertEqual(result["last_emulator_counter"], 99)
        self.assertFalse(result["map02_scene_frame_identified"])
        self.assertFalse(result["emu_to_movie_frame_offset_verified"])
        self.assertFalse(result["ps1_gpu_captures_read"])

    def test_accepts_last_movie_input_candidate(self):
        self.mark("VH_PRIVATE_REPLAY_MARKER counter=100 candidate_input=99 mode=PLAY scene=unverified")
        self.assertEqual(verify(self.report, self.log)["markers_count"], 1)

    def test_rejects_offset_or_movie_range_mismatch(self):
        for counter, candidate in ((0, 0), (101, 100), (5, 5)):
            with self.subTest(counter=counter):
                self.mark(f"VH_PRIVATE_REPLAY_MARKER counter={counter} candidate_input={candidate} mode=PLAY scene=unverified")
                with self.assertRaises(ValueError):
                    verify(self.report, self.log)

    def test_rejects_duplicate_or_backwards_counter(self):
        for first, second in ((3, 3), (9, 2)):
            with self.subTest(first=first, second=second):
                self.mark(f"VH_PRIVATE_REPLAY_MARKER counter={first} candidate_input={first-1} mode=PLAY scene=unverified",
                          f"VH_PRIVATE_REPLAY_MARKER counter={second} candidate_input={second-1} mode=PLAY scene=unverified")
                with self.assertRaises(ValueError):
                    verify(self.report, self.log)

    def test_refuses_malformed_or_non_play_marker(self):
        for token in ("mode=REC", "scene=MAP02", "candidate_input=abc"):
            with self.subTest(token=token):
                self.mark("VH_PRIVATE_REPLAY_MARKER counter=2 candidate_input=1 mode=PLAY scene=unverified".replace(
                    "mode=PLAY" if token.startswith("mode") else ("scene=unverified" if token.startswith("scene") else "candidate_input=1"), token))
                with self.assertRaises(ValueError):
                    verify(self.report, self.log)

    def test_refuses_no_markers(self):
        self.mark("Other console data")
        with self.assertRaises(ValueError):
            verify(self.report, self.log)

    def test_refuses_unrelated_core_or_unauthenticated_claim_change(self):
        self.mark("VH_PRIVATE_REPLAY_MARKER counter=2 candidate_input=1 mode=PLAY scene=unverified")
        for key, value in (("core", "Nymashock"), ("map02_scene_frame_identified", True)):
            with self.subTest(key=key):
                report = dict(self.summary, **{key: value})
                self.report.write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaises(ValueError):
                    verify(self.report, self.log)

    def test_rejects_symlinks(self):
        self.mark("VH_PRIVATE_REPLAY_MARKER counter=2 candidate_input=1 mode=PLAY scene=unverified")
        link = self.root / "link-console.txt"
        link.symlink_to(self.log)
        with self.assertRaises(ValueError):
            verify(self.report, link)

    def test_rejects_more_than_200_markers(self):
        self.summary["input_log_frame_count"] = 1000
        self.report.write_text(json.dumps(self.summary), encoding="utf-8")
        self.mark(*(f"VH_PRIVATE_REPLAY_MARKER counter={x} candidate_input={x-1} mode=PLAY scene=unverified" for x in range(1, 202)))
        with self.assertRaises(ValueError):
            verify(self.report, self.log)

    def test_observer_is_non_mutating_and_never_marks_map02_verified(self):
        lua = (Path(__file__).resolve().parents[1] / "tools" / "map02_bizhawk_private_replay_observer.lua").read_text(encoding="utf-8")
        self.assertIn('movie.mode() == "PLAY"', lua)
        self.assertIn("emu.framecount()", lua)
        self.assertIn("emu.frameadvance()", lua)
        self.assertIn("scene=unverified", lua)
        for mutation in ("joypad.set", "io.open", "os.execute", "savestate.save", "client.screenshot"):
            self.assertNotIn(mutation, lua)


if __name__ == "__main__":
    unittest.main()
