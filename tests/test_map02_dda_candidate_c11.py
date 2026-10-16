"""Compile the generated C rejected-edge helper with and without opt-in flags.

Synthetic executable only, not a pinned original-GPU build.
"""
import shutil
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

from tools.instrument_map02_dda_rejected_edges import HELPER

PREFIX = r"""
#include <stdio.h>
#include <stddef.h>
typedef struct { int target; } RenderCtx;
typedef struct { RenderCtx *rc; int clipT, clipB; } DdaCtx;
typedef struct { int unused; } DdaPart;
typedef struct { int unused; } DdaUV;
static int vh_pixel_sample_active = 1;
static int vh_sample_scope_active = 1;
static int vh_pixel_sample_y = 9;
static const char *vh_pixel_sample_dir;
static unsigned vh_sample_scope_frame = 3, vh_sample_scope_ordinal = 9;
static void VH_PixelSampleInit(void) {}
static int dda_unfp(long long value) { return (int)value; }
"""
END = r"""
int main(int argc, char **argv) {
    RenderCtx rc = {0};
    DdaCtx cx = {&rc, 10, 15};
    if (argc != 2) return 2;
    vh_pixel_sample_dir = argv[1];
#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE)
    vh_pixel_sample_y = 9;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 4);
    vh_pixel_sample_y = 16;
    VH_Map02RejectedEdges(&cx, 16, 10, 20, 5);
    VH_Map02RejectedEdges(&cx, 16, 10, 20, 6);
    vh_pixel_sample_y = 9;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 7);
#endif
    return 0;
}
"""
FLAGS = ["-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_PUTPIXEL_SCOPE",
         "-DVH_MAP02_RASTER_SKIP_TRACE", "-DVH_MAP02_DDA_VERTICAL_TRACE"]

class CandidateC11Tests(unittest.TestCase):
    def test_compile_run_and_fail_closed(self):
        cc = shutil.which(os.environ.get("CC", "")) or shutil.which("cc")
        if not cc:
            self.skipTest("C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "candidate.c"
            source.write_text(PREFIX + HELPER + END, encoding="utf-8")
            for enabled in (False, True):
                target = root / ("enabled" if enabled else "disabled")
                cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-function", "-Wno-unused-variable"] + FLAGS
                if enabled:
                    cmd += ["-DVH_MAP02_DDA_REJECTED_EDGES_TRACE"]
                subprocess.run(cmd + [str(source), "-o", str(target)],
                               check=True, capture_output=True, text=True)
                subprocess.run([str(target), str(root)], check=True,
                               capture_output=True, text=True)
                journal = root / "dda-rejected-edge-candidates.jsonl"
                if enabled:
                    self.assertTrue(journal.exists())
                    records = [__import__("json").loads(line) for line in journal.read_text().splitlines()]
                    self.assertEqual([row["reason"] for row in records], [4, 5, 6, 7])
                    self.assertEqual([row["y"] for row in records], [9, 16, 16, 9])
                    self.assertEqual([row["step"] for row in records], [0, 1, 2, 3])
                else:
                    self.assertFalse(journal.exists())
            bad = subprocess.run(
                [cc, "-std=c11", "-DVH_MAP02_DDA_REJECTED_EDGES_TRACE",
                 "-c", str(source), "-o", str(root / "bad.o")],
                capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("requires original native diagnostic chain", bad.stderr)

if __name__ == "__main__":
    unittest.main()
