#!/usr/bin/env python3
"""v40 patch-generator tests; native CI compiles the real upstream objects."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_map02_v40 import once, modify_header, modify_gpu, modify_raster

HEADER = """typedef struct {
    int scale;                        /* geometry x scale when target==1 (else effectively 1) */
} RenderCtx;
"""
GPU = """
            rcn.target = 0; rcn.scale = 1;
    rch = rcn; rch.target = 1; rch.scale = hiScale;
    VhMap02V39Tag v39Tag;
    if (something) {
                    VH_Map02V39Active = 1;
    }
    HiresAppendQuad(&rch, a, b, c, d, q->r0, q->g0, q->b0, 1, ...);
"""
RASTER = """
    HiresPrim *hp;
    hp->rc = *rch;
    hp->rc = *rch; /* rect path */
    RenderCtx rc = hp->rc;
    HiresRasterizeBand(s_hpool.band[id].clipY, s_hpool.band[id].clipH);
    /* V39 marker declaration: */
    VH_Map02V39Active
            if (draw) {                                      /* 0000h = transparent (skip, still step) */
"""


class TestV40(unittest.TestCase):
    def test_header_fields(self):
        s = modify_header(HEADER)
        self.assertIn("unsigned int v40Token, v40Gfx, v40Route;", s)
        self.assertIn("int scale;", s)

    def test_gpu_opt_in_only(self):
        s = modify_gpu(GPU)
        self.assertIn("rcn.v40Token = rcn.v40Gfx = rcn.v40Route = 0;", s)
        self.assertIn("rch.v40Token = nextTok;", s)
        self.assertIn("rch.v40Gfx = v39Tag.gfx;", s)
        self.assertIn("rch.v40Route = v39Tag.route;", s)
        self.assertEqual(s.count("rch.v40Token = nextTok;"), 1)

    def test_raster_reads_immutable_context(self):
        s = modify_raster(RASTER)
        self.assertIn("cx->rc->v40Token", s)
        self.assertIn("cx->rc->v40Gfx", s)
        self.assertIn("cx->rc->v40Route", s)
        self.assertNotIn("extern volatile unsigned VH_Map02V39Token;", s)
        self.assertEqual(s.count("hp->rc = *rch;"), 2)
        self.assertIn("RenderCtx rc = hp->rc;", s)

    def test_all_paths_reject_double_patch(self):
        for fn, fixture in [
            (modify_header, HEADER), (modify_gpu, GPU), (modify_raster, RASTER)
        ]:
            with self.assertRaises(ValueError):
                fn(fn(fixture))

    def test_refuse_changed_snapshot_contract(self):
        with self.assertRaisesRegex(ValueError, "snapshot contract"):
            modify_raster(RASTER.replace("hp->rc = *rch;", "hp->rc = shared_state;"))

    def test_refuse_missing_gpu_native_init(self):
        with self.assertRaisesRegex(ValueError, "initialize every primitive"):
            modify_gpu(GPU.replace("rcn.target = 0; rcn.scale = 1;", ""))

    def test_refuse_v39_missing(self):
        with self.assertRaisesRegex(ValueError, "v39"):
            modify_gpu(GPU.replace("VH_Map02V39Active = 1;", ""))
        with self.assertRaisesRegex(ValueError, "v39"):
            modify_raster(RASTER.replace("VH_Map02V39Active", ""))

    def test_duplicate_anchors_rejected(self):
        with self.assertRaises(ValueError):
            once("foo foo", "foo", "bar", "test")

    def test_sparse_native_and_hires_samples_separate(self):
        s = modify_raster(RASTER)
        self.assertIn("cx->rc->target &&", s)
        self.assertIn("!cx->hdPx", s)
        self.assertIn("(current_x & 63) == 0 && (y & 63) == 0", s)


if __name__ == "__main__":
    unittest.main()
