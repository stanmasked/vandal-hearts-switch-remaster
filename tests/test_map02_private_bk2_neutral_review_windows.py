"""Invented BK2 button histories and a fictional full-length archive ONLY."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.map02_private_bk2_neutral_review_windows import (
    NeutralReviewCollector, inspect_movie,
)

ORDER = ("Up", "Down", "Left", "Right", "Select", "Start", "Square",
         "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2",
         "L3", "R3", "MODE")
SYMBOLS = "UDLRsSQTOXlrLRxyz"
HEADER = ("MovieVersion SyntheticCIOnly\nPlatform PSX\n"
          "GameName Vandal Hearts (USA)\nCore Octoshock\n")
SYNC = json.dumps({"o": {"FIOConfig": {
    "Devices8": [2, 0, 0, 0, 0, 0, 0, 0],
    "Memcards": [False, False], "Multitaps": [False, False],
}}})
LOGKEY = ("LogKey:#Disc Select|Open|Close|Reset|#P1 LStick X|P1 LStick Y|"
          "P1 RStick X|P1 RStick Y|P1 Up|P1 Down|P1 Left|P1 Right|"
          "P1 Select|P1 Start|P1 Square|P1 Triangle|P1 Circle|P1 Cross|"
          "P1 L1|P1 R1|P1 L2|P1 R2|P1 L3|P1 R3|P1 MODE|\n")


def input_frame(names=()):
    digital = "".join(SYMBOLS[i] if name in names else "."
                      for i, name in enumerate(ORDER))
    return "|    1,...|  128,  128,  128,  128,%s|\n" % digital


def invented_full_movie(path):
    # Preserves only public aggregate counts (933949 frames, 20152
    # changes, 13150 press onsets). All control timing is fictional.
    idle = input_frame()
    bursts = {50: 240, 100: 360}
    pieces = [idle * 1661]
    for i in range(10076):
        held = (("Start", "Up") if i == 0
                else ("Circle", "Up") if i < 3074 else ("Circle",))
        pieces.extend((input_frame(held), idle))
        if i in bursts:
            pieces.append(idle * bursts[i])
    tail = 933949 - 1661 - 20152 - sum(bursts.values())
    pieces.append(idle * tail)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("Header.txt", HEADER)
        z.writestr("SyncSettings.json", SYNC)
        z.writestr("Input Log.txt", "[Input]\n" + LOGKEY
                   + "".join(pieces) + "[/Input]\n")


class NeutralReviewTests(unittest.TestCase):
    def collect(self, tail, *, minimum=2, maximum=100, limit=12,
                after=1663, before=933949):
        c = NeutralReviewCollector(
            minimum=minimum, maximum=maximum,
            limit=limit, after=after, before=before)
        # Initial BK2 startup silence is deliberately ignored; a button
        # must be present on both sides of a candidate interval.
        history = [frozenset()] * 1661 + [
            frozenset({"Start"}), frozenset({"Start"}),
            frozenset({"Up"})] + [
            frozenset(items) for items in tail
        ]
        for i, held in enumerate(history):
            c.push(i, held)
        return c.ranked()

    def test_one_neutral_interval_with_both_button_edges(self):
        points = self.collect([(), (), (), ("Circle",)])
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["neutral_input_frames"], 3)
        self.assertEqual(points[0]["first_neutral_input_frame_zero_based"], 1664)
        self.assertEqual(points[0]["first_following_button_frame_zero_based"], 1667)
        self.assertEqual(points[0]["suggested_local_review_input_indices_zero_based"],
                         [1663, 1665, 1667])

    def test_initial_startup_silence_is_not_transition(self):
        self.assertEqual(self.collect([("Circle",)]), [])

    def test_trailing_silence_ignored(self):
        self.assertEqual(self.collect([(), (), (), ()]), [])

    def test_uninterrupted_buttons_not_suggested(self):
        self.assertEqual(self.collect([("Circle",), ("Circle",)]), [])

    def test_below_minimum_is_excluded(self):
        self.assertEqual(self.collect([(), (), ("Circle",)], minimum=3), [])

    def test_at_minimum_is_accepted(self):
        self.assertEqual(len(self.collect([(), (), ("Circle",)], minimum=2)), 1)

    def test_above_maximum_is_excluded(self):
        self.assertEqual(self.collect([(), (), (), ("Circle",)], maximum=2), [])

    def test_at_maximum_is_accepted(self):
        self.assertEqual(len(self.collect([(), (), (), ("Circle",)], maximum=3)), 1)

    def test_before_bound_must_include_following_button(self):
        self.assertEqual(
            self.collect([(), (), ("Circle",)], before=1666), [])

    def test_after_bound_must_include_neutral_begin(self):
        self.assertEqual(
            self.collect([(), (), ("Circle",)], after=1665), [])

    def test_after_bound_applies_to_earliest_suggested_capture_frame(self):
        # The neutral run starts at 1664, but its "before" screenshot is
        # input frame 1663. A requested lower bound of 1664 must reject it.
        self.assertEqual(
            self.collect([(), (), (), ("Circle",)], after=1664), [])

    def test_ranking_uses_duration_not_scene_probability(self):
        points = self.collect([
            (), (), ("Circle",),
            (), (), (), (), ("Up",),
        ])
        self.assertEqual([x["neutral_input_frames"] for x in points], [4, 2])

    def test_equal_length_intervals_use_earlier_input_frame(self):
        points = self.collect([
            (), (), ("Circle",), (), (), ("Up",),
        ])
        self.assertLess(
            points[0]["first_neutral_input_frame_zero_based"],
            points[1]["first_neutral_input_frame_zero_based"])

    def test_result_limit_is_enforced(self):
        points = self.collect([
            (), (), ("Circle",), (), (), ("Up",),
        ], limit=1)
        self.assertEqual(len(points), 1)

    def test_bounded_candidate_memory_even_with_many_pauses(self):
        c = NeutralReviewCollector(minimum=2, maximum=100, limit=3)
        for i in range(1664):
            c.push(i, frozenset({"Start"}) if i >= 1661 else frozenset())
        index = 1664
        for _ in range(250):
            for buttons in ((), (), ("Circle",)):
                c.push(index, frozenset(buttons))
                index += 1
            self.assertLessEqual(len(c._windows), 3)
        self.assertEqual(len(c.ranked()), 3)
        first_frames = [w["first_neutral_input_frame_zero_based"] for w in c.ranked()]
        self.assertEqual(first_frames, [1664, 1667, 1670])

    def test_late_longer_interval_replaces_earliest_short_one(self):
        points = self.collect([
            (), (), ("Circle",),
            (), (), (), (), ("Up",),
        ], limit=1)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["neutral_input_frames"], 4)

    def test_contiguous_frames_required(self):
        collector = NeutralReviewCollector(minimum=2)
        collector.push(0, frozenset())
        with self.assertRaises(ValueError):
            collector.push(2, frozenset({"Start"}))

    def test_button_state_input_requires_frozenset(self):
        collector = NeutralReviewCollector(minimum=2)
        with self.assertRaises(ValueError):
            collector.push(0, ["Start"])

    def test_invalid_limits_and_boolean_are_refused(self):
        for kwargs in (
            {"minimum": 0}, {"maximum": 1}, {"minimum": 99, "maximum": 98},
            {"maximum": 24001}, {"limit": 0}, {"limit": 51},
            {"after": 1662}, {"after": 933950}, {"before": 1663},
            {"minimum": True}, {"limit": False},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    NeutralReviewCollector(**kwargs)

    def test_fictional_full_bk2_fingerprint_and_nonidentification(self):
        with tempfile.TemporaryDirectory() as folder:
            movie = Path(folder) / "fictional-vh.bk2"
            invented_full_movie(movie)
            r = inspect_movie(movie, minimum=180, maximum=500, limit=3)
            self.assertEqual(r["source_input_frames_parsed"], 933949)
            self.assertTrue(r["source_input_aggregate_matches_prior_inspection"])
            self.assertEqual([w["neutral_input_frames"] for w in r["review_windows"]],
                             [361, 241])
            self.assertEqual(r["selection_method"],
                             "duration_of_controller_neutral_intervals_only")
            for key in ("map02_scene_frame_identified",
                        "any_scene_transition_authenticated",
                        "emulator_to_movie_frame_offset_independently_verified",
                        "video_or_screenshot_captured",
                        "original_ps1_disc_authenticated",
                        "real_octoshock_playback_verified",
                        "ps1_gpu_vram_verified",
                        "private_bk2_or_inputs_uploaded_to_github"):
                self.assertFalse(r[key])
            self.assertNotIn(str(movie), str(r))
            self.assertNotIn("Start", str(r))

    def test_missing_archive_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                inspect_movie(Path(folder) / "no-movie.bk2")

    def test_symlink_archive_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            movie = Path(folder) / "source.bk2"
            link = Path(folder) / "movie-link.bk2"
            movie.write_bytes(b"zip-placeholder")
            link.symlink_to(movie)
            with self.assertRaises(ValueError):
                inspect_movie(link)


    def test_archive_inside_git_checkout_or_worktree_is_refused(self):
        for marker_kind in ("directory", "worktree-file", "symlinked-parent"):
            with self.subTest(marker_kind=marker_kind):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    if marker_kind == "directory":
                        (root / ".git").mkdir()
                        movie = root / "source.bk2"
                    elif marker_kind == "worktree-file":
                        (root / ".git").write_text("gitdir: ../private-worktree")
                        movie = root / "source.bk2"
                    else:
                        actual = root / "checkout"
                        actual.mkdir()
                        (actual / ".git").mkdir()
                        movie = actual / "source.bk2"
                    movie.write_bytes(b"not-a-zip")
                    if marker_kind == "symlinked-parent":
                        alias = root / "alias"
                        alias.symlink_to(actual, target_is_directory=True)
                        movie = alias / "source.bk2"
                    with self.assertRaisesRegex(ValueError, "outside Git checkout/worktree"):
                        inspect_movie(movie)


if __name__ == "__main__":
    unittest.main()
