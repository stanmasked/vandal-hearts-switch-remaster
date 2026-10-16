"""Synthetic DrawOTag source hooks + C host test for actual OT ordinal wiring.

No game frames, textures, pixel data or hardware assertions are produced.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_drawotag_scope import (
    ENTRY, FRAME, PRIM, PRIM_END, INVALID_TOKEN, CYCLE, END, instrument,
)

ROOT = Path(__file__).resolve().parents[1]

def source_fixture():
    return (r"""
#include <stdlib.h>
#include <assert.h>
#include "map02_scoped_blend_sink.h"
typedef struct P_TAG { unsigned tag; } P_TAG;
static unsigned s_drawFrame = 0;
static P_TAG slots[5];
static int invalid_walk;
static unsigned visits;
static void *PC_OtResolve(unsigned token, int *bucket) {
    if (invalid_walk && token == 3) return 0;
    if (token == 0 || token > 4) return 0;
    *bucket = (token == 1 || token == 3);
    return &slots[token];
}
static void TrcFrameEnd(void) {}
""" + ENTRY + r"""
    unsigned nextTok = ((P_TAG *)p)->tag;
    unsigned long walkSteps = 0;
""" + FRAME + r"""
""" + "    while (nextTok) {\n" + r"""        int isBucket = 0;
        void *cur = PC_OtResolve(nextTok, &isBucket);
        unsigned rawTagOfCur;
        if (cur == NULL) {
""" + INVALID_TOKEN + r"""
""" + PRIM + r"""
            unsigned short word = (unsigned short)(visits + 1u);
            vh_map02_probe_begin(4, 3, word, word, 0, 1, 1, 1);
            vh_map02_probe_blendg1(4, 3, (unsigned short)(word | 0x8000),
                                    word, word, 0, 1);
            vh_map02_probe_end(4, 3, word);
            visits++;
""" + PRIM_END + r"""
""" + CYCLE + r"""
            break;
        }
    }
""" + END + r"""
}
int main(void) {
    VHMap02BlendEvent event;
    P_TAG root;
    root.tag = 1;
    slots[1].tag = 2;
    slots[2].tag = 3;
    slots[3].tag = 4;
    slots[4].tag = 0;
    DrawOTag((unsigned *)&root);
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    assert(!vh_map02_scope_failed());
    assert(vh_map02_scope_count() == 2);
    assert(vh_map02_scope_copy(0, &event) && event.ordinal == 0);
    assert(vh_map02_scope_copy(1, &event) && event.ordinal == 1);
    invalid_walk = 1;
    visits = 0;
    DrawOTag((unsigned *)&root);
    assert(vh_map02_scope_failed());
    assert(!vh_map02_scope_copy(0, &event));
#else
    assert(visits == 2);
#endif
    return 0;
}
""")

class DrawOTagScopeTests(unittest.TestCase):
    def test_patch_anchors_and_guards(self):
        patched = instrument(source_fixture())
        self.assertIn("vh_map02_scope_begin_frame(", patched)
        self.assertIn("vh_map02_scope_begin_primitive(vh_scope_ordinal)", patched)
        self.assertIn("vh_map02_scope_end_primitive()", patched)
        self.assertIn("vh_map02_scope_end_frame()", patched)
        self.assertEqual(patched.count("if (vh_scope_active) vh_map02_scope_abort();"), 2)
        self.assertIn("vh_scope_ordinal++", patched)
        self.assertIn("Hires", "Hires is unrelated to the synthetic fixture")

    def test_source_drift_rejected(self):
        source = source_fixture()
        for broken in (source.replace(PRIM_END, ""),
                       source.replace(PRIM, ""),
                       source.replace(CYCLE, ""),
                       source.replace(INVALID_TOKEN, ""),
                       source + "\n" + FRAME,
                       instrument(source)):
            with self.subTest(broken=broken[:70]), self.assertRaises(ValueError):
                instrument(broken)

    @unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
    def test_synthetic_ot_bucket_ordinal_and_abort(self):
        source = source_fixture()
        instrumented = instrument(source)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, src, enabled in (
                ("original", source, False),
                ("patched-off", instrumented, False),
                ("patched-on", instrumented, True),
            ):
                with self.subTest(name=name):
                    path = root / (name + ".c")
                    binary = root / name
                    path.write_text(src, encoding="utf-8")
                    subprocess.run([
                        "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "tools"),
                        * (["-DVH_MAP02_SCOPED_BLEND_PROBE"] if enabled else []),
                        str(path), str(ROOT / "tools/map02_scoped_blend_sink.c"),
                        "-o", str(binary),
                    ], check=True, capture_output=True, text=True)
                    env = os.environ.copy()
                    if enabled:
                        env.update(VH_MAP02_PROBE_FRAME="1",
                                   VH_MAP02_PROBE_X="4",
                                   VH_MAP02_PROBE_Y="3")
                    subprocess.run([str(binary)], env=env, check=True,
                                   capture_output=True, text=True)

if __name__ == "__main__":
    unittest.main()
