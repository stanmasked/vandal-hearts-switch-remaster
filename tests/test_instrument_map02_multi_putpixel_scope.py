"""Asset-free mutation checks for two-word same-DrawOTag PC observer."""
import tempfile
from pathlib import Path
import unittest

from test_instrument_map02_native_putpixel import SOURCE
from test_instrument_map02_putpixel_scope import GPU
from tools.instrument_map02_multi_putpixel_scope import (
    FLAG, multi_gpu, multi_raster, prepare,
)


class NativeTwoWordScopeTests(unittest.TestCase):
    def test_two_coordinates_required_with_one_global_write_path(self):
        generated = multi_raster(SOURCE)
        self.assertIn('getenv("VH_MAP02_PUTPIXEL_X2")', generated)
        self.assertIn('getenv("VH_MAP02_PUTPIXEL_Y2")', generated)
        self.assertIn("x2 == vh_pixel_sample_x && y2 == vh_pixel_sample_y",generated)
        self.assertIn("vh_pixel_sample_x2 = (int)x2;", generated)
        self.assertIn("vh_pixel_sample_y2 = (int)y2;", generated)
        self.assertIn("vh_pixel_sample_count < VH_PIXEL_SAMPLE_MAX", generated)
        self.assertIn("vh_pixel_sample_count, vh_sample_scope_frame", generated)
        self.assertIn("VH_MAP02_PUTPIXEL_FRAME",generated)
        self.assertIn(f"#if defined({FLAG})", generated)
        self.assertEqual(generated.count(
            "WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);"), 1)
        self.assertNotIn("VH_MAP02_PUTPIXEL_SCOPE", generated)
        self.assertNotIn("VH_MAP02_PUTPIXEL_SAMPLE", generated)
        with self.assertRaisesRegex(ValueError, "already installed"):
            multi_raster(generated)

    def test_same_gpu_walk_and_native_snapshot_pairing(self):
        generated = multi_gpu(GPU)
        self.assertIn('VH_CaptureEvent("before","draw"', generated)
        self.assertIn('VH_CaptureEvent("after","draw"', generated)
        self.assertIn("VH_Map02PixelScopeSet", generated)
        self.assertIn("VH_Map02PixelScopeClear", generated)
        self.assertIn("vh_sample_primitive_ordinal++", generated)
        self.assertIn(f"#if defined({FLAG})",generated)
        self.assertNotIn("VH_MAP02_PUTPIXEL_SCOPE", generated)
        with self.assertRaisesRegex(ValueError, "already injected"):
            multi_gpu(generated)

    def test_drift_and_existing_destination_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "anchor"):
            multi_raster(SOURCE.replace(
                "static unsigned short s_vram[VRAM_H][VRAM_W];",
                "/* changed */"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, raster = root/"libgpu.c", root/"pc_raster.c"
            gpu.write_text(GPU)
            raster.write_text(SOURCE)
            target = root/"generated"
            with self.assertRaisesRegex(ValueError, "Git blob"):
                prepare(gpu, raster, target)
            self.assertFalse(target.exists())
            target.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(gpu, raster, target)


if __name__ == "__main__":
    unittest.main()
