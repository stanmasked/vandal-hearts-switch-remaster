"""Exercise actual generated C trace printf output through the JSONL tools.

This is a synthetic tile harness, not an original-game capture. The three C
emitters and the loader observation are extracted from the production patch
generator rather than reimplemented as Python JSON fixtures.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.extract_map02_trace import extract_trace_text
from tools.make_map02_trace_patch import instrument_graphics, instrument_loader
from tools.verify_map02_trace import evaluate_trace, parse_trace_text

from test_make_map02_trace_patch import GRAPHICS, LOADER


C_PREFIX = r"""
#include <stdio.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    short gfx[18];
    unsigned char faceCt;
} MapTileModel;
typedef struct {
    unsigned char u0, v0;
    uint16_t clut, tpage;
} POLY_FT4;
static struct {
    int mapNum;
    unsigned int frameCounter;
} gState = {11, 12};
static MapTileModel tiles[22][28];
static MapTileModel *gMapRowPointers[22];
static MapTileModel *gMapDataPtr = &tiles[0][0];
"""

C_MAIN = r"""
int main(int argc, char **argv) {
    int i;
    int is_dat = argc > 1 && strcmp(argv[1], "dat") == 0;
    int is_empty = argc > 1 && strcmp(argv[1], "empty") == 0;
    POLY_FT4 poly_a = {240, 192, 287, 18};
    POLY_FT4 poly_b = {240, 208, 301, 23};
    for (i = 0; i < 22; ++i) gMapRowPointers[i] = tiles[i];
    tiles[8][19].faceCt = 1;
    tiles[8][19].gfx[0] = is_dat ? 498 : 641;
    tiles[11][11].faceCt = is_empty ? 0 : 1;
    tiles[11][11].gfx[0] = is_dat ? 550 : 643;
    puts("PC-port synthetic boot diagnostic: NOT original game output");
__LOADER_HOOK__
    VH_Map02TraceVisit(&tiles[8][19], "normal");
    VH_Map02TraceDraw(&tiles[8][19], 0, tiles[8][19].gfx[0], &poly_a, "normal");
    VH_Map02TraceVisit(&tiles[11][11], "normal");
    if (!is_empty) {
        VH_Map02TraceSkip(&tiles[11][11], 0, tiles[11][11].gfx[0],
                          "normal", "backface");
        ++gState.frameCounter;
        VH_Map02TraceVisit(&tiles[11][11], "edge");
        VH_Map02TraceDraw(&tiles[11][11], 0, tiles[11][11].gfx[0],
                           &poly_b, "edge");
    }
    return 0;
}
"""


def generated_emitter_source():
    modified = instrument_graphics(GRAPHICS)
    start = modified.index("/* Called only for a face that reached AddPrim")
    end = modified.index("\n#endif", start)
    helpers = modified[start:end]
    loader = instrument_loader(LOADER)
    probe = loader.index("/* The resource is named M_MAP02")
    start = loader.rfind("#if defined(PC_FEAT) && defined(VH_TRACE_MAP02)", 0, probe)
    end = loader.index("#endif", probe) + len("#endif")
    hook = loader[start:end]
    return C_PREFIX + "\n" + helpers + "\n" + C_MAIN.replace("__LOADER_HOOK__", hook)


class GeneratedCTraceBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("gcc") or shutil.which("cc")
        if not cls.compiler:
            raise unittest.SkipTest("C compiler unavailable")

    def test_c_emitted_prs_and_dat_traces_pass_both_clis(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "generated_map02_emitter.c"
            binary = root / "generated_map02_emitter"
            source.write_text(generated_emitter_source(), encoding="utf-8")
            subprocess.run(
                [self.compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-DPC_FEAT", "-DVH_TRACE_MAP02", str(source), "-o", str(binary)],
                check=True, capture_output=True, text=True,
            )
            for kind, expected in (("prs", "PRS"), ("dat", "DAT")):
                with self.subTest(kind=kind):
                    raw = subprocess.run(
                        [str(binary), kind], capture_output=True, text=True, check=True
                    ).stdout
                    self.assertIn("NOT original game output", raw)
                    captured = extract_trace_text(raw)
                    self.assertEqual(len(captured), 8)
                    self.assertEqual([e["stage"] for e in captured],
                                     ["post_load", "post_load", "visit", "draw",
                                      "visit", "skip", "visit", "draw"])
                    extraction = subprocess.run(
                        [sys.executable, "-m", "tools.extract_map02_trace",
                         "-", "--require-complete"],
                        input=raw, capture_output=True, text=True
                    )
                    self.assertEqual(extraction.returncode, 0, extraction.stderr)
                    self.assertEqual(parse_trace_text(extraction.stdout), captured)
                    report = evaluate_trace(captured)
                    self.assertEqual(report["errors"], [])
                    self.assertEqual(report["post_load_overall_variant"], expected)
                    self.assertEqual(report["draw_overall_variant"], expected)
                    self.assertEqual(report["observations"][1]["skip_reasons"], ["backface"])
                    self.assertEqual(report["observations"][1]["visit_paths"], ["edge", "normal"])
                    self.assertEqual(report["observations"][0]["draw_metadata"]["clut"], 287)
                    trace = root / (kind + ".jsonl")
                    trace.write_text(extraction.stdout, encoding="utf-8")
                    validation = subprocess.run(
                        [sys.executable, "-m", "tools.verify_map02_trace",
                         str(trace), "--require-uniform-variant"],
                        capture_output=True, text=True
                    )
                    self.assertEqual(validation.returncode, 0, validation.stderr)
                    self.assertEqual(json.loads(validation.stdout)["draw_overall_variant"],
                                     expected)

    def test_trace_events_survive_abrupt_c_exit_without_stdio_shutdown(self):
        # With stdout piped, printf may be block buffered. _Exit skips
        # stdio cleanup, proving the generated event hooks flush explicitly.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "abrupt_emitter.c"
            executable = root / "abrupt_emitter"
            program = generated_emitter_source().replace(
                "#include <stdio.h>", "#include <stdio.h>\n#include <stdlib.h>", 1
            )
            self.assertEqual(program.count("    return 0;\n}"), 1)
            program = program.replace("    return 0;\n}", "    _Exit(0);\n}", 1)
            source.write_text(program, encoding="utf-8")
            subprocess.run(
                [self.compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-DPC_FEAT", "-DVH_TRACE_MAP02",
                 str(source), "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            result = subprocess.run(
                [str(executable), "prs"], capture_output=True, text=True, check=True
            )
            captured = extract_trace_text(result.stdout)
            self.assertEqual(len(captured), 8)
            self.assertEqual(
                [event["stage"] for event in captured],
                ["post_load", "post_load", "visit", "draw",
                 "visit", "skip", "visit", "draw"],
            )
            self.assertEqual(evaluate_trace(captured)["errors"], [])

    def test_zero_face_c_capture_reports_missing_submission_not_visibility(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "emitter.c"
            binary = root / "emitter"
            source.write_text(generated_emitter_source(), encoding="utf-8")
            subprocess.run(
                [self.compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-DPC_FEAT", "-DVH_TRACE_MAP02", str(source), "-o", str(binary)],
                check=True, capture_output=True, text=True,
            )
            raw = subprocess.run(
                [str(binary), "empty"], capture_output=True, text=True, check=True
            ).stdout
            report = evaluate_trace(extract_trace_text(raw))
            self.assertEqual(report["observations"][1]["draw_status"],
                             "no_faces_in_observed_passes")
            self.assertIn("missing draw observation for (11, 11, 0)", report["errors"])
            self.assertIn("missing post_load observation for (11, 11, 0)", report["errors"])


if __name__ == "__main__":
    unittest.main()
