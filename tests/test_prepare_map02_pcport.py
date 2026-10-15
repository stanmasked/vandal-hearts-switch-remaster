"""Build-overlay tests using a tiny upstream-shaped checkout (no game data)."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_loader import ANCHOR
from tools.prepare_map02_pcport import prepare, git_blob_sha1
from test_make_map02_trace_patch import GRAPHICS as FULL_GRAPHICS



def graphics_fixture():
    """Standalone fake renderer, without importing sibling test modules."""
    parts = []
    for name in ("RenderMapTile", "RenderEdgeMapTile", "RenderOverheadMapTile"):
        parts.append(f"""void {name}(u32 *ot, MapTileModel *tileModel, s32 gridColor) {{
    gfx = tileModel->gfx[faceIdx];
    poly->clut = gGfxClutIds[gfx];
    poly->tpage = gGfxTPageIds[gfx];
    poly->code = GPU_CODE_POLY_FT4;
    AddPrim(ot + OT_SIZE - otz, poly);
}}
""")
    parts.append("s32 GetBestViewOfTarget(s8 z, s8 x, s32 param_3) { return 0; }")
    return "\n".join(parts)



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
            result = prepare(root, out, allow_modified_source=True)
            self.assertEqual(result, out / "map02_trace.mk")
            self.assertEqual((root / "src/core/graphics.c").read_text(), original)
            self.assertIn("VH_TRACE_MAP02_DRAW", (out / "graphics.trace.c").read_text())
            self.assertIn("VH_TRACE_MAP02_POST_LOAD", (out / "game_setup.trace.c").read_text())
            provenance = json.loads((out / "source_provenance.json").read_text())
            self.assertTrue(provenance["allow_modified_source"])
            self.assertEqual(provenance["trace_mode"], "legacy")
            self.assertNotIn("binary_marker", provenance)
            self.assertNotIn("binary_loader_marker", provenance)
            self.assertEqual(len(provenance["source_files"]), 3)
            self.assertEqual(set(provenance["generated_files"]),
                             {"game_setup.trace.c", "graphics.trace.c", "map02_trace.mk"})
            for name, expected_digest in provenance["generated_files"].items():
                self.assertEqual(expected_digest,
                                 hashlib.sha256((out / name).read_bytes()).hexdigest())
            self.assertFalse(all(item["matches_pinned"] for item in provenance["source_files"].values()))
            overlay = result.read_text()
            self.assertIn("-DVH_TRACE_MAP02_DRAW", overlay)
            self.assertIn("-DVH_TRACE_MAP02_POST_LOAD", overlay)
            self.assertIn("$(BUILD_DIR)/src/core/graphics.o", overlay)
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(root, out, allow_modified_source=True)

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
            prepare(root, out, allow_modified_source=True)
            for name, macro in (("states/game_setup", "VH_TRACE_MAP02_POST_LOAD"),
                                ("core/graphics", "VH_TRACE_MAP02_DRAW")):
                result = subprocess.run(
                    ["make", "-n", "-f", "Makefile", "-f", str(out / "map02_trace.mk"),
                     f"build/src/{name}.o"], cwd=root / "platform/pc",
                    capture_output=True, text=True, check=True)
                self.assertIn(f"-D{macro}", result.stdout)
                self.assertIn(f"{name.rsplit('/', 1)[-1]}.trace.c", result.stdout)

    def test_full_trace_make_overlay_replaces_both_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "pcport", Path(tmp) / "full-trace"
            fake_upstream(root)
            source = root / "src/states/game_setup.c"
            source.write_text('#include "field.h"\n' + source.read_text())
            (root / "src/core/graphics.c").write_text(FULL_GRAPHICS)
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
            overlay = prepare(root, out, allow_modified_source=True,
                              full_trace=True)
            provenance = json.loads((out / "source_provenance.json").read_text())
            self.assertEqual(provenance["trace_mode"], "full")
            self.assertRegex(provenance["binary_marker"],
                             r"^VH_MAP02_TRACE_BUILD_ID:[0-9a-f]{64}$")
            self.assertIn(provenance["binary_marker"],
                          (out / "graphics.trace.c").read_text())
            self.assertRegex(provenance["binary_loader_marker"],
                             r"^VH_MAP02_TRACE_LOADER_ID:[0-9a-f]{64}$")
            self.assertEqual(provenance["binary_marker"].split(":", 1)[1],
                             provenance["binary_loader_marker"].split(":", 1)[1])
            self.assertIn(provenance["binary_loader_marker"],
                          (out / "game_setup.trace.c").read_text())
            loader = (out / "game_setup.trace.c").read_text()
            renderer = (out / "graphics.trace.c").read_text()
            self.assertIn("traceTiles[8][19]", loader)
            self.assertIn("VH_Map02TraceVisit", renderer)
            self.assertIn("VH_Map02TraceSkip", renderer)
            self.assertIn("VH_Map02TraceDraw", renderer)
            self.assertEqual(renderer.count("VH_Map02TraceVisit(tileModel,"), 3)
            self.assertIn("-DVH_TRACE_MAP02", overlay.read_text())
            self.assertNotIn("-DVH_TRACE_MAP02_DRAW", overlay.read_text())
            for part in ("states/game_setup", "core/graphics"):
                proc = subprocess.run(
                    ["make", "-n", "-f", "Makefile", "-f", str(overlay),
                     f"build/src/{part}.o"], cwd=root / "platform/pc",
                    capture_output=True, text=True, check=True,
                )
                self.assertIn("-DVH_TRACE_MAP02", proc.stdout)
                self.assertIn(part.rsplit("/", 1)[-1] + ".trace.c",
                              proc.stdout)
                self.assertEqual(proc.stdout.count(".trace.c"), 1)
                self.assertNotIn(" ../../src/", proc.stdout)

    def test_real_pinned_blob_hash_algorithm(self):
        self.assertEqual(git_blob_sha1(b"hello"),
                         "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0")

    def test_pinned_sources_required_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "pcport", Path(tmp) / "trace"
            fake_upstream(root)
            with self.assertRaisesRegex(ValueError, "differs from pinned upstream"):
                prepare(root, out)
            self.assertFalse(out.exists())

    def test_output_path_rejects_shell_metacharacters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pcport"
            fake_upstream(root)
            for unsafe in ("bad;echo", "bad&echo", "bad'quote"):
                with self.subTest(path=unsafe):
                    with self.assertRaisesRegex(ValueError, "shell/make-special"):
                        prepare(root, Path(tmp) / unsafe, allow_modified_source=True)

    def test_rejects_writes_inside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pcport"
            fake_upstream(root)
            with self.assertRaisesRegex(ValueError, "outside upstream"):
                prepare(root, root / "diagnostics", allow_modified_source=True)

    def test_rejects_makefile_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "pcport", Path(tmp) / "trace"
            fake_upstream(root)
            (root / "platform/pc/Makefile").write_text("different make recipe")
            with self.assertRaisesRegex(ValueError, "not the expected"):
                prepare(root, out, allow_modified_source=True)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
