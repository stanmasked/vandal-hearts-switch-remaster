"""Synthetic source and host C regressions; not a real MAP02 capture."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_scoped_blend import (
    BLEND_CALL, HIRES, NATIVE, NATIVE_ANCHOR, PUT_SIGNATURE,
    WRITE_SIGNATURE, instrument,
)


def source_fixture():
    return r"""
#include <stddef.h>
#include <assert.h>
#define VRAM_W 8
#define VRAM_H 8
typedef struct RenderCtx { int target, scale; } RenderCtx;
static unsigned short s_vram[VRAM_H][VRAM_W];
static unsigned short s_hires[VRAM_W * VRAM_H * 4];
static int accurate_mode = 1;
static int AccurateEnabled(void) { return accurate_mode; }
static unsigned short BlendG1(unsigned fg, unsigned bg, int abr, int textured) {
    (void)abr; (void)textured;
    return (unsigned short)(fg ^ bg);
}
""" + WRITE_SIGNATURE + r"""
    (void)x; (void)y;
    if (semiTrans) {
        if (AccurateEnabled()) {
""" + BLEND_CALL + r"""
        } else {
            *px = c;
        }
    } else {
        *px = c;
    }
}
""" + PUT_SIGNATURE + r"""
    if (rc->target) {
        int W = VRAM_W * rc->scale, H = VRAM_H * rc->scale;
        if (x < 0 || x >= W || y < 0 || y >= H) return;
        """ + HIRES + r"""
        return;
    }
""" + NATIVE_ANCHOR + r"""
}
static int begins, blends, ends;
void vh_map02_probe_begin(int x, int y, unsigned short before,
                          unsigned short front, int abr, int semi,
                          int textured, int accurate) {
    (void)x; (void)y; (void)before; (void)front; (void)abr;
    (void)semi; (void)textured; (void)accurate;
    begins++;
}
void vh_map02_probe_blendg1(int x, int y, unsigned short fg,
                            unsigned short bg, unsigned short result,
                            int abr, int textured) {
    (void)x; (void)y; (void)fg; (void)bg; (void)result;
    (void)abr; (void)textured;
    blends++;
}
void vh_map02_probe_end(int x, int y, unsigned short after) {
    (void)x; (void)y; (void)after;
    ends++;
}
int main(void) {
    RenderCtx native = {0, 1}, hires = {1, 2};
    PutPixel(&native, 1, 1, 0x001f, 2, 1, 1);
    PutPixel(&hires, 1, 1, 0x001f, 2, 1, 1);
    accurate_mode = 0;
    PutPixel(&native, 1, 1, 0x002f, 2, 1, 1);
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    assert(begins == 2 && ends == 2 && blends == 1);
#else
    assert(begins == 0 && ends == 0 && blends == 0);
#endif
    return 0;
}
"""


class ScopedBlendSourceTests(unittest.TestCase):
    def test_single_native_scope_and_actual_blend(self):
        result = instrument(source_fixture())
        self.assertEqual(result.count("vh_map02_probe_begin(x, y"), 1)
        self.assertEqual(result.count("vh_map02_probe_blendg1(x, y"), 1)
        self.assertEqual(result.count("vh_map02_probe_end(x, y"), 1)
        self.assertIn("textured, 0);", result)
        self.assertIn("textured, 1);", result)
        self.assertIn("fg = (unsigned short)((unsigned)c | 0x8000u)", result)
        self.assertIn("unsigned short bg = *px;", result)
        self.assertIn("unsigned short result = BlendG1(fg, bg, abr, textured)", result)

    def test_rejects_drift_duplicates_and_prior_probes(self):
        source = source_fixture()
        bad = (source + BLEND_CALL,
               source.replace(NATIVE_ANCHOR, ""),
               source.replace(HIRES, ""),
               source.replace(WRITE_SIGNATURE, ""),
               source + "\n#ifdef VH_MAP02_PIXEL_PROBE\n#endif",
               instrument(source))
        for item in bad:
            with self.subTest(bad=item[-50:]), self.assertRaises(ValueError):
                instrument(item)

    @unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
    def test_original_and_both_build_modes_execute(self):
        original = source_fixture()
        patched = instrument(original)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for label, source, diagnostic in (
                ("original", original, False),
                ("patched-off", patched, False),
                ("patched-on", patched, True),
            ):
                with self.subTest(label=label):
                    file = root / (label + ".c")
                    exe = root / label
                    file.write_text(source, encoding="utf-8")
                    flags = (["-DVH_MAP02_SCOPED_BLEND_PROBE"] if diagnostic else [])
                    subprocess.run(
                        ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                         *flags, str(file), "-o", str(exe)],
                        check=True, capture_output=True, text=True)
                    subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
