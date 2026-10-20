"""Compile and execute the opt-in C span recorder in a synthetic harness.

This tests the generated C hook ABI, NOT the original upstream C raster.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.instrument_map02_dda_span import instrument_span
from tools.instrument_map02_raster_skips import SPAN_ANCHOR
from tools.verify_map02_dda_native_spans import parse_native_spans
from tools.audit_map02_independent_dda_journals import audit, CANDIDATE_FILE, SPAN_FILE

C_TEMPLATE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
typedef struct { int target; } RenderCtx;
typedef struct {
    RenderCtx *rc;
    int clipL, clipR, clipT, clipB;
} DdaCtx;
typedef struct { int unused; } DdaUV;
static int vh_pixel_sample_active = 1;
static int vh_sample_scope_active = 1;
static int vh_pixel_sample_y = 12;
static const char *vh_pixel_sample_dir;
static unsigned vh_sample_scope_frame = 3;
static unsigned vh_sample_scope_ordinal = 9;
static int vh_sample_scope_type = 2;
static void VH_PixelSampleInit(void) {}
static void VH_Map02SkipAt(int x, int y, int reason) {
    (void)x; (void)y; (void)reason;
}
REPLACE_SPAN
    (void)cx; (void)y; (void)x_start; (void)x_bound; (void)uv;
}
int main(int argc, char **argv) {
    RenderCtx rc = {0};
    DdaCtx cx = {&rc, 5, 25, 10, 15};
    DdaUV uv = {0};
    if (argc != 2) return 2;
    vh_pixel_sample_dir = argv[1];
    dda_span(&cx, 12, 10, 20, uv);
    dda_span(&cx, 13, 10, 20, uv);
    rc.target = 1;
    dda_span(&cx, 12, 10, 20, uv);
    return 0;
}
'''


class NativeSpanCompileTests(unittest.TestCase):
    def test_c11_enabled_and_disabled_probe(self):
        cc = shutil.which(os.environ.get("CC", "")) or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not cc:
            self.skipTest("No native C compiler")
        generated = instrument_span(C_TEMPLATE.replace("REPLACE_SPAN", SPAN_ANCHOR))
        flags = ["-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_PUTPIXEL_SCOPE",
                 "-DVH_MAP02_RASTER_SKIP_TRACE", "-DVH_MAP02_DDA_VERTICAL_TRACE"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "probe.c"
            source.write_text(generated, encoding="utf-8")
            for enabled in (False, True):
                output = root / ("probe_on" if enabled else "probe_off")
                args = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-Wno-unused-variable"]
                args += flags + ["-DVH_MAP02_DDA_SPAN_TRACE"] if enabled else []
                subprocess.run(args + [str(source), "-o", str(output)],
                               check=True, capture_output=True, text=True)
                subprocess.run([str(output), str(root)], check=True,
                               capture_output=True, text=True)
                log = root / "dda-native-spans.jsonl"
                if enabled:
                    raw = log.read_bytes()
                    validated = parse_native_spans(raw)
                    envelope = audit(root)
                    self.assertEqual(envelope["files"][SPAN_FILE]["event_count"], 1)
                    self.assertIsNone(envelope["files"][CANDIDATE_FILE]["event_count"])
                    self.assertFalse(envelope["retail_map02_frame_verified"])
                    self.assertEqual(len(validated), 1)
                    self.assertEqual((validated[0].x_start, validated[0].x_bound), (10, 20))
                    rows = [json.loads(line) for line in raw.splitlines()]
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["x_start"], 10)
                    self.assertEqual(rows[0]["x_bound"], 20)
                    self.assertEqual(rows[0]["primitive_ordinal"], 9)
                    self.assertEqual(rows[0]["frame"], 3)
                    self.assertEqual(rows[0]["clip_t"], 10)
                    self.assertEqual(rows[0]["clip_b"], 15)
                    # Mutate bytes emitted by the compiled C producer, not
                    # hand-constructed fixtures; the strict consumer must fail.
                    for mutated in (
                        raw.replace(b'"x_bound":20', b'"x_bound":9'),
                        raw.replace(b'"frame":3', b'"frame":true'),
                        raw.rstrip(b"\n"),
                        raw.replace(b'"step":0', b'"step":1'),
                        raw + raw,
                    ):
                        self.assertNotEqual(mutated, raw, "mutation did not change captured bytes")
                        with self.subTest(mutated=mutated[:100]):
                            with self.assertRaises(ValueError):
                                parse_native_spans(mutated)
                else:
                    self.assertFalse(log.exists())

    def test_incomplete_flags_fail_closed(self):
        cc = shutil.which(os.environ.get("CC", "")) or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not cc:
            self.skipTest("No native C compiler")
        generated = instrument_span(C_TEMPLATE.replace("REPLACE_SPAN", SPAN_ANCHOR))
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "probe.c"
            file.write_text(generated, encoding="utf-8")
            result = subprocess.run([cc, "-std=c11", "-DVH_MAP02_DDA_SPAN_TRACE",
                                     "-c", str(file), "-o", str(Path(temp) / "probe.o")],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires all native GPU", result.stderr)


if __name__ == "__main__":
    unittest.main()
