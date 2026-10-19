"""Exercise the opt-in C GPU-flush transport through the real Linux ELF pipe.

Only synthetic BGR555 pixels are used; this does not run game rasterization.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.capture_map02_live_frame_pipe import capture

PRODUCER = r'''
#include "map02_native_frame_pipe.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv)
{
    /* Two scanlines with one sentinel padding word per row. */
    uint16_t framebuffer[6] = {
        0x8000, 0x7fff, 0xface,
        0x0123, 0x4567, 0xbabe
    };
    if (vh_map02_frame_pipe_wait_release(STDIN_FILENO) != 0)
        return 3;
    if (argc > 1 && !strcmp(argv[1], "bad-stride")) {
        if (vh_map02_frame_pipe_emit(STDOUT_FILENO, 123, 2, 2,
                                     framebuffer, 1) != -1 || errno != EINVAL)
            return 20;
        return 6;
    }
    if (argc > 1 && !strcmp(argv[1], "null-buffer")) {
        if (vh_map02_frame_pipe_emit(STDOUT_FILENO, 123, 2, 2,
                                     NULL, 3) != -1 || errno != EINVAL)
            return 20;
        return 6;
    }
    if (argc > 1 && !strcmp(argv[1], "too-wide")) {
        if (vh_map02_frame_pipe_emit(STDOUT_FILENO, 123, 1025, 2,
                                     framebuffer, 1025) != -1 || errno != EINVAL)
            return 20;
        return 6;
    }
    if (argc > 1 && !strcmp(argv[1], "zero-frame")) {
        if (vh_map02_frame_pipe_emit(STDOUT_FILENO, 0, 2, 2,
                                     framebuffer, 3) != -1 || errno != EINVAL)
            return 20;
        return 6;
    }
    if (argc > 1 && !strcmp(argv[1], "wrong-frame"))
        return vh_map02_frame_pipe_emit(STDOUT_FILENO, 124, 2, 2,
                                        framebuffer, 3) == 0 ? 0 : 9;
    if (argc > 1 && !strcmp(argv[1], "wrong-size"))
        return vh_map02_frame_pipe_emit(STDOUT_FILENO, 123, 1, 2,
                                        framebuffer, 3) == 0 ? 0 : 9;
    return vh_map02_frame_pipe_emit(STDOUT_FILENO, 123, 2, 2,
                                    framebuffer, 3) == 0 ? 0 : 9;
}
'''


class NativeFlushPipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-flush-c11-")
        base = Path(cls.workspace.name)
        cls.cc = os.environ.get("CC", "cc")
        if not shutil.which(cls.cc):
            raise RuntimeError("selected native compiler unavailable")
        cls.source = base / "producer.c"
        cls.source.write_text(PRODUCER, encoding="utf-8")
        cls.executable = base / "producer"
        cls.flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                     "-pedantic", "-Itools"]
        subprocess.run(
            [cls.cc, *cls.flags, "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1",
             str(cls.source), "tools/map02_native_frame_pipe.c",
             "-o", str(cls.executable)],
            check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-flush-private-")
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "private"
        self.out.mkdir(mode=0o700)

    def run_capture(self, *args):
        return capture(
            self.executable, self.out, frame=123, width=2, height=2,
            executable_sha256=self.digest, timeout=5, args=args)

    def test_native_pitched_buffer_yields_exact_little_endian_pixels(self):
        result = self.run_capture()
        # Padding words 0xFACE and 0xBABE may never leave the process.
        expected = bytes.fromhex("0080ff7f23016745")
        self.assertEqual((self.out / "process-frame.bgr555").read_bytes(),
                         expected)
        self.assertEqual(result["image_sha256"],
                         hashlib.sha256(expected).hexdigest())
        self.assertEqual(result["executable_sha256"], self.digest)
        self.assertFalse(result["native_renderer_origin_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])

    def test_disabled_diagnostic_build_is_compile_error(self):
        compilation = subprocess.run(
            [self.cc, *self.flags, "-c", "tools/map02_native_frame_pipe.c",
             "-o", str(self.out.parent / "without-diagnostic.o")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(compilation.returncode, 0)

    def test_zero_diagnostic_value_is_compile_error(self):
        compilation = subprocess.run(
            [self.cc, *self.flags, "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=0",
             "-c", "tools/map02_native_frame_pipe.c",
             "-o", str(self.out.parent / "disabled.o")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(compilation.returncode, 0)

    def test_invalid_stride_emits_no_frame(self):
        with self.assertRaisesRegex(ValueError, "producer failed"):
            self.run_capture("bad-stride")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_null_framebuffer_emits_no_frame(self):
        with self.assertRaisesRegex(ValueError, "producer failed"):
            self.run_capture("null-buffer")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_invalid_width_emits_no_frame(self):
        with self.assertRaisesRegex(ValueError, "producer failed"):
            self.run_capture("too-wide")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_zero_frame_emits_no_frame(self):
        with self.assertRaisesRegex(ValueError, "producer failed"):
            self.run_capture("zero-frame")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_wrong_frame_number_refused_by_live_launcher(self):
        with self.assertRaisesRegex(ValueError, "header"):
            self.run_capture("wrong-frame")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_wrong_frame_geometry_refused_by_live_launcher(self):
        with self.assertRaisesRegex(ValueError, "truncated|header"):
            self.run_capture("wrong-size")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_release_gate_refuses_wrong_byte(self):
        proc = subprocess.run(
            [str(self.executable)], input=b"\x00",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"")


if __name__ == "__main__":
    unittest.main()
