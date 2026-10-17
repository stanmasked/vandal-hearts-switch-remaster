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
from tools.verify_map02_dda_rejected_edges import validate
from tools.audit_map02_independent_dda_journals import audit, CANDIDATE_FILE, SPAN_FILE

PREFIX = r"""
#include <stdio.h>
#include <stddef.h>
#include <string.h>
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
    if (argc != 2 && !(argc == 3 && (strcmp(argv[2], "fill") == 0 || strcmp(argv[2], "single") == 0))) return 2;
    vh_pixel_sample_dir = argv[1];
#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE)
    vh_pixel_sample_y = 9;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 4);
    if (argc == 3 && strcmp(argv[2], "single") == 0) return 0;
    vh_pixel_sample_y = 16;
    VH_Map02RejectedEdges(&cx, 16, 10, 20, 5);
    VH_Map02RejectedEdges(&cx, 16, 10, 20, 6);
    vh_pixel_sample_y = 9;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 7);
    rc.target = 1;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 7);
    rc.target = 0;
    vh_pixel_sample_active = 0;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 7);
    vh_pixel_sample_active = 1;
    vh_sample_scope_active = 0;
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 7);
    vh_sample_scope_active = 1;
    VH_Map02RejectedEdges(&cx, 10, 10, 20, 7);
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 5);
    VH_Map02RejectedEdges(&cx, 9, 10, 20, 99);
    if (argc == 3) {
        int i;
        vh_pixel_sample_y = 9;
        for (i = 0; i < 100; ++i)
            VH_Map02RejectedEdges(&cx, 9, 10, 20, 7);
    }
#endif
    return 0;
}
"""
FLAGS = ["-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_PUTPIXEL_SCOPE",
         "-DVH_MAP02_RASTER_SKIP_TRACE", "-DVH_MAP02_DDA_VERTICAL_TRACE"]

class CandidateC11Tests(unittest.TestCase):
    def test_compile_run_and_fail_closed(self):
        requested = os.environ.get("CC") or "cc"
        cc = shutil.which(requested)
        if not cc:
            self.fail(f"required C compiler unavailable: {requested}")
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
                for invalid_arg in ("invalid", "f", ""):
                    invalid = subprocess.run([str(target), str(root), invalid_arg],
                                             capture_output=True, text=True)
                    self.assertEqual(invalid.returncode, 2)
                journal = root / "dda-rejected-edge-candidates.jsonl"
                if enabled:
                    self.assertTrue(journal.exists())
                    records = validate(journal.read_bytes())
                    # This purpose-built four-branch fixture switches
                    # the selected Y halfway through one synthetic process;
                    # a genuine single-sample capture must NOT accept it.
                    with self.assertRaisesRegex(ValueError, "mixed DDA capture"):
                        audit(root)
                    single_dir = root / "single"
                    single_dir.mkdir()
                    subprocess.run([str(target), str(single_dir), "single"],
                                   check=True, capture_output=True, text=True)
                    envelope = audit(single_dir)
                    self.assertEqual(envelope["files"][CANDIDATE_FILE]["event_count"], 1)
                    self.assertIsNone(envelope["files"][SPAN_FILE]["event_count"])
                    self.assertTrue(envelope["single_sample_envelope_consistent"])
                    self.assertFalse(envelope["rejected_triangle_pixel_coverage_verified"])
                    self.assertEqual([row["reason"] for row in records], [4, 5, 6, 7])
                    self.assertEqual([row["y"] for row in records], [9, 16, 16, 9])
                    self.assertEqual([row["step"] for row in records], [0, 1, 2, 3])
                    self.assertEqual([(row["clip_t"], row["clip_b"]) for row in records], [(10, 15)] * 4)
                    self.assertTrue(all((row["y"] < row["clip_t"] if row["reason"] in (4, 7) else row["y"] > row["clip_b"]) for row in records))
                    self.assertEqual(len(records), 4)
                    self.assertEqual({row["stage"] for row in records}, {"rejected_edge_candidate"})
                    with self.assertRaisesRegex(ValueError, "reason inconsistent"):
                        validate(journal.read_bytes().replace(b'"reason":4', b'"reason":5', 1))
                    with self.assertRaises(ValueError):
                        validate(journal.read_bytes()[:-1])
                    cap_dir = root / "cap"
                    cap_dir.mkdir()
                    subprocess.run([str(target), str(cap_dir), "fill"],
                                   check=True, capture_output=True, text=True)
                    capped = (cap_dir / journal.name).read_bytes()
                    self.assertEqual(len(capped.splitlines()), 64)
                    with self.assertRaisesRegex(ValueError, "truncation"):
                        validate(capped)
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
