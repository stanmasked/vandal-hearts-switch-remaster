"""End-to-end synthetic C test: unified generated rasterizer + private sink.

Not the original game; no real DrawOTag context authentication is claimed.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_instrument_map02_scoped_blend import source_fixture
from tools.instrument_map02_scoped_blend import instrument

ROOT = Path(__file__).resolve().parents[1]

MAIN = r"""
#include "map02_scoped_blend_sink.h"

int main(void) {
    VHMap02BlendEvent event;
    RenderCtx native = {0, 1}, hires = {1, 2};
    vh_map02_scope_reset();
    assert(vh_map02_scope_begin_frame(31, 1, 1));
    assert(vh_map02_scope_begin_primitive(0, 4));
    PutPixel(&native, 1, 1, 0x001f, 2, 1, 1);
    PutPixel(&hires, 1, 1, 0x001f, 2, 1, 1);
    accurate_mode = 0;
    PutPixel(&native, 1, 1, 0x002f, 2, 1, 1);
    PutPixel(&native, 1, 1, 0x003f, 2, 0, 1);
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_end_frame());
    assert(vh_map02_scope_count() == 3);
    assert(vh_map02_scope_copy(0, &event));
    assert(event.frame == 31 && event.ordinal == 0 && event.step == 0 && event.primitive_type == 4);
    assert(event.accurate && event.has_blend);
    assert(event.blend_fg == 0x801f);
    assert(event.blend_bg == event.before);
    assert(event.blend_result == event.after);
    assert(vh_map02_scope_copy(1, &event));
    assert(!event.accurate && event.semi && !event.has_blend);
    assert(vh_map02_scope_copy(2, &event));
    assert(!event.semi && !event.has_blend);
    assert(event.after == event.front);
    return 0;
}
"""


@unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
class ScopedBlendEndToEndTests(unittest.TestCase):
    def test_generated_c_probes_private_sink(self):
        original = source_fixture().split("static int begins, blends, ends;")[0]
        self.assertTrue(original.endswith("}\n"))
        patched = instrument(original) + MAIN
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scoped.c"
            binary = Path(tmp) / "scoped-test"
            source.write_text(patched, encoding="utf-8")
            subprocess.run([
                "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                "-DVH_MAP02_SCOPED_BLEND_PROBE",
                "-I", str(ROOT / "tools"),
                str(source), str(ROOT / "tools/map02_scoped_blend_sink.c"),
                "-o", str(binary)
            ], check=True, text=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
