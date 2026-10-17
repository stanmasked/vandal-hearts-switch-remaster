"""Execute generated two-word native PutPixel scope in an isolated C11 probe.

The synthetic raster calls the same unchanged native WritePixel statement.
No original game files are needed; CI separately compiles real pinned sources.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_instrument_map02_native_putpixel import SOURCE
from tools.instrument_map02_multi_putpixel_scope import multi_raster

DRIVER = r'''
int main(void) {
#if defined(VH_MAP02_MULTI_PUTPIXEL_SCOPE)
    VH_Map02PixelScopeSet(12, 1, 2);
    PutPixel(30, 30, 0x801f, 1, 0, 1);
    PutPixel(35, 35, 0x03e0, 1, 0, 1);
    PutPixel(30, 30, 0x801f, 1, 0, 1); /* real same-value call */
    PutPixel(31, 31, 0x7fff, 1, 0, 1); /* not sampled */
    VH_Map02PixelScopeClear();

    VH_Map02PixelScopeSet(12, 2, 2);
    PutPixel(35, 35, 0x7c00, 1, 0, 1);
    VH_Map02PixelScopeClear();
    VH_Map02PixelScopeSet(13, 3, 2); /* different GPU frame */
    PutPixel(30, 30, 0x0000, 1, 0, 1);
    VH_Map02PixelScopeClear();
#endif
    return 0;
}
'''

CAP_DRIVER = r'''
int main(void) {
#if defined(VH_MAP02_MULTI_PUTPIXEL_SCOPE)
    unsigned i;
    VH_Map02PixelScopeSet(12, 1, 2);
    for (i = 0; i < 70u; i++) {
        if (i & 1u)
            PutPixel(35, 35, (unsigned short)(i + 1u), 1, 0, 1);
        else
            PutPixel(30, 30, (unsigned short)(i + 1u), 1, 0, 1);
    }
    VH_Map02PixelScopeClear();
#endif
    return 0;
}
'''


class NativeTwoWordExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gcc = shutil.which("gcc")
        if cls.gcc is None:
            raise unittest.SkipTest("gcc is unavailable")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="vh-multi-c11-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "pc_raster.multiscope.c"
        self.source.write_text(multi_raster(SOURCE) + DRIVER, encoding="utf-8")
        self.binary = self.root / "native-multiscope-test"
        subprocess.run(
            [self.gcc, "-std=gnu11", "-Wall", "-Werror",
             "-DVH_MAP02_MULTI_PUTPIXEL_SCOPE",
             str(self.source), "-o", str(self.binary)],
            check=True, capture_output=True, text=True,
        )

    def run_capture(self, name, *, x2="35", y2="35"):
        target = self.root / name
        target.mkdir()
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("VH_MAP02_")}
        env.update({
            "VH_MAP02_PUTPIXEL_DIR": str(target),
            "VH_MAP02_PUTPIXEL_FRAME": "12",
            "VH_MAP02_PUTPIXEL_X": "30",
            "VH_MAP02_PUTPIXEL_Y": "30",
            "VH_MAP02_PUTPIXEL_X2": x2,
            "VH_MAP02_PUTPIXEL_Y2": y2,
        })
        subprocess.run([str(self.binary)], env=env,
                       check=True, capture_output=True, text=True)
        path = target / "putpixel-native-events.jsonl"
        return (path.read_bytes() if path.exists() else None)

    def test_same_native_stream_orders_two_addresses_and_ignores_other_frame(self):
        raw = self.run_capture("valid")
        self.assertIsNotNone(raw)
        self.assertTrue(raw.endswith(b"\n"))
        rows = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual([e["step"] for e in rows], [0, 1, 2, 3])
        self.assertEqual([e["frame"] for e in rows], [12, 12, 12, 12])
        self.assertEqual([e["primitive_ordinal"] for e in rows],
                         [1, 1, 1, 2])
        self.assertEqual([e["primitive_type"] for e in rows], [2] * 4)
        self.assertEqual([(e["x"], e["y"]) for e in rows],
                         [(30,30), (35,35), (30,30), (35,35)])
        self.assertEqual([e["before"] for e in rows],
                         [0, 0, 0x801f, 0x03e0])
        self.assertEqual([e["after"] for e in rows],
                         [0x801f, 0x03e0, 0x801f, 0x7c00])
        self.assertEqual(rows[1]["accurate"], 1)

    def test_duplicate_or_invalid_second_coordinate_disables_capture(self):
        self.assertIsNone(self.run_capture("duplicates", x2="30", y2="30"))
        self.assertIsNone(self.run_capture("not_numeric", x2="abc"))
        self.assertIsNone(self.run_capture("out_of_bounds", x2="1024"))

    def test_both_addresses_share_a_single_global_64_call_ceiling(self):
        cap_source = self.root / "pc_raster.multiscope.cap.c"
        cap_source.write_text(multi_raster(SOURCE) + CAP_DRIVER,
                              encoding="utf-8")
        subprocess.run(
            [self.gcc, "-std=gnu11", "-Wall", "-Werror",
             "-DVH_MAP02_MULTI_PUTPIXEL_SCOPE",
             str(cap_source), "-o", str(self.binary)],
            check=True, capture_output=True, text=True,
        )
        raw = self.run_capture("cap")
        self.assertIsNotNone(raw)
        events = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(len(events), 64)
        self.assertEqual([e["step"] for e in events], list(range(64)))
        self.assertEqual({(e["x"], e["y"]) for e in events},
                         {(30, 30), (35, 35)})
        self.assertEqual(events[0]["before"], 0)
        self.assertEqual(events[-1]["step"], 63)

    def test_normal_non_opt_in_binary_has_no_scope_symbols(self):
        obj = self.root / "normal-gpu.o"
        subprocess.run(
            [self.gcc, "-std=gnu11", "-c", str(self.source), "-o", str(obj)],
            check=True, capture_output=True, text=True,
        )
        nm = shutil.which("nm")
        if nm is None:
            self.skipTest("nm is unavailable")
        symbols = subprocess.run([nm, "-a", str(obj)],
                                 check=True, capture_output=True, text=True).stdout
        self.assertNotIn("VH_Map02PixelScope", symbols)
        self.assertNotIn("VH_PixelSampleRecord", symbols)


if __name__ == "__main__":
    unittest.main()
