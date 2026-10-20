"""Proof that source JSON supports 1-2 members of each original faction."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_map02_fixture as gen


class VariableRosterSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(gen.DEFAULT_INPUT.read_text("utf-8"))

    def test_source_header_is_still_exact_for_both_previous_2_vs_2_maps(self):
        for sid, (filename, _, _) in gen.SCENARIO_HEADERS.items():
            with self.subTest(scene=sid):
                config = json.loads((ROOT / "data" / filename).read_text("utf-8"))
                compiled = gen.render(config)
                header = ROOT / "source" / ("map02_encounter_data.h" if sid.endswith("_a")
                                             else "map02_encounter_b_data.h")
                self.assertEqual(compiled, header.read_text("utf-8"))
                self.assertIn("    2, 2\n};", compiled)

    def test_minimal_one_ally_one_enemy_emits_inert_slots(self):
        data = copy.deepcopy(self.source)
        data["allies"] = data["allies"][:1]
        data["enemies"] = data["enemies"][:1]
        compiled = gen.render(data)
        self.assertIn("{{1, 2, 5, 0}, {0, 0, 0, 0}, {5, 2, 2, 0}, {0, 0, 0, 0}}", compiled)
        self.assertIn("    1, 1\n};", compiled)

    def test_one_ally_two_enemies_and_two_allies_one_enemy(self):
        for allies, enemies in ((1, 2), (2, 1)):
            with self.subTest(allies=allies,enemies=enemies):
                data = copy.deepcopy(self.source)
                data["allies"] = data["allies"][:allies]
                data["enemies"] = data["enemies"][:enemies]
                result = gen.render(data)
                self.assertIn(f"    {allies}, {enemies}\n}};", result)
                self.assertEqual(result.count("{0, 0, 0, 0}"), 4-allies-enemies)

    def test_generated_rosters_build_and_load_in_native_c(self):
        """Test the real JSON -> generated header -> portable C engine boundary."""
        compiler = os.environ.get("CC", "cc")
        with tempfile.TemporaryDirectory(prefix="vh-map02-rosters-") as tmp:
            folder = Path(tmp)
            for filename in ("map02_battle_fixture.h", "map02_encounter_b_data.h"):
                shutil.copyfile(ROOT / "source" / filename, folder / filename)
            harness = folder / "check.c"
            exe = folder / "check"
            for ally_count, enemy_count in ((1, 1), (1, 2), (2, 1), (2, 2)):
                with self.subTest(allies=ally_count, enemies=enemy_count):
                    data = copy.deepcopy(self.source)
                    data["allies"] = data["allies"][:ally_count]
                    data["enemies"] = data["enemies"][:enemy_count]
                    (folder / "map02_encounter_data.h").write_text(
                        gen.render(data), encoding="utf-8"
                    )
                    harness.write_text(
                        '#include <assert.h>\n'
                        '#include "map02_battle_fixture.h"\n'
                        'int main(void) {\n'
                        '    VhMap02Battle s;\n'
                        '    int i;\n'
                        '    assert(vh_binit_index(&s, 0));\n'
                        f'    assert(s.ally_count == {ally_count});\n'
                        f'    assert(s.enemy_count == {enemy_count});\n'
                        '    assert(s.status == VH_BONGOING);\n'
                        '    for (i = s.ally_count; i < VH_BALLIES; ++i)\n'
                        '        assert(s.units[i].x == 0 && s.units[i].y == 0 &&\n'
                        '               s.units[i].hp == 0 && s.units[i].acted == 0);\n'
                        '    for (i = VH_BALLIES + s.enemy_count; i < VH_BUNITS; ++i)\n'
                        '        assert(s.units[i].x == 0 && s.units[i].y == 0 &&\n'
                        '               s.units[i].hp == 0 && s.units[i].acted == 0);\n'
                        '    assert(vh_bchoose(&s) == VH_BSELECT);\n'
                        '    return 0;\n'
                        '}\n',
                        encoding="utf-8",
                    )
                    subprocess.run(
                        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                         "-pedantic", "-O2", str(harness), "-o", str(exe)],
                        check=True, capture_output=True, text=True,
                    )
                    subprocess.run([str(exe)], check=True,
                                   capture_output=True, text=True)

    def test_empty_oversized_duplicate_and_wrong_typed_roster_refused(self):
        for side in ("allies", "enemies"):
            for label, mutation in (
                ("empty", []),
                ("too_many", [{"x":0, "y":0, "hp":1}]*3),
                ("not_list", {}),
                ("boolean_hp", [{"x":1, "y":0, "hp":True}]),
                ("duplicate_spawn", [self.source[side][0]]*2),
            ):
                with self.subTest(side=side,label=label):
                    data = copy.deepcopy(self.source)
                    data[side] = mutation
                    with self.assertRaises(ValueError):
                        gen.render(data)


if __name__ == "__main__":
    unittest.main()
