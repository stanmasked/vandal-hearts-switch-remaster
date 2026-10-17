"""Fail-closed direct VRAM before/after snapshot state-machine regressions.

No original proprietary data; the C fixture supplies synthetic native words.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r"""
#include <assert.h>
#include "map02_vram_edges.h"
int main(void) {
    VHMap02VramEdge entry;
    unsigned i;
    vh_map02_edges_reset();
    assert(!vh_map02_edges_copy(0, &entry));
    assert(vh_map02_edges_begin_frame(7, 10, 20));
    assert(vh_map02_edges_begin_primitive(0, 1, 0x001f));
    assert(vh_map02_edges_end_primitive(0x03e0));
    assert(vh_map02_edges_begin_primitive(1, 2, 0x03e0));
    assert(vh_map02_edges_end_primitive(0x03e0)); /* transparent no-op */
    assert(vh_map02_edges_end_frame());
    assert(vh_map02_edges_count() == 2);
    assert(vh_map02_edges_copy(0, &entry));
    assert(entry.frame == 7 && entry.ordinal == 0 && entry.primitive_type == 1);
    assert(entry.x == 10 && entry.y == 20);
    assert(entry.before == 0x001f && entry.after == 0x03e0);
    assert(vh_map02_edges_copy(1, &entry));
    assert(entry.ordinal == 1 && entry.primitive_type == 2);
    assert(entry.before == entry.after);
    assert(!vh_map02_edges_copy(2, &entry));
    assert(!vh_map02_edges_begin_primitive(2, 4, 1));
    assert(vh_map02_edges_failed());
    assert(!vh_map02_edges_copy(0, &entry));

    vh_map02_edges_reset();
    assert(vh_map02_edges_begin_frame(7, 10, 20));
    assert(!vh_map02_edges_begin_primitive(1, 1, 0));
    assert(!vh_map02_edges_end_frame());
    vh_map02_edges_reset();
    assert(vh_map02_edges_begin_frame(7, 10, 20));
    assert(!vh_map02_edges_begin_primitive(0, 5, 0));
    vh_map02_edges_reset();
    assert(vh_map02_edges_begin_frame(7, 10, 20));
    assert(vh_map02_edges_begin_primitive(0, 1, 0));
    assert(!vh_map02_edges_end_frame()); /* never publish half draw */
    assert(vh_map02_edges_failed());

    vh_map02_edges_reset();
    assert(vh_map02_edges_begin_frame(7, 10, 20));
    for (i = 0; i < VH_MAP02_MAX_DRAW_EDGES; i++) {
        assert(vh_map02_edges_begin_primitive(i, 4, 0));
        assert(vh_map02_edges_end_primitive(0));
    }
    assert(!vh_map02_edges_begin_primitive(VH_MAP02_MAX_DRAW_EDGES, 4, 0));
    assert(vh_map02_edges_failed());
    assert(!vh_map02_edges_copy(0, &entry));
    return 0;
}
"""


@unittest.skipUnless(shutil.which("cc"), "C99 compiler unavailable")
class NativeVramEdgeTests(unittest.TestCase):
    def test_independent_bounds_order_noops_and_abort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.c"
            binary = root / "test-edges"
            main.write_text(SOURCE, encoding="utf-8")
            subprocess.run([
                "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "tools"),
                str(main), str(ROOT / "tools/map02_vram_edges.c"),
                "-o", str(binary)
            ], capture_output=True, text=True, check=True)
            subprocess.run([str(binary)], capture_output=True,
                           text=True, check=True)


if __name__ == "__main__":
    unittest.main()
