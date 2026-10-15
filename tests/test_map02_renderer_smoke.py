"""Host-only C smoke check for generated map02 trace (synthetic GPU and tiles)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_renderer import instrument

C_FIXTURE = r'''
#include <stdint.h>
typedef unsigned int u32;
typedef int s32;
typedef signed char s8;
typedef struct { int gfx[18]; } MapTileModel;
typedef struct { unsigned char u0, v0, code; unsigned short clut, tpage; } POLY_FT4;
static struct { int mapNum; } gState = {11};
static MapTileModel gMapRowPointers[22][28];
static unsigned short gGfxClutIds[1000], gGfxTPageIds[1000];
#define GPU_CODE_POLY_FT4 0x2c
#define OT_SIZE 1024
static void AddPrim(u32 *ot, POLY_FT4 *poly) {(void)ot; (void)poly;}
void RenderMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {
   int faceIdx = 0, gfx = tileModel->gfx[faceIdx], otz = 7;
   POLY_FT4 quad = {.u0 = 240, .v0 = 192};
   POLY_FT4 *poly = &quad;
   (void)gridColor;
   gfx = tileModel->gfx[faceIdx];
   poly->clut = gGfxClutIds[gfx];
   poly->tpage = gGfxTPageIds[gfx];
   poly->code = GPU_CODE_POLY_FT4;
   AddPrim(ot + OT_SIZE - otz, poly);
}
void RenderEdgeMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {
   int faceIdx = 0, gfx = tileModel->gfx[faceIdx], otz = 7;
   POLY_FT4 quad = {.u0 = 240, .v0 = 192};
   POLY_FT4 *poly = &quad;
   (void)gridColor;
   gfx = tileModel->gfx[faceIdx];
   poly->clut = gGfxClutIds[gfx];
   poly->tpage = gGfxTPageIds[gfx];
   poly->code = GPU_CODE_POLY_FT4;
   AddPrim(ot + OT_SIZE - otz, poly);
}
void RenderOverheadMapTile(u32 *ot, MapTileModel *tileModel, s32 brightness) {
   int faceIdx = 0, gfx = tileModel->gfx[faceIdx], otz = 7;
   POLY_FT4 quad = {.u0 = 240, .v0 = 192};
   POLY_FT4 *poly = &quad;
   (void)brightness;
   gfx = tileModel->gfx[faceIdx];
   poly->clut = gGfxClutIds[gfx];
   poly->tpage = gGfxTPageIds[gfx];
   poly->code = GPU_CODE_POLY_FT4;
   AddPrim(ot + OT_SIZE - otz, poly);
}
s32 GetBestViewOfTarget(s8 z, s8 x, s32 param_3) {
   return (s32)z + (s32)x + param_3;
}
int main(void) {
   u32 ot[1024] = {0};
   gGfxClutIds[641] = 287; gGfxTPageIds[641] = 18;
   gGfxClutIds[643] = 301; gGfxTPageIds[643] = 23;
   gMapRowPointers[8][19].gfx[0] = 641;
   gMapRowPointers[11][11].gfx[0] = 643;
   RenderMapTile(ot, &gMapRowPointers[8][19], 0);
   RenderEdgeMapTile(ot, &gMapRowPointers[8][19], 0);
   RenderOverheadMapTile(ot, &gMapRowPointers[11][11], 0);
   return 0;
}
'''


class RendererSmokeTests(unittest.TestCase):
    def test_generated_code_compiles_and_emits_two_jsonl_events(self):
        compiler = shutil.which('gcc') or shutil.which('cc')
        if not compiler:
            self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'graphics_trace.c'
            exe = Path(temp) / 'graphics_trace'
            src.write_text(instrument(C_FIXTURE), encoding='utf-8')
            subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-DVH_TRACE_MAP02_DRAW', str(src), '-o', str(exe)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual([(v['z'], v['x'], v['gfx']) for v in records],
                         [(8, 19, 641), (11, 11, 643)])
        self.assertEqual([(v['clut'], v['tpage']) for v in records],
                         [(287, 18), (301, 23)])
        self.assertEqual([v['stage'] for v in records], ['draw', 'draw'])
        self.assertEqual(len(records), 2)


if __name__ == '__main__':
    unittest.main()
