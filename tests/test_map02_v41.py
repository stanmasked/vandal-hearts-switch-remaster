#!/usr/bin/env python3
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_map02_v41 import patch_header, patch_gpu, patch_raster
from verify_map02_v41 import analyze, parse_line

HEADER = "    unsigned int v40Token, v40Gfx, v40Route;\n"
GPU = ("            rcn.v40Token = rcn.v40Gfx = rcn.v40Route = 0;\n"
       "            rch = rcn; rch.target = 1; rch.scale = hiScale;\n")
RASTER = """    hp->rc = *rch;
    RenderCtx rc = hp->rc;
    fprintf(stderr, "[v39-terrain-dda] token=%u gfx=%u route=%u x=%d y=%d u=%d v=%d raw=%u draw=%d semi=%d abr=%d\\n",
                    VH_Map02V39Token, VH_Map02V39Gfx, VH_Map02V39Route,
                    current_x, y, su, sv, draw ? (unsigned)texel : 0u,
                    draw, cx->semiTrans, cx->abr);
    fprintf(stderr, "[v40-terrain-hires] token=%u gfx=%u route=%u x=%d y=%d u=%d v=%d raw=%u draw=%d semi=%d abr=%d scale=%d\\n",
                    cx->rc->v40Token, cx->rc->v40Gfx, cx->rc->v40Route,
                    current_x, y, su, sv, draw ? (unsigned)texel : 0u,
                    draw, cx->semiTrans, cx->abr, cx->rc->scale);
"""


def ot(f=1, token=12, gfx=641, route=1, clut=31786):
    return (f"[v39-terrain-ot] f={f} token={token} gfx={gfx} route={route} "
            f"tpage=5 clut={clut}\n")


def pixel(kind="v39-terrain-dda", f=1, token=12, gfx=641,
          route=1, raw=32767, draw=1, scale=2):
    line = (f"[{kind}] f={f} token={token} gfx={gfx} route={route} "
            f"x=64 y=64 u=8 v=9 raw={raw} draw={draw} semi=1 abr=2")
    if kind == "v40-terrain-hires":
        line += f" scale={scale}"
    return line + "\n"


class TestPatch(unittest.TestCase):
    def test_header_adds_field(self):
        self.assertIn("v41Frame", patch_header(HEADER))

    def test_gpu_frame_snapshot_before_hires_copy(self):
        s = patch_gpu(GPU)
        self.assertIn("rcn.v41Frame = s_drawFrame;", s)
        self.assertLess(s.index("rcn.v41Frame ="), s.index("rch = rcn;"))

    def test_raster_events_have_frame(self):
        s = patch_raster(RASTER)
        self.assertIn("[v39-terrain-dda] f=%u token=", s)
        self.assertIn("[v40-terrain-hires] f=%u token=", s)
        self.assertEqual(s.count("cx->rc->v41Frame"), 2)
        self.assertIn("hp->rc = *rch;", s)

    def test_duplicate_patches_fail(self):
        for fn, src in [(patch_header, HEADER), (patch_gpu, GPU),
                        (patch_raster, RASTER)]:
            with self.assertRaises(ValueError):
                fn(fn(src))

    def test_missing_deferred_context_fails(self):
        with self.assertRaises(ValueError):
            patch_raster(RASTER.replace("hp->rc = *rch;", ""))


