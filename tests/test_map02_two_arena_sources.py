"""Verify both independent 8-slot maps are strictly authored and C-reproducible."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_map02_roster8 as gen


class TwoArenaSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = json.loads(gen.DEFAULT_INPUT.read_text(encoding="utf-8"))
        cls.second = json.loads(gen.SECOND_INPUT.read_text(encoding="utf-8"))

    def test_checked_in_headers_match_both_independent_sources(self):
        self.assertEqual(
            gen.render(self.primary),
            (ROOT / "source/map02_roster8_smoke_data.h").read_text(encoding="utf-8"),
        )
        second_c = gen.render(
            self.second, gen.SECOND_FIXTURE_ID, gen.SECOND_SYMBOL,
            "VH_MAP02_ROSTER8_SECOND_H",
        )
        self.assertEqual(
            second_c,
            (ROOT / "source/map02_roster8_second_data.h").read_text(
                encoding="utf-8"),
        )
        self.assertNotEqual(gen.parse(self.primary), gen.parse(
            self.second, gen.SECOND_FIXTURE_ID))
        self.assertEqual(gen.parse(self.second, gen.SECOND_FIXTURE_ID)[-1],
                         (1, 0))

    def test_source_to_native_c_compiler_for_both_maps_and_three_sizes(self):
        with tempfile.TemporaryDirectory(prefix="vh-two-arenas-") as td:
            root = Path(td)
            executable = root / "two"
            source = root / "two.c"
            source.write_text(
                '#include <assert.h>\n'
                '#include "map02_roster8_variants.h"\n'
                'int main(void) {\n'
                '  int scene, variant;\n'
                '  for (scene = 0; scene < VH_R8_SCENES; ++scene)\n'
                '    for (variant = 0; variant < VH_R8_VARIANTS; ++variant) {\n'
                '      VhRoster8 r; VhBattle8 state;\n'
                '      assert(vh_r8_scene_variant(&r, scene, variant));\n'
                '      assert(vh_r8_valid(&r));\n'
                '      assert(vh_b8_init_scene_variant(&state, scene, variant));\n'
                '      assert(state.roster.cursor_x == scene);\n'
                '    }\n'
                '  return 0;\n'
                '}\n',
                encoding="utf-8",
            )
            subprocess.run(
                [os.environ.get("CC", "cc"), "-std=c11", "-O2",
                 "-Wall", "-Wextra", "-Werror", "-pedantic",
                 "-I", str(ROOT / "source"), str(source), "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(executable)], check=True,
                           capture_output=True, text=True)

    def test_crossmap_forgery_and_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            gen.render(self.second)
        with self.assertRaises(ValueError):
            gen.render(self.primary, gen.SECOND_FIXTURE_ID, gen.SECOND_SYMBOL,
                       "VH_MAP02_ROSTER8_SECOND_H")
        with self.assertRaises(ValueError):
            gen.render(self.second, gen.SECOND_FIXTURE_ID, gen.SYMBOL,
                       "VH_MAP02_ROSTER8_SMOKE_H")
        invalid = copy.deepcopy(self.second)
        invalid["allies"][0] = copy.deepcopy(invalid["enemies"][0])
        with self.assertRaises(ValueError):
            gen.render(invalid, gen.SECOND_FIXTURE_ID, gen.SECOND_SYMBOL,
                       "VH_MAP02_ROSTER8_SECOND_H")
        invalid = copy.deepcopy(self.second)
        invalid["board"]["blocked"].append([1, 0])
        with self.assertRaises(ValueError):
            gen.render(invalid, gen.SECOND_FIXTURE_ID, gen.SECOND_SYMBOL,
                       "VH_MAP02_ROSTER8_SECOND_H")
        invalid = copy.deepcopy(self.second)
        invalid["enemies"] = []
        with self.assertRaises(ValueError):
            gen.render(invalid, gen.SECOND_FIXTURE_ID, gen.SECOND_SYMBOL,
                       "VH_MAP02_ROSTER8_SECOND_H")
        with self.assertRaises(ValueError):
            json.loads('{"board":1,"board":2}',
                       object_pairs_hook=gen.unique_pairs)


if __name__ == "__main__":
    unittest.main()
