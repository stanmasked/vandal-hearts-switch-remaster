#!/usr/bin/env python3
"""Reject malformed MAP02 JSON, stale generated C data and private-content drift."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_map02_fixture as gen


class AuthoredEncounterDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(gen.DEFAULT_INPUT.read_text(encoding="utf-8"),
                             object_pairs_hook=gen.objects_unique)

    def test_generated_header_is_exact_and_deterministic(self):
        built = gen.render(self.doc)
        self.assertEqual(built, gen.DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(gen.render(copy.deepcopy(self.doc)), built)
        self.assertIn("VH_BEVENT_ENEMIES_DOWN", built)
        self.assertIn("VH_BEVENT_ALLIES_DOWN", built)
        self.assertIn("{0x00, 0x08, 0x08, 0x08, 0x10, 0x00}", built)

    def test_authored_alternate_scene_is_supported_without_rewriting_rules(self):
        altered = copy.deepcopy(self.doc)
        altered["board"]["blocked"] = [[3, 1], [3, 3], [4, 4]]
        altered["rules"]["move_range"] = 1
        altered["rules"]["attack_damage"] = 2
        altered["allies"][0]["x"] = 2
        altered["cursor"] = [2, 2]
        rendered = gen.render(altered)
        self.assertIn("{0x00, 0x08, 0x00, 0x08, 0x10, 0x00}", rendered)
        self.assertIn("    1, 2,", rendered)
        self.assertNotEqual(rendered, gen.render(self.doc))

    def test_rejects_bad_tiles_units_rules_and_outcome_events(self):
        cases = []
        for mutation in ("duplicate-wall", "unit-on-wall", "overlap",
                         "outside-map", "bool-hp", "zero-hp",
                         "invalid-move", "invalid-damage", "cursor-off-ally",
                         "duplicate-event", "wrong-event", "missing-event",
                         "unknown-field", "wrong-map-size", "extra-unit"):
            d = copy.deepcopy(self.doc)
            if mutation == "duplicate-wall":
                d["board"]["blocked"].append([3, 1])
            elif mutation == "unit-on-wall":
                d["allies"][0].update(x=3, y=2)
            elif mutation == "overlap":
                d["enemies"][0].update(x=1, y=4)
            elif mutation == "outside-map":
                d["allies"][0]["x"] = 8
            elif mutation == "bool-hp":
                d["allies"][0]["hp"] = True
            elif mutation == "zero-hp":
                d["enemies"][1]["hp"] = 0
            elif mutation == "invalid-move":
                d["rules"]["move_range"] = 0
            elif mutation == "invalid-damage":
                d["rules"]["attack_damage"] = 1000
            elif mutation == "cursor-off-ally":
                d["cursor"] = [0, 0]
            elif mutation == "duplicate-event":
                d["events"][1] = d["events"][0]
            elif mutation == "wrong-event":
                d["events"][0]["result"] = "defeat"
            elif mutation == "missing-event":
                d["events"] = d["events"][:1]
            elif mutation == "unknown-field":
                d["retail_disc"] = "not permitted"
            elif mutation == "wrong-map-size":
                d["board"]["width"] = 9
            elif mutation == "extra-unit":
                d["allies"].append(dict(x=0, y=0, hp=1))
            cases.append((mutation, d))
        for name, data in cases:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    gen.render(data)

    def test_rejects_json_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            json.loads('{"schema_version": 1, "schema_version": 2}',
                       object_pairs_hook=gen.objects_unique)

    def test_cli_check_refuses_stale_artifact_without_modifying_it(self):
        content = gen.render(self.doc)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.h"
            path.write_text(content + "/* unwanted manual change */\n")
            before = path.read_bytes()
            import subprocess
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools/generate_map02_fixture.py"),
                 "--input", str(gen.DEFAULT_INPUT), "--output", str(path),
                 "--check"], text=True, capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(path.read_bytes(), before)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools/generate_map02_fixture.py"),
                 "--input", str(gen.DEFAULT_INPUT), "--output", str(path)],
                text=True, capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(path.read_text(), content)


if __name__ == "__main__":
    unittest.main()
