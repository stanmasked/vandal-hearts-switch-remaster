"""Synthetic tests for the map02 runtime trace checker."""
import json
import unittest

from tools.verify_map02_trace import evaluate_trace, parse_trace_text


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

    def test_repeated_draws_across_frames(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries[3]["frame"] = 1
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 2})
        report = evaluate_trace(entries)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["observations"][0]["draw_observation_count"], 2)

    def test_changed_gfx_in_later_frame_detected(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 498, "frame": 2})
        self.assertTrue(any("changed across frames" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_duplicate_frame_rejected(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries.append(dict(entries[2]))
        self.assertTrue(any("duplicate draw observation" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_json_lines_loader_output(self):
        entries = observations()
        payload = "\n".join(json.dumps(entry) for entry in entries) + "\n"
        self.assertEqual(parse_trace_text(payload), entries)
        self.assertEqual(evaluate_trace(parse_trace_text(payload))["errors"], [])

    def test_json_array_and_invalid_line(self):
        entries = observations()
        self.assertEqual(parse_trace_text(json.dumps(entries)), entries)
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_trace_text(json.dumps(entries[0]) + "\ninvalid\n")
        with self.assertRaisesRegex(ValueError, "no observations"):
            parse_trace_text("\n  \n")

    def test_single_jsonl_observation(self):
        entry = observations()[0]
        self.assertEqual(parse_trace_text(json.dumps(entry) + "\n"), [entry])
        report = evaluate_trace(parse_trace_text(json.dumps(entry)))
        self.assertTrue(any("missing draw" in e for e in report["errors"]))

    def test_draw_metadata_is_preserved(self):
        entries = observations()
        entries[2].update({"u": 240, "v": 192, "clut": 35, "tpage": 5})
        report = evaluate_trace(entries)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["observations"][0]["draw_metadata"],
                         {"u": 240, "v": 192, "clut": 35, "tpage": 5})

    def test_invalid_draw_metadata_is_rejected(self):
        entries = observations()
        entries[2].update({"u": True, "v": 256, "clut": -1, "tpage": "5"})
        errors = evaluate_trace(entries)["errors"]
        for field in ("u", "v", "clut", "tpage"):
            self.assertTrue(any(f": {field} must be" in e for e in errors))

    def test_later_frame_metadata_is_validated(self):
        entries = observations()
        entries[2].update({"frame": 1, "u": 240, "v": 192, "clut": 35, "tpage": 5})
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "frame": 2, "gfx": 641, "u": 256, "clut": 35})
        errors = evaluate_trace(entries)["errors"]
        self.assertTrue(any("u must be" in e for e in errors))

    def test_later_frame_metadata_change_is_reported(self):
        entries = observations()
        entries[2].update({"frame": 1, "u": 240, "clut": 35})
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "frame": 2, "gfx": 641, "u": 239, "clut": 35})
        self.assertTrue(any("u changed across frames" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_invalid_json_shapes(self):
        with self.assertRaisesRegex(ValueError, "JSON list"):
            evaluate_trace({"z": 8})
        entries = observations()
        entries[0]["gfx"] = True
        self.assertTrue(any("must be integers" in e for e in evaluate_trace(entries)["errors"]))


if __name__ == "__main__":
    unittest.main()
