"""Map02 multi-load splitting and capture-level verdicts (synthetic events only)."""
import unittest

from tools.evaluate_map02_session import evaluate_capture_session
from tools.verify_map02_trace import evaluate_trace
from test_verify_map02_trace import observations


def full_events(a=641, b=643):
    return [
        {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": a},
        {"z": 11, "x": 11, "face": 0, "stage": "post_load", "gfx": b},
        {"z": 8, "x": 19, "face": 0, "stage": "visit", "gfx": a,
         "frame": 8, "path": "normal", "face_count": 2},
        {"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": a,
         "frame": 8, "path": "normal"},
        {"z": 11, "x": 11, "face": 0, "stage": "visit", "gfx": b,
         "frame": 8, "path": "normal", "face_count": 2},
        {"z": 11, "x": 11, "face": 0, "stage": "draw", "gfx": b,
         "frame": 8, "path": "normal"},
    ]


class Map02EpisodeTests(unittest.TestCase):
    def test_single_map_load_retains_existing_analysis_schema(self):
        events = observations()
        self.assertEqual(evaluate_capture_session(iter(events)), evaluate_trace(events))
        strict = full_events()
        self.assertEqual(evaluate_capture_session(iter(strict), require_full_trace=True),
                         evaluate_trace(strict, require_full_trace=True))

    def test_reentering_map11_is_two_valid_independent_visits(self):
        events = full_events() + full_events()
        result = evaluate_capture_session(iter(events), require_full_trace=True)
        self.assertEqual(result["map_load_count"], 2)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["post_load_overall_variant"], "PRS")
        self.assertEqual(result["draw_overall_variant"], "PRS")
        self.assertEqual(result["observations"], [])
        self.assertEqual(len(result["map_loads"]), 2)
        self.assertEqual([ep["event_range"] for ep in result["map_loads"]],
                         [{"first": 1, "last": 6}, {"first": 7, "last": 12}])
        self.assertEqual([[x["draw_observation_count"] for x in ep["observations"]]
                          for ep in result["map_loads"]], [[1, 1], [1, 1]])

    def test_cross_load_prs_dat_change_never_treated_as_one_conclusion(self):
        events = full_events() + full_events(498, 550)
        result = evaluate_capture_session((event for event in events),
                                          require_full_trace=True)
        self.assertEqual(result["map_load_count"], 2)
        self.assertEqual(result["post_load_overall_variant"], "mixed")
        self.assertEqual(result["draw_overall_variant"], "mixed")
        self.assertTrue(any("changed between" in e for e in result["errors"]))
        self.assertEqual([ep["post_load_overall_variant"] for ep in result["map_loads"]],
                         ["PRS", "DAT"])

    def test_missing_second_episode_draw_is_reported_only_for_that_load(self):
        events = full_events() + full_events()[:-1]
        result = evaluate_capture_session(iter(events), require_full_trace=True)
        self.assertEqual(result["map_load_count"], 2)
        self.assertTrue(any("map load 2: missing draw observation" in e
                            for e in result["errors"]))
        self.assertTrue(any("map load 2: full trace nonempty visit without draw or skip"
                            in e for e in result["errors"]))
        self.assertEqual(result["map_loads"][0]["errors"], [])

    def test_ambiguous_duplicate_loader_record_is_not_reinterpreted_as_new_map(self):
        events = observations()[:2] + [dict(observations()[0])]
        result = evaluate_capture_session(iter(events))
        self.assertNotIn("map_loads", result)
        self.assertTrue(any("duplicate observation" in e for e in result["errors"]))

    def test_malformed_coordinate_objects_reach_validator_without_crashing(self):
        for bad in ([], {}, [8, 19], True, "8", None):
            with self.subTest(bad=bad):
                broken = {"z": bad, "x": 19, "face": 0,
                          "gfx": 641, "stage": "post_load"}
                result = evaluate_capture_session(iter([broken, *full_events()]),
                                                  require_full_trace=True)
                self.assertNotIn("map_loads", result)
                self.assertTrue(any("z,x,face,gfx must be integers" in error
                                    for error in result["errors"]))

    def test_bad_coordinates_between_loads_preserve_event_offsets(self):
        invalid = {"z": {}, "x": 19, "face": 0,
                   "gfx": 641, "stage": "visit"}
        events = full_events() + [invalid] + full_events()
        report = evaluate_capture_session(iter(events), require_full_trace=True)
        self.assertEqual(report["map_load_count"], 2)
        self.assertEqual([ep["event_range"] for ep in report["map_loads"]],
                         [{"first": 1, "last": 7}, {"first": 8, "last": 13}])
        self.assertTrue(any("map load 1: entry 6:" in error
                            for error in report["errors"]))
        self.assertEqual(report["map_loads"][1]["errors"], [])

    def test_non_target_noise_counts_in_episode_event_ranges(self):
        noise = {"z": 99, "x": 99, "face": 0,
                 "gfx": 641, "stage": "draw"}
        events = [noise] + full_events() + [noise] + full_events()
        report = evaluate_capture_session(iter(events), require_full_trace=True)
        self.assertEqual([ep["event_range"] for ep in report["map_loads"]],
                         [{"first": 1, "last": 8}, {"first": 9, "last": 14}])
        self.assertEqual(report["errors"], [])

    def test_legacy_repeated_loads_are_separate(self):
        result = evaluate_capture_session(iter(observations() + observations()))
        self.assertEqual(result["map_load_count"], 2)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["post_load_overall_variant"], "PRS")


if __name__ == "__main__":
    unittest.main()
