"""Compile and execute private PC scratch capture with synthetic RGB24 bytes."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = r"""
#include "map02_pc_preoverlay_capture.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    unsigned char rgba[12] = {1,2,3,4,5,6,7,8,9,10,11,12};
    int ok;
    if (argc != 3) return 20;
    if (setenv("VH_MAP02_PROBE_FRAME", "7", 1) ||
        setenv("VH_MAP02_PC_PREOVERLAY_OUTPUT_DIR", argv[1], 1)) return 21;
    if (!strcmp(argv[2], "bad-frame"))
        setenv("VH_MAP02_PROBE_FRAME", "7x", 1);
    if (!strcmp(argv[2], "bad-nonce"))
        return 22;
    if (vh_map02_pc_capture_preoverlay(6, rgba, 2, 2, 0, 0) != 1 &&
        strcmp(argv[2], "bad-frame")) return 23;
    ok = vh_map02_pc_capture_preoverlay(7, rgba, 2, 2,
             !strcmp(argv[2], "movie"), !strcmp(argv[2], "hires"));
    if (!strcmp(argv[2], "valid")) {
        if (ok != 1) return 24;
        if (vh_map02_pc_capture_preoverlay(7, rgba, 2, 2, 0, 0) != 0)
            return 25;
    } else if (ok != 0) {
        return 26;
    }
    return 0;
}
"""


class PrivatePcRgb24NativeCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("gcc") or shutil.which("clang")
        if cls.compiler is None:
            raise unittest.SkipTest("host C compiler unavailable")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.directory = root / "private"
        self.directory.mkdir(mode=0o700)
        program = root / "capture_test.c"
        program.write_text(SOURCE)
        self.executable = root / "capture"
        cmd = [
            self.compiler, "-std=c11", "-D_POSIX_C_SOURCE=200809L",
            "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "tools"),
            str(program),
            str(ROOT / "tools/map02_pc_preoverlay_capture.c"),
            str(ROOT / "tools/map02_capture_session.c"),
            "-o", str(self.executable),
        ]
        build = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr)

    def run_mode(self, name):
        return subprocess.run([str(self.executable), str(self.directory), name],
                              capture_output=True, text=True)

    def test_writes_exact_owner_private_bottom_up_rgb_and_in_process_receipt(self):
        result = self.run_mode("valid")
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.directory / "map02-pc-present-preoverlay-rgb24.bin"
        seal = self.directory / "map02-pc-present-preoverlay-receipt.jsonl"
        self.assertEqual(raw.read_bytes(), bytes(range(1, 13)))
        self.assertEqual(stat.S_IMODE(raw.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(seal.stat().st_mode), 0o600)
        receipt = json.loads(seal.read_text())
        self.assertEqual(receipt["schema"], "vh.map02.pc-preoverlay-capture.v1")
        self.assertEqual(receipt["gpu_draw_frame"], 7)
        self.assertEqual((receipt["width"], receipt["height"], receipt["bytes"]),
                         (2, 2, 12))
        self.assertEqual(receipt["pixel_format"], "rgb24-bottom-up")
        self.assertEqual(len(receipt["capture_session"]), 32)
        self.assertFalse(receipt["movie_overlay_active"])
        self.assertFalse(receipt["hires_active"])
        self.assertFalse(receipt["presented_window_authenticated"])

    def test_movie_hires_or_invalid_selected_frame_rejected_without_capture(self):
        for mode in ("movie", "hires", "bad-frame"):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_mode(mode).returncode, 0)
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_existing_file_never_overwritten(self):
        rgb = self.directory / "map02-pc-present-preoverlay-rgb24.bin"
        rgb.write_bytes(b"foreign")
        self.assertEqual(self.run_mode("valid").returncode, 24)
        self.assertEqual(rgb.read_bytes(), b"foreign")

    def test_unprivate_directory_never_receives_image(self):
        self.directory.chmod(0o755)
        self.addCleanup(self.directory.chmod, 0o700)
        self.assertEqual(self.run_mode("valid").returncode, 24)
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
