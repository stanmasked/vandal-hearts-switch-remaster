"""Synthetic tests for the map02 runtime trace checker."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_overall_variants_identify_cross_face_mixing(self):
        prs = evaluate_trace(observations())
        self.assertEqual(prs["post_load_overall_variant"], "PRS")
        self.assertEqual(prs["draw_overall_variant"], "PRS")
        dat = evaluate_trace(observations(a=498, b=550))
        self.assertEqual(dat["post_load_overall_variant"], "DAT")
        self.assertEqual(dat["draw_overall_variant"], "DAT")
        mixed = evaluate_trace(observations(a=641, b=550))
        self.assertEqual(mixed["errors"], [])
        self.assertEqual(mixed["post_load_overall_variant"], "mixed")
        self.assertEqual(mixed["draw_overall_variant"], "mixed")
        missing = evaluate_trace(observations()[:-1])
        self.assertEqual(missing["draw_overall_variant"], "incomplete_or_unknown")

    def test_strict_uniform_variant_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.json"
            command = [sys.executable, "-m", "tools.verify_map02_trace",
                       str(path), "--require-uniform-variant"]
            for a, b, expected in ((641, 643, 0), (498, 550, 0),
                                   (641, 550, 1)):
                with self.subTest(a=a, b=b):
                    path.write_text(json.dumps(observations(a=a, b=b)), encoding="utf-8")
                    result = subprocess.run(command, capture_output=True)
                    self.assertEqual(result.returncode, expected)
            path.write_text(json.dumps(observations(a=641, b=550)), encoding="utf-8")
            self.assertEqual(subprocess.run(command[:-1], capture_output=True).returncode, 0)

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

    def test_mixed_framed_and_unframed_draws_rejected(self):
        entries = observations()
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 2})
        report = evaluate_trace(entries)
        self.assertTrue(any("mixed framed and unframed" in e
                            for e in report["errors"]))

    def test_repeated_draws_across_frames(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries[3]["frame"] = 1
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 2})
        report = evaluate_trace(entries)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["observations"][0]["draw_observation_count"], 2)

    def test_two_render_paths_in_one_frame_are_distinct_observations(self):
        entries = observations()
        entries[2].update({"frame": 1, "path": "normal", "u": 240, "clut": 35})
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 1, "path": "edge",
                        "u": 240, "clut": 35})
        report = evaluate_trace(entries)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["observations"][0]["draw_observation_count"], 2)
        self.assertEqual(report["observations"][0]["draw_paths"], ["edge", "normal"])

    def test_same_path_in_same_frame_still_rejected(self):
        entries = observations()
        entries[2].update({"frame": 1, "path": "normal"})
        entries.append(dict(entries[2]))
        self.assertTrue(any("duplicate draw observation" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_invalid_or_mixed_draw_path_annotations_rejected(self):
        invalid = observations()
        invalid[2].update({"frame": 1, "path": "unknown"})
        self.assertTrue(any("path must be" in e for e in evaluate_trace(invalid)["errors"]))
        mixed = observations()
        mixed[2]["frame"] = 1
        mixed.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                      "gfx": 641, "frame": 2, "path": "normal"})
        self.assertTrue(any("mixed annotated and unannotated" in e
                            for e in evaluate_trace(mixed)["errors"]))

    def test_changed_gfx_in_later_frame_detected(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 498, "frame": 2})
        self.assertTrue(any("changed across frames" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_unknown_gfx_in_later_frame_detected(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 999, "frame": 2})
        errors = evaluate_trace(entries)["errors"]
        self.assertTrue(any("changed across frames" in e for e in errors))
        self.assertTrue(any("unexpected GFX 999" in e for e in errors))

    def test_duplicate_frame_rejected(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries.append(dict(entries[2]))
        self.assertTrue(any("duplicate draw observation" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_metadata_drift_in_later_frame_detected(self):
        entries = observations()
        entries[2].update({"frame": 1, "u": 240, "clut": 35})
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 2, "u": 239, "clut": 35})
        errors = evaluate_trace(entries)["errors"]
        self.assertTrue(any("u changed across frames" in e for e in errors))

    def test_invalid_metadata_in_later_frame_detected(self):
        entries = observations()
        entries[2].update({"frame": 1, "clut": 35})
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 2, "clut": False})
        self.assertTrue(any("clut must be an integer" in e
                            for e in evaluate_trace(entries)["errors"]))

    def test_metadata_first_appearing_in_later_frame(self):
        entries = observations()
        entries[2]["frame"] = 1
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 2, "clut": 35})
        entries.append({"z": 8, "x": 19, "face": 0, "stage": "draw",
                        "gfx": 641, "frame": 3, "clut": 33})
        report = evaluate_trace(entries)
        self.assertTrue(any("clut changed across frames" in e for e in report["errors"]))
        self.assertEqual(report["observations"][0]["draw_metadata"]["clut"], 35)

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
