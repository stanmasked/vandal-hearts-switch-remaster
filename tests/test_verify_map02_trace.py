"""Synthetic tests for the map02 runtime trace checker."""
import unittest

from tools.verify_map02_trace import evaluate_trace


def observations(a=641, b=643, draw_a=None, draw_b=None):
    return [
        {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": a},
        {"z": 11, "x": 11, "face": 0, "stage": "post_load", "gfx": b},
        {"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": a if draw_a is None else draw_a},
        {"z": 11, "x": 11, "face": 0, "stage": "draw", "gfx": b if draw_b is None else draw_b},
    ]


class RuntimeTraceTests(unittest.TestCase):
    def test_prs_variant(self):
        report = evaluate_trace(observations())
        self.assertEqual(report["errors"], [])
        self.assertEqual([x["draw_variant"] for x in report["observations"]], ["PRS", "PRS"])

    def test_dat_variant(self):
        report = evaluate_trace(observations(a=498, b=550))
        self.assertEqual(report["errors"], [])
        self.assertEqual([x["draw_variant"] for x in report["observations"]], ["DAT", "DAT"])

    def test_change_between_stages(self):
        report = evaluate_trace(observations(draw_a=498))
        self.assertTrue(any("changed between" in error for error in report["errors"]))

    def test_missing_draw(self):
        report = evaluate_trace(observations()[:-1])
        self.assertTrue(any("missing draw" in error for error in report["errors"]))

    def test_duplicate_and_invalid_gfx(self):
        entries = observations()
        entries.append(dict(entries[0]))
        entries[1]["gfx"] = 999
        errors = evaluate_trace(entries)["errors"]
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("unexpected GFX" in error for error in errors))

    def test_duplicate_does_not_overwrite_original_observation(self):
        entries = observations()
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": 498})
        report = evaluate_trace(entries)
        self.assertTrue(any("duplicate observation" in error for error in report["errors"]))
        self.assertEqual(report["observations"][0]["draw_gfx"], 641)
        self.assertFalse(any("changed between" in error for error in report["errors"]))

    def test_invalid_json_shapes(self):
        with self.assertRaisesRegex(ValueError, "JSON list"):
            evaluate_trace({"z": 8})
        entries = observations()
        entries[0]["gfx"] = True
        self.assertTrue(any("must be integers" in e for e in evaluate_trace(entries)["errors"]))


if __name__ == "__main__":
    unittest.main()
