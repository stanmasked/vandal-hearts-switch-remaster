"""Independently validate both approved authored maps and controller selector."""
import json
from pathlib import Path
import sys
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_map02_fixture as gen

class TwoEncounterTests(unittest.TestCase):
    def test_both_json_to_c_headers_are_exact_and_distinct(self):
        ids = ("map02_original_fixture_a", "map02_original_fixture_b")
        outputs = []
        for sid, (file_name, guard, symbol) in gen.SCENARIO_HEADERS.items():
            self.assertIn(sid, ids)
            with self.subTest(sid=sid):
                payload = json.loads((ROOT / "data" / file_name).read_text(),
                                     object_pairs_hook=gen.objects_unique)
                self.assertEqual(payload["id"], sid)
                built = gen.render(payload)
                target = ROOT / "source" / ("map02_encounter_data.h" if sid.endswith("_a") else "map02_encounter_b_data.h")
                self.assertEqual(target.read_text(), built)
                self.assertIn(guard, built)
                self.assertIn(symbol, built)
                outputs.append(built)
        self.assertNotEqual(outputs[0], outputs[1])
        self.assertIn("{0x00, 0x28, 0x28, 0x08, 0x10, 0x00}", outputs[1])
        self.assertIn("    3, 2,", outputs[1])

    def test_both_generated_headers_check_without_mutation(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/generate_map02_fixture.py"),
             "--all", "--check"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_second_scenario_rejects_unapproved_ids_and_bad_enemy_spawns(self):
        path = ROOT / "data/map02_fixture_b.json"
        source = json.loads(path.read_text())
        changed = dict(source, id="retail_map02_unverified")
        with self.assertRaisesRegex(ValueError, "approved"):
            gen.render(changed)
        import copy
        changed = copy.deepcopy(source)
        changed["enemies"][0]["x"] = 1
        changed["enemies"][0]["y"] = 2
        with self.assertRaises(ValueError):
            gen.render(changed)

    def test_switch_renderer_and_buttons_use_selected_scenario(self):
        code = (ROOT / "source/main.c").read_text()
        self.assertIn("HidNpadButton_L | HidNpadButton_R", code)
        self.assertIn("vh_binit_index(&battle, next)", code)
        self.assertIn("vh_binit_index(&battle, scenario_id)", code)
        self.assertIn("draw_map02_battle(pixels, stride_pixels, &battle,", code)

if __name__ == "__main__":
    unittest.main()