class TestCorrelation(unittest.TestCase):
    def report(self, *lines):
        return analyze(lines)

    def test_correlates_same_frame_and_token(self):
        r = self.report(ot(), pixel(), pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "provenance_correlated")
        self.assertEqual(r["paired_primitive_count"], 1)
        self.assertFalse(r["pixel_equivalence_proven"])
        self.assertFalse(r["gameplay_execution_proven"])

    def test_interleaved_threads_need_not_log_in_order(self):
        r = self.report(pixel("v40-terrain-hires"), pixel(), ot())
        self.assertEqual(r["status"], "provenance_correlated")

    def test_recycled_token_separate_frames(self):
        r = self.report(
            ot(f=1, token=12, gfx=641), pixel(f=1, token=12, gfx=641),
            pixel("v40-terrain-hires", f=1, token=12, gfx=641),
            ot(f=2, token=12, gfx=643), pixel(f=2, token=12, gfx=643),
            pixel("v40-terrain-hires", f=2, token=12, gfx=643),
        )
        self.assertEqual(r["paired_primitive_count"], 2)
        self.assertEqual(r["frames_with_events"], 2)

    def test_recycled_token_wrong_frame_identity_rejected(self):
        r = self.report(ot(f=1, gfx=641), ot(f=2, gfx=643),
                        pixel(f=2, gfx=641),
                        pixel("v40-terrain-hires", f=2, gfx=643))
        self.assertEqual(r["status"], "inconsistent")
        self.assertIn("mismatched native origin", r["errors"][0])

    def test_dangling_frame_sample_is_not_attached_by_token(self):
        r = self.report(ot(f=1), pixel(f=2),
                        pixel("v40-terrain-hires", f=1))
        self.assertEqual(r["status"], "inconsistent")
        self.assertIn("orphan native sample", r["errors"][0])

    def test_gfx_mismatch_rejected(self):
        r = self.report(ot(), pixel(gfx=242),
                        pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "inconsistent")

    def test_route_mismatch_rejected(self):
        r = self.report(ot(), pixel(route=2),
                        pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "inconsistent")

    def test_duplicate_ot_event_rejected(self):
        r = self.report(ot(), ot(), pixel(), pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "inconsistent")

    def test_unframed_legacy_trace_refused(self):
        r = self.report(ot(), pixel().replace("f=1 ", ""),
                        pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "inconsistent")
        self.assertIn("missing=['f']", r["errors"][0])

    def test_one_sided_sample_is_insufficient(self):
        r = self.report(ot(), pixel())
        self.assertEqual(r["status"], "insufficient_evidence")
        self.assertEqual(r["native_primitive_count"], 1)
        self.assertEqual(r["hires_primitive_count"], 0)

    def test_no_sample_is_insufficient(self):
        r = self.report(ot())
        self.assertEqual(r["status"], "insufficient_evidence")
        self.assertEqual(r["unsampled_ot_primitive_count"], 1)

    def test_native_and_hires_on_different_primitive_not_paired(self):
        r = self.report(ot(token=12), ot(token=13),
                        pixel(token=12),
                        pixel("v40-terrain-hires", token=13))
        self.assertEqual(r["status"], "insufficient_evidence")
        self.assertEqual(r["paired_primitive_count"], 0)

    def test_ignore_unrelated_runtime_logs(self):
        r = self.report("ordinary GPU log\n", "[debug] unrelated\n",
                        ot(), pixel(), pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "provenance_correlated")

    def test_opaque_vs_zero_textures(self):
        ok = self.report(ot(), pixel(raw=0, draw=0),
                         pixel("v40-terrain-hires", raw=0, draw=0))
        self.assertEqual(ok["status"], "provenance_correlated")
        bad = self.report(ot(), pixel(raw=0, draw=1),
                          pixel("v40-terrain-hires"))
        self.assertEqual(bad["status"], "inconsistent")

    def test_reject_invalid_route_scale_and_uv(self):
        for bad in (pixel(route=4), pixel("v40-terrain-hires", scale=0),
                    pixel().replace("u=8 ", "u=256 ")):
            with self.subTest(bad=bad):
                r = self.report(ot(), bad, pixel("v40-terrain-hires"))
                self.assertEqual(r["status"], "inconsistent")

    def test_reject_duplicate_and_unknown_fields(self):
        for bad in (pixel().replace(" u=8 ", " u=8 u=8 "),
                    pixel().replace(" u=8 ", " w=8 ")):
            with self.subTest(bad=bad):
                self.assertEqual(self.report(ot(), bad)["status"], "inconsistent")

    def test_long_record_rejected(self):
        self.assertEqual(self.report(ot(), "A" * 16385)["status"], "inconsistent")

    def test_status_when_no_trace(self):
        r = self.report("unrelated log line\n")
        self.assertEqual(r["status"], "insufficient_evidence")
        self.assertEqual(r["frames_with_events"], 0)

    def test_negative_screen_coordinates_allowed(self):
        r = self.report(ot(), pixel().replace(" x=64 ", " x=-1 "),
                        pixel("v40-terrain-hires"))
        self.assertEqual(r["status"], "provenance_correlated")

    def test_frame_token_pair_is_stable_and_ordered(self):
        r = self.report(ot(f=3, token=27), ot(f=1, token=2),
                        pixel(f=1, token=2), pixel("v40-terrain-hires", f=1, token=2),
                        pixel(f=3, token=27), pixel("v40-terrain-hires", f=3, token=27))
        self.assertEqual(r["examples_of_paired_frame_tokens"][0]["frame"], 1)
        self.assertEqual(r["examples_of_paired_frame_tokens"][1]["frame"], 3)

    def test_direct_line_parser(self):
        tag, fields = parse_line("syslog prefix " + ot(), 42)
        self.assertEqual(tag, "v39-terrain-ot")
        self.assertEqual(fields["gfx"], 641)


if __name__ == "__main__":
    unittest.main()
