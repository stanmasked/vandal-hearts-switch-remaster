"""Build-overlay tests using a tiny upstream-shaped checkout (no game data)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_loader import ANCHOR
from tools.prepare_map02_pcport import prepare
from tests.test_instrument_map02_renderer import fixture as graphics_fixture


def fake_upstream(root: Path):
    (root / "src/states").mkdir(parents=True)
    (root / "src/core").mkdir()
    (root / "platform/pc").mkdir(parents=True)
    (root / "platform/pc/Makefile").write_text('''GAME_C_FLAGS := -std=gnu89
$(BUILD_DIR)/src/%.o: $(SRC_DIR)/%.c | stage
\t$(CC) $(GAME_C_FLAGS) -MMD -MP -c -o $@ $<
''')
    (root / "src/states/game_setup.c").write_text('''void LoadMap(void) {
   ProcessMapFileData(&gScratch1_801317c0[0]);
   pTiles[iz][ix].gfx[iFace] += GFX_MAP_TEXTURES_OFS;
''' + ANCHOR)
    (root / "src/core/graphics.c").write_text(graphics_fixture())


class PrepareTests(unittest.TestCase):
    def test_generates_both_source_files_and_make_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "pcport", Path(tmp) / "trace"
            fake_upstream(root)
            original = (root / "src/core/graphics.c").read_text()
            result = prepare(root, out)
            self.assertEqual(result, out / "map02_trace.mk")
            self.assertEqual((root / "src/core/graphics.c").read_text(), original)
            self.assertIn("VH_TRACE_MAP02_DRAW", (out / "graphics.trace.c").read_text())
            self.assertIn("VH_TRACE_MAP02_POST_LOAD", (out / "game_setup.trace.c").read_text())
            overlay = result.read_text()
            self.assertIn("-DVH_TRACE_MAP02_DRAW", overlay)
            self.assertIn("-DVH_TRACE_MAP02_POST_LOAD", overlay)
            self.assertIn("$(BUILD_DIR)/src/core/graphics.o", overlay)
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(root, out)

    def test_make_dry_run_uses_generated_source_and_feature_defines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "pcport", Path(tmp) / "trace"
            fake_upstream(root)
            mk = root / "platform/pc/Makefile"
            mk.write_text("""SRC_DIR := ../../src
BUILD_DIR := build
CC := gcc
GAME_C_FLAGS := -std=gnu89
stage:
\t@true
$(BUILD_DIR)/src/%.o: $(SRC_DIR)/%.c | stage
\t$(CC) $(GAME_C_FLAGS) -MMD -MP -c -o $@ $<
""")
            prepare(root, out)
            for name, macro in (("states/game_setup", "VH_TRACE_MAP02_POST_LOAD"),
                                ("core/graphics", "VH_TRACE_MAP02_DRAW")):
                result = subprocess.run(
                    ["make", "-n", "-f", "Makefile", "-f", str(out / "map02_trace.mk"),
                     f"build/src/{name}.o"], cwd=root / "platform/pc",
                    capture_output=True, text=True, check=True)
                self.assertIn(f"-D{macro}", result.stdout)
                self.assertIn(f"{name.rsplit('/', 1)[-1]}.trace.c", result.stdout)

    def test_rejects_writes_inside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pcport"
            fake_upstream(root)
            with self.assertRaisesRegex(ValueError, "outside upstream"):
                prepare(root, root / "diagnostics")

    def test_rejects_makefile_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "pcport", Path(tmp) / "trace"
            fake_upstream(root)
            (root / "platform/pc/Makefile").write_text("different make recipe")
            with self.assertRaisesRegex(ValueError, "not the expected"):
                prepare(root, out)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
