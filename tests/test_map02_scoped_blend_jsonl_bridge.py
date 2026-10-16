"""Synthetic C JSONL -> Python strict BlendG1 witness verification.

Exercises the exact byte format emitted by the private in-memory C sink.
No actual game assets, traces or pixel screenshots are involved.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.map02_blendg1_witness import compare_blendg1_witnesses

ROOT = Path(__file__).resolve().parents[1]

C_SOURCE = r"""
#include <assert.h>
#include <stdio.h>
#include "map02_scoped_blend_sink.h"
int main(void) {
    unsigned index;
    char line[512];
    vh_map02_scope_reset();
    assert(vh_map02_scope_begin_frame(7, 20, 40));
    assert(vh_map02_scope_begin_primitive(0, 4));
    vh_map02_probe_begin(20, 40, 0x001f, 0x7c00, 0, 1, 1, 1);
    vh_map02_probe_blendg1(20, 40, 0xfc00, 0x001f, 0x03e0, 0, 1);
    vh_map02_probe_end(20, 40, 0x03e0);
    vh_map02_probe_begin(20, 40, 0x03e0, 0x0010, 1, 1, 1, 0);
    vh_map02_probe_end(20, 40, 0x03f0);
    vh_map02_probe_begin(20, 40, 0x03f0, 0x0100, 0, 0, 1, 0);
    vh_map02_probe_end(20, 40, 0x0100);
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_end_frame());
    assert(vh_map02_scope_count() == 3);
    for (index = 0; index < vh_map02_scope_count(); index++) {
        assert(vh_map02_scope_format_putpixel(index, line, sizeof line) > 0);
        fputs(line, stdout);
        if (vh_map02_scope_format_blendg1(index, line, sizeof line))
            fputs(line, stdout);
    }
    return 0;
}
"""


@unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
class ScopedBlendJsonlBridgeTests(unittest.TestCase):
    def test_producer_rows_match_python_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "emit.c"
            binary = root / "emit"
            source.write_text(C_SOURCE, encoding="utf-8")
            subprocess.run(
                ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "tools"),
                 str(source), str(ROOT / "tools/map02_scoped_blend_sink.c"),
                 "-o", str(binary)],
                check=True, capture_output=True, text=True)
            raw = subprocess.check_output([str(binary)], text=True)
        self.assertTrue(raw.endswith("\n"))
        rows = [json.loads(line) for line in raw.splitlines()]
        pixels = [r for r in rows if r["stage"] == "native_putpixel"]
        blends = [r for r in rows if r["stage"] == "native_blendg1"]
        self.assertEqual(len(pixels), 3)
        self.assertEqual(len(blends), 1)
        self.assertTrue(all(p["primitive_type"] == 4 for p in pixels))
        report = compare_blendg1_witnesses(pixels, blends)
        self.assertEqual(report["observed_blendg1_putpixel_pairs"], 1)
        self.assertEqual(report["legacy_semi_putpixel_calls_without_blendg1"], 1)
        altered = [dict(blends[0], primitive_type=5)]
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses(pixels, altered)
        missing = [dict(blends[0])]
        del missing[0]["blend_fg"]
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses(pixels, missing)


if __name__ == "__main__":
    unittest.main()
