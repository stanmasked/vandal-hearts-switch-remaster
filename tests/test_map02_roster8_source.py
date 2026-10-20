"""End-to-end source JSON -> portable C eight-slot roster smoke tests."""
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


class Roster8SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(gen.DEFAULT_INPUT.read_text(encoding="utf-8"))

    def test_four_by_four_authoring_and_native_compiler_bridge(self):
        cc = os.environ.get("CC", "cc")
        with tempfile.TemporaryDirectory(prefix="vh-roster8-json-") as temp:
            tmp = Path(temp)
            header = tmp / "smoke_roster.h"
            source = tmp / "smoke.c"
            exe = tmp / "smoke"
            for ally_count, enemy_count in ((1, 1), (1, 4), (3, 3), (4, 4)):
                with self.subTest(allies=ally_count, enemies=enemy_count):
                    data = copy.deepcopy(self.data)
                    data["allies"] = data["allies"][:ally_count]
                    data["enemies"] = data["enemies"][:enemy_count]
                    header.write_text(gen.render(data), encoding="utf-8")
                    source.write_text(
                        '#include <assert.h>\n'
                        '#include "map02_roster8.h"\n'
                        '#include "smoke_roster.h"\n'
                        'int main(void) {\n'
                        '  VhRoster8 state = VH_MAP02_ROSTER8_SMOKE;\n'
                        '  assert(vh_r8_valid(&state));\n'
                        f'  assert(state.ally_count == {ally_count});\n'
                        f'  assert(state.enemy_count == {enemy_count});\n'
                        f'  assert(vh_r8_alive(&state, 0) == {ally_count});\n'
                        f'  assert(vh_r8_alive(&state, 1) == {enemy_count});\n'
                        '  assert(vh_r8_occupant(&state, 0, 0) == 0);\n'
                        '  assert(vh_r8_result(&state) == VH_BONGOING);\n'
                        '  return 0;\n'
                        '}\n', encoding="utf-8"
                    )
                    subprocess.run(
                        [cc, "-std=c11", "-O2", "-Wall", "-Wextra",
                         "-Werror", "-pedantic", "-I", str(ROOT / "source"),
                         str(source), "-o", str(exe)],
                        check=True, text=True, capture_output=True,
                    )
                    subprocess.run([str(exe)], check=True,
                                   text=True, capture_output=True)

    def test_invalid_rosters_fail_closed(self):
        for side in ("allies", "enemies"):
            for label, invalid in (
                ("zero", []),
                ("five", self.data[side] + [dict(x=7, y=5, hp=1)]),
                ("bad_hp", [dict(x=7, y=5, hp=True)]),
                ("duplicate", [self.data[side][0]] * 2),
            ):
                with self.subTest(side=side, issue=label):
                    d = copy.deepcopy(self.data)
                    d[side] = invalid
                    with self.assertRaises(ValueError):
                        gen.render(d)
        d = copy.deepcopy(self.data)
        d["enemies"][0] = copy.deepcopy(d["allies"][0])
        with self.assertRaises(ValueError):
            gen.render(d)
        d = copy.deepcopy(self.data)
        d["allies"][0]["x"], d["allies"][0]["y"] = 3, 1
        with self.assertRaises(ValueError):
            gen.render(d)
        d = copy.deepcopy(self.data)
        d["cursor"] = [7, 5]
        with self.assertRaises(ValueError):
            gen.render(d)
        d = copy.deepcopy(self.data)
        d["id"] = "unauthorized_content"
        with self.assertRaises(ValueError):
            gen.render(d)
        with self.assertRaises(ValueError):
            json.loads('{"id":"a","id":"b"}', object_pairs_hook=gen.unique_pairs)


if __name__ == "__main__":
    unittest.main()
