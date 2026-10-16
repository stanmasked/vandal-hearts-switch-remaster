"""Host C regression for bounded MAP02 sink. Synthetic input only."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include <assert.h>
#include <string.h>
#include "map02_scoped_blend_sink.h"

static void valid_accurate(void) {
    vh_map02_probe_begin(4, 3, 0x0020, 0x0001, 1, 1, 1, 1);
    vh_map02_probe_blendg1(4, 3, 0x8001, 0x0020, 0x0030, 1, 1);
    vh_map02_probe_end(4, 3, 0x0030);
}
static void setup(void) {
    vh_map02_scope_reset();
    assert(vh_map02_scope_begin_frame(7, 4, 3));
    assert(vh_map02_scope_begin_primitive(0, 4));
}
static void reject(void) {
    assert(vh_map02_scope_failed());
    assert(vh_map02_scope_count() == 0);
    assert(!vh_map02_scope_copy(0, (VHMap02BlendEvent *)0));
    assert(!vh_map02_scope_end_frame());
}
int main(void) {
    VHMap02BlendEvent e;
    unsigned i;
    char private_line[512];
    vh_map02_scope_reset();
    vh_map02_probe_begin(0, 0, 0, 1, 1, 1, 1, 1);
    vh_map02_probe_end(0, 0, 1);
    assert(!vh_map02_scope_failed()); /* no selected frame */
    setup();
    assert(!vh_map02_scope_copy(0, &e));
    assert(!vh_map02_scope_format_putpixel(0, private_line,
                                           (unsigned)sizeof private_line));
    /* Writes to other coordinates are not recorded. */
    vh_map02_probe_begin(5, 3, 0, 0, 0, 0, 0, 0);
    vh_map02_probe_end(5, 3, 0);
    valid_accurate();
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_begin_primitive(1, 5));
    vh_map02_probe_begin(4, 3, 0x0030, 0x0040, 3, 1, 0, 0);
    vh_map02_probe_end(4, 3, 0x0050); /* legacy blend, no BlendG1 call */
    vh_map02_probe_begin(4, 3, 0x0050, 0x0070, 0, 0, 0, 0);
    vh_map02_probe_end(4, 3, 0x0070); /* opaque copy */
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_end_frame());
    assert(vh_map02_scope_count() == 3);
    assert(vh_map02_scope_copy(0, &e));
    assert(e.frame == 7 && e.ordinal == 0 && e.step == 0);
    assert(e.primitive_type == 4);
    assert(vh_map02_scope_format_putpixel(0, private_line,
                                          (unsigned)sizeof private_line) > 0);
    assert(strstr(private_line, "\"primitive_type\":4") != NULL);
    assert(private_line[strlen(private_line) - 1] == '\n');
    assert(vh_map02_scope_format_blendg1(0, private_line,
                                         (unsigned)sizeof private_line) > 0);
    assert(strstr(private_line, "\"blend_fg\":32769") != NULL);
    assert(private_line[strlen(private_line) - 1] == '\n');
    assert(!vh_map02_scope_format_blendg1(1, private_line,
                                          (unsigned)sizeof private_line));
    assert(!vh_map02_scope_format_putpixel(0, private_line, 1));
    vh_map02_probe_begin(4, 3, 0, 1, 1, 1, 1, 1);
    assert(!vh_map02_scope_failed()); /* after frame: ignored */
    assert(e.has_blend == 1 && e.blend_fg == 0x8001);
    assert(e.blend_bg == 0x0020 && e.blend_result == 0x0030);
    assert(vh_map02_scope_copy(1, &e));
    assert(e.ordinal == 1 && e.step == 1 && !e.has_blend);
    assert(!vh_map02_scope_copy(3, &e));
    assert(!vh_map02_scope_begin_frame(8, 4, 3));
    reject();

    setup();
    vh_map02_probe_begin(4, 3, 0, 1, 1, 1, 1, 1);
    vh_map02_probe_end(4, 3, 3); /* required BlendG1 absent */
    reject();

    setup();
    vh_map02_probe_begin(4, 3, 0, 1, 1, 1, 1, 1);
    vh_map02_probe_blendg1(4, 3, 0x0001, 0, 3, 1, 1); /* bit15 missing */
    reject();

    setup();
    vh_map02_probe_begin(4, 3, 0, 1, 1, 1, 1, 1);
    vh_map02_probe_blendg1(4, 3, 0x8001, 0, 3, 1, 1);
    vh_map02_probe_blendg1(4, 3, 0x8001, 0, 3, 1, 1); /* duplicate */
    reject();

    setup();
    valid_accurate();
    assert(!vh_map02_scope_end_frame()); /* primitive still open */
    reject();

    setup();
    assert(vh_map02_scope_end_primitive());
    assert(!vh_map02_scope_begin_primitive(2, 4)); /* skipped ordinal */
    reject();

    vh_map02_scope_reset();
    assert(vh_map02_scope_begin_frame(7, 4, 3));
    assert(!vh_map02_scope_begin_primitive(0, 256));
    reject();

    setup();
    for (i = 0; i < VH_MAP02_MAX_EVENTS; i++) {
        if (i == 0) valid_accurate();
        else {
            vh_map02_probe_begin(4, 3, 0, 1, 0, 0, 1, 0);
            vh_map02_probe_end(4, 3, 1);
        }
    }
    vh_map02_probe_begin(4, 3, 0, 1, 0, 0, 1, 0); /* overflow */
    reject();
    return 0;
}
"""


@unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
class ScopedBlendSinkTests(unittest.TestCase):
    def test_native_event_machine_compiles_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.c"
            exe = root / "probe-test"
            main.write_text(HARNESS, encoding="utf-8")
            subprocess.run([
                "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "tools"),
                str(ROOT / "tools/map02_scoped_blend_sink.c"),
                str(main), "-o", str(exe)
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
