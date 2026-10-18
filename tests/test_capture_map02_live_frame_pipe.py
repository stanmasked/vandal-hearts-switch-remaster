"""Asset-free native ELF producer -> private BGR555 channel regressions."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.capture_map02_live_frame_pipe import capture

SOURCE = r'''
#include <stdint.h>
#include <unistd.h>
#include <string.h>
static int sendall(const void *v, size_t n) {
    const char *p = (const char *)v;
    while (n) {
        ssize_t k = write(1, p, n);
        if (k <= 0) return 0;
        p += k;
        n -= (size_t)k;
    }
    return 1;
}
int main(int argc, char **argv) {
    char release = 0;
    if (read(0, &release, 1) != 1 || release != 1) return 8;
    if (argc > 1 && !strcmp(argv[1], "exit")) return 7;
    unsigned char header[20] = {
        'V','H','M','2','F','R','M','1', 123,0,0,0, 2,0,0,0, 2,0,0,0
    };
    unsigned char pixels[8] = {0,0, 255,127, 1,0, 2,0};
    if (argc > 1 && !strcmp(argv[1], "wrong-frame")) header[8] = 124;
    if (argc > 1 && !strcmp(argv[1], "wrong-magic")) header[0] = 'X';
    if (!sendall(header, sizeof(header))) return 9;
    if (argc > 1 && !strcmp(argv[1], "short")) return 0;
    if (!sendall(pixels, sizeof(pixels))) return 9;
    if (argc > 1 && !strcmp(argv[1], "extra")) {
        char extra = 'X';
        sendall(&extra, 1);
    }
    return 0;
}
'''


class NativePipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-elf-pipe-")
        root = Path(cls.workspace.name)
        src, cls.executable = root / "producer.c", root / "producer"
        src.write_text(SOURCE, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if shutil.which(cc) is None:
            raise RuntimeError("selected native C compiler unavailable")
        subprocess.run(
            [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
             str(src), "-o", str(cls.executable)], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-private-frame-")
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "private"
        self.out.mkdir(mode=0o700)

    def run_capture(self, *args, **kwargs):
        return capture(
            self.executable, self.out, frame=123, width=2, height=2,
            executable_sha256=kwargs.get("digest", self.digest),
            timeout=5, args=args)

    def assert_empty(self):
        self.assertEqual(list(self.out.iterdir()), [])

    def test_real_elf_stdout_exact_bytes_hash_and_fail_closed_flags(self):
        receipt = self.run_capture()
        expected = bytes([0, 0, 255, 127, 1, 0, 2, 0])
        image = self.out / "process-frame.bgr555"
        self.assertEqual(image.read_bytes(), expected)
        self.assertEqual(receipt["image_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertTrue(receipt["kernel_observed_pinned_elf_before_stream"])
        self.assertTrue(receipt["child_stdout_pipe_frame_received"])
        self.assertFalse(receipt["native_renderer_origin_authenticated"])
        self.assertFalse(receipt["hd_replacement_authorized"])
        self.assertEqual(image.stat().st_mode & 0o777, 0o600)
        report = (self.out / "process-frame.json").read_text()
        self.assertNotIn(str(self.executable), report)
        self.assertNotIn(str(self.out), report)

    def test_wrong_frame_refused(self):
        with self.assertRaisesRegex(ValueError, "header"):
            self.run_capture("wrong-frame")
        self.assert_empty()

    def test_wrong_magic_refused(self):
        with self.assertRaisesRegex(ValueError, "header"):
            self.run_capture("wrong-magic")
        self.assert_empty()

    def test_short_output_refused(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.run_capture("short")
        self.assert_empty()

    def test_extra_bytes_refused(self):
        with self.assertRaisesRegex(ValueError, "exceeded"):
            self.run_capture("extra")
        self.assert_empty()

    def test_nonzero_producer_refused(self):
        with self.assertRaisesRegex(ValueError, "failed"):
            self.run_capture("exit")
        self.assert_empty()

    def test_wrong_elf_digest_refused(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.run_capture(digest="0" * 64)
        self.assert_empty()

    def test_symlink_executable_refused(self):
        link = self.out.parent / "symlink"
        link.symlink_to(self.executable)
        with self.assertRaises(OSError):
            capture(link, self.out, frame=123, width=2, height=2,
                    executable_sha256=self.digest)
        self.assert_empty()

    def test_unsafe_private_directory_refused(self):
        self.out.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.run_capture()
        self.assert_empty()

    def test_bad_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, "geometry"):
            capture(self.executable, self.out, frame=123, width=5000,
                    height=2, executable_sha256=self.digest)
        self.assert_empty()


if __name__ == "__main__":
    unittest.main()
