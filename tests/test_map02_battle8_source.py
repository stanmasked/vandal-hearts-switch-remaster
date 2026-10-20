"""End-to-end independent JSON fixture -> C header -> actual 4v4 turns."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_map02_roster8 as fixture


class Battle8SourceBridge(unittest.TestCase):
    def test_json_to_native_four_by_four_victory_and_defeat(self):
        data = json.loads(fixture.DEFAULT_INPUT.read_text(encoding="utf-8"))
        cc = os.environ.get("CC", "cc")
        with tempfile.TemporaryDirectory(prefix="vh-map02-battle8-source-") as tmp:
            folder = Path(tmp)
            (folder / "scene.h").write_text(fixture.render(data), encoding="utf-8")
            source = folder / "battle.c"
            source.write_text(
                '#include <assert.h>\n'
                '#include "map02_battle8.h"\n'
                '#include "scene.h"\n'
                'int main(void) {\n'
                '  VhBattle8 game;\n'
                '  int i;\n'
                '  assert(vh_b8_init(&game, &VH_MAP02_ROSTER8_SMOKE, 2, 2));\n'
                '  for (i = 0; i < 4; ++i) {\n'
                '    game.roster.cursor_x = game.roster.units[i].x;\n'
                '    game.roster.cursor_y = game.roster.units[i].y;\n'
                '    assert(vh_b8_choose(&game) == VH_BSELECT);\n'
                '    game.roster.cursor_x = game.roster.units[4+i].x;\n'
                '    game.roster.cursor_y = game.roster.units[4+i].y;\n'
                '    assert(vh_b8_choose(&game) == VH_BATTACK);\n'
                '    assert(game.status == (i == 3 ? VH_BWIN : VH_BONGOING));\n'
                '  }\n'
                '  assert(vh_b8_init(&game, &VH_MAP02_ROSTER8_SMOKE, 2, 3));\n'
                '  assert(vh_b8_end_turn(&game) == VH_BEND);\n'
                '  assert(game.status == VH_BLOSS);\n'
                '  assert(game.turns_completed == 1);\n'
                '  for (i = 0; i < 4; ++i)\n'
                '    assert(!vh_balive(&game.roster.units[i]));\n'
                '  return 0;\n'
                '}\n',
                encoding="utf-8",
            )
            binary = folder / "battle"
            subprocess.run(
                [cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-pedantic", "-I", str(ROOT / "source"),
                 str(source), "-o", str(binary)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(binary)], check=True,
                           capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
