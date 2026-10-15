"""Synthetic safety and insertion tests for the optional upstream trace patch."""
import unittest

from tools.make_map02_trace_patch import (
    create_patch, instrument_graphics, instrument_loader,
)


LOADER = """#include "field.h"
void LoadMap(void) {
   for (;;) { break; }
   SetupField();
}

void SetupField(void) {
}
"""

GRAPHICS = """#include "PsyQ/gtemac.h"
void RenderMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {
   s32 faceIdx = 0, gfx = 641, opz = 1;
   POLY_FT4 *poly = 0;
   gfx = tileModel->gfx[faceIdx];
      if (gfx != GFX_NULL) {
         gte_stopz(&opz);
         if (opz > 0) {
            AddPrim(ot + OT_SIZE - otz, poly);
         }
      }
}

void RenderEdgeMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {
   s32 faceIdx = 0, gfx = 641, opz = 1;
   POLY_FT4 *poly = 0;
      gte_stopz(&opz);
      if (opz > 0) {
         gfx = tileModel->gfx[faceIdx];
         AddPrim(ot + OT_SIZE - otz, poly);
      }
}

void RenderOverheadMapTile(u32 *ot, MapTileModel *tileModel, s32 brightness) {
   s32 faceIdx = 0, gfx = 641, opz = 1;
   POLY_FT4 *poly = 0;
   gfx = tileModel->gfx[faceIdx];
      if (gfx != GFX_NULL) {
         gte_stopz(&opz);
         if (opz > 0) {
            AddPrim(ot + OT_SIZE - otz, poly);
         }
      }
}

s32 GetBestViewOfTarget(s8 z, s8 x, s32 param_3) {
   return 0;
}
"""


class Map02TracePatchTests(unittest.TestCase):
    def test_loader_hook_is_scoped_to_runtime_map_eleven(self):
        result = instrument_loader(LOADER)
        self.assertIn("gState.mapNum == 11", result)
        self.assertIn('stage', result)
        self.assertIn("traceTiles[8][19]", result)
        self.assertIn("traceTiles[11][11]", result)
        self.assertIn("VH_TRACE_MAP02", result)
        self.assertEqual(result.count("SetupField();"), 1)

    def test_three_submit_paths_are_instrumented(self):
        result = instrument_graphics(GRAPHICS)
        self.assertEqual(result.count("VH_Map02TraceDraw(tileModel, faceIdx"), 3)
        for path in ("normal", "edge", "overhead"):
            self.assertIn(f'"{path}");', result)
        self.assertIn('poly->clut', result)
        self.assertIn('poly->tpage', result)
        self.assertIn('gState.frameCounter', result)
        self.assertEqual(result.count("AddPrim(ot + OT_SIZE - otz, poly);"), 3)
        self.assertEqual(result.count('VH_Map02TraceSkip(tileModel, faceIdx'), 5)
        self.assertIn('"null_gfx"', result)
        self.assertIn('"backface"', result)


    def test_patch_contains_only_two_expected_paths(self):
        diff = create_patch(LOADER, GRAPHICS)
        self.assertIn("--- a/src/states/game_setup.c", diff)
        self.assertIn("+++ b/src/states/game_setup.c", diff)
        self.assertIn("--- a/src/core/graphics.c", diff)
        self.assertIn("+++ b/src/core/graphics.c", diff)
        self.assertEqual(diff.count("--- a/"), 2)

    def test_refuses_reinstrumentation(self):
        with self.assertRaisesRegex(ValueError, "already"):
            instrument_loader(instrument_loader(LOADER))
        with self.assertRaisesRegex(ValueError, "already"):
            instrument_graphics(instrument_graphics(GRAPHICS))

    def test_refuses_modified_or_missing_anchors(self):
        with self.assertRaisesRegex(ValueError, "anchor"):
            instrument_loader(LOADER.replace("   SetupField();", "   OtherSetup();"))
        with self.assertRaisesRegex(ValueError, "AddPrim"):
            instrument_graphics(GRAPHICS.replace("AddPrim(ot + OT_SIZE - otz, poly);",
                                                 "OtherPrim(ot, poly);", 1))
        with self.assertRaisesRegex(ValueError, "anchor"):
            instrument_loader(LOADER.replace('#include "field.h"\n', ""))


if __name__ == "__main__":
    unittest.main()
