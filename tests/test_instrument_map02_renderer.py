"""Synthetic checks for map02 draw trace injection into the pinned PC-port renderer."""
import unittest

from tools.instrument_map02_renderer import GUARD, instrument


def fixture():
    return '''void RenderMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {
    gfx = tileModel->gfx[faceIdx];
    poly->clut = gGfxClutIds[gfx];
    poly->tpage = gGfxTPageIds[gfx];
    poly->code = GPU_CODE_POLY_FT4;
    AddPrim(ot + OT_SIZE - otz, poly);
}
void RenderEdgeMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {
    gfx = tileModel->gfx[faceIdx];
    poly->clut = gGfxClutIds[gfx];
    poly->tpage = gGfxTPageIds[gfx];
    poly->code = GPU_CODE_POLY_FT4;
    AddPrim(ot + OT_SIZE - otz, poly);
}
void RenderOverheadMapTile(u32 *ot, MapTileModel *tileModel, s32 brightness) {
    gfx = tileModel->gfx[faceIdx];
    poly->clut = gGfxClutIds[gfx];
    poly->tpage = gGfxTPageIds[gfx];
    poly->code = GPU_CODE_POLY_FT4;
    AddPrim(ot + OT_SIZE - otz, poly);
}
s32 GetBestViewOfTarget(s8 z, s8 x, s32 param_3) {
}
'''


class InstrumentRendererTests(unittest.TestCase):
    def test_three_rendering_paths_instrumented(self):
        modified = instrument(fixture())
        self.assertEqual(modified.count('vh_trace_map02_draw(tileModel, faceIdx, gfx, poly);'), 3)
        self.assertIn('poly->u0', modified)
        self.assertIn('poly->clut', modified)
        self.assertIn('gMapRowPointers[8][19]', modified)
        self.assertIn('gMapRowPointers[11][11]', modified)
        self.assertIn(GUARD, modified)

    def test_instrumentation_is_opt_in(self):
        modified = instrument(fixture())
        self.assertEqual(modified.count('#ifdef VH_TRACE_MAP02_DRAW'), 4)
        with self.assertRaisesRegex(ValueError, 'already instrumented'):
            instrument(modified)

    def test_rejects_missing_function(self):
        with self.assertRaisesRegex(ValueError, 'RenderEdgeMapTile'):
            instrument(fixture().replace('void RenderEdgeMapTile(', 'void MissingFunction('))

    def test_rejects_missing_submission(self):
        with self.assertRaisesRegex(ValueError, 'primitive submission'):
            instrument(fixture().replace('AddPrim(ot + OT_SIZE - otz, poly);', 'NotAddPrim();', 1))

    def test_rejects_missing_metadata(self):
        with self.assertRaisesRegex(ValueError, 'texture metadata'):
            instrument(fixture().replace('poly->clut = gGfxClutIds[gfx];', '/* absent */', 1))


if __name__ == '__main__':
    unittest.main()
