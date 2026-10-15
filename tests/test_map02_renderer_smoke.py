"""Host-only C smoke check for generated map02 trace (synthetic GPU and tiles)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_renderer import instrument
from tools.extract_map02_trace import extract_trace_text
from tools.verify_map02_trace import evaluate_trace

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
    def _run_compiled_renderer(self, fixture_source):
        compiler = shutil.which('gcc') or shutil.which('cc')
        if not compiler:
            self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'graphics_trace.c'
            exe = Path(temp) / 'graphics_trace'
            src.write_text(instrument(fixture_source), encoding='utf-8')
            subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-DVH_TRACE_MAP02_DRAW', str(src), '-o', str(exe)],
                           check=True, capture_output=True, text=True)
            return subprocess.run([str(exe)], check=True,
                                  capture_output=True, text=True).stdout

    def test_compiled_renderer_to_extractor_to_validator_pipeline(self):
        """Real compiled C draw emissions + synthetic post-load facts (no disc)."""
        draw_stdout = self._run_compiled_renderer(C_FIXTURE)
        post_load = (
            '{"z":8,"x":19,"face":0,"stage":"post_load","gfx":641}\\n'
            '{"z":11,"x":11,"face":0,"stage":"post_load","gfx":643}\\n'
        )
        noisy_capture = "PC boot output\\n" + post_load + "GPU initialized\\n" + draw_stdout
        observations = extract_trace_text(noisy_capture)
        report = evaluate_trace(observations)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["post_load_overall_variant"], "PRS")
        self.assertEqual(report["draw_overall_variant"], "PRS")
        self.assertEqual([row["draw_observation_count"] for row in report["observations"]], [1, 1])

    def test_compiled_renderer_detects_post_load_draw_gfx_divergence(self):
        """A deliberately modified synthetic draw sample must fail consistency."""
        modified = C_FIXTURE.replace(
            'gMapRowPointers[8][19].gfx[0] = 641;',
            'gMapRowPointers[8][19].gfx[0] = 498;',
        )
        self.assertNotEqual(modified, C_FIXTURE)
        draw_stdout = self._run_compiled_renderer(modified)
        header = (
            '{"z":8,"x":19,"face":0,"stage":"post_load","gfx":641}\\n'
            '{"z":11,"x":11,"face":0,"stage":"post_load","gfx":643}\\n'
        )
        report = evaluate_trace(extract_trace_text(header + draw_stdout))
        self.assertTrue(any("changed between loading and drawing" in error
                            for error in report["errors"]))
        self.assertEqual(report["observations"][0]["draw_variant"], "DAT")

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
