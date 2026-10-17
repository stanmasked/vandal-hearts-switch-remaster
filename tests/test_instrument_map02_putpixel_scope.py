"""Synthetic mutation tests for actual same-binary DrawOTag/PutPixel scope."""
import tempfile
from pathlib import Path
import unittest

from test_instrument_map02_native_putpixel import SOURCE
from tools.instrument_map02_putpixel_scope import (
    FLAG, scope_gpu, scope_raster, prepare,
)

GPU = r'''
#include <stdio.h>
/* ---- GetTPage / GetClut (psx-spx "Texpage Attribute" / "Clut Attribute") */
int LoadImage(RECT *rect, unsigned int *p) {
    if (rect->w > 0 && rect->h > 0) TrcWrite('L', rect, 8, src, (u32)(rect->w * rect->h * 2));
    HiresMirrorRect(rect->x, rect->y, rect->w, rect->h);   /* keep the hi-res FB in sync (backgrounds) */
}
int MoveImage(RECT *rect, int x, int y) {
    { int xy[2]; xy[0] = x; xy[1] = y; TrcWrite('M', rect, 8, xy, 8); }
    HiresMirrorRect(x, y, rect->w, rect->h);   /* keep the hi-res FB in sync (VRAM->VRAM blit) */
}
int ClearImage(RECT *rect, u_char r, u_char g, u_char b) {
    { unsigned char rgb[3]; rgb[0] = r; rgb[1] = g; rgb[2] = b; TrcWrite('C', rect, 8, rgb, 3); }
    FillRectRaw(rect->x, rect->y, rect->w, rect->h, r, g, b);
}
void DrawOTag(unsigned int *p) {
    unsigned long walkSteps = 0;
    if (!isBucket) {
            switch (type) {
            default:
                break;
            }
        }
        nextTok = rawTagOfCur;
    TrcFrameEnd();
}
'''

# The full PC libgpu instrumenter checks further exact hooks and ordering;
# these tests run against this constructed template only to exercise new
# failure modes. CI additionally generates from real pinned source + objects.
class ScopeGenerationTests(unittest.TestCase):
    def test_raster_scopes_only_real_native_putpixel(self):
        output=scope_raster(SOURCE)
        self.assertIn("VH_Map02PixelScopeSet",output)
        self.assertIn("VH_Map02PixelScopeClear",output)
        self.assertIn("VH_MAP02_PUTPIXEL_FRAME",output)
        self.assertIn("vh_pixel_sample_active && vh_sample_scope_active",output)
        self.assertIn("primitive_ordinal",output)
        self.assertIn("primitive_type",output)
        self.assertIn("vh_sample_scope_frame",output)
        self.assertIn("frame == vh_sample_target_frame",output)
        self.assertEqual(output.count("WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);"),1)
        self.assertNotIn("VH_MAP02_PUTPIXEL_SAMPLE",output)
        with self.assertRaisesRegex(ValueError, "already installed"):
            scope_raster(output)

    def test_real_gpu_draw_and_capture_hooks_share_single_primitive_walk(self):
        from tools.instrument_map02_gpu_native_events import instrument
        # Artificially complete the other native recorder's source anchors.
        # The raw native generator is itself independently regression tested.
        combined=scope_gpu(instrument(GPU))
        self.assertIn('VH_CaptureEvent("before","draw"',combined)
        self.assertIn('VH_CaptureEvent("after","draw"',combined)
        self.assertIn("VH_Map02PixelScopeSet",combined)
        self.assertIn("VH_Map02PixelScopeClear",combined)
        self.assertIn("vh_sample_primitive_ordinal++",combined)
        with self.assertRaisesRegex(ValueError, "already injected"):
            scope_gpu(combined)
        with self.assertRaisesRegex(ValueError, "end native primitive scope"):
            scope_gpu(GPU)

    def test_wrong_sha_and_preexisting_destination_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            gpu=root/"libgpu.c"
            raster=root/"pc_raster.c"
            gpu.write_text(GPU)
            raster.write_text(SOURCE)
            destination=root/"build"
            with self.assertRaisesRegex(ValueError, "Git blob"):
                prepare(gpu,raster,destination)
            self.assertFalse(destination.exists())
            destination.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(gpu,raster,destination)


if __name__=="__main__":
    unittest.main()
