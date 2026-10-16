"""Synthetic integer four-tap Gaussian: native C versus Python oracle.

Compiles the exact C source used by the Switch build, then compares
PCM samples for a deterministic range of phases, histories and loops.
No proprietary game samples or external resources required.
"""
from __future__ import annotations

import ctypes
import random
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.interpolate_spu_gaussian import gaussian_voice_sample
from tools.spu_gaussian_table import GAUSS
from tools.simulate_spu_voice import SpuSampleCursor


class NativeGaussianTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="vh-native-gauss-")
        library = Path(cls.tmp.name) / "libvhgauss.so"
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-O2", "-fPIC", "-shared", "-Isource",
             "source/vh_spu_gaussian.c", "-o", str(library)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        lib = ctypes.CDLL(str(library))
        cls.fetch = lib.vh_spu_gaussian_sample
        cls.fetch.restype = ctypes.c_int16
        cls.fetch.argtypes = [
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t, ctypes.c_uint64,
            ctypes.c_int64, ctypes.c_int64, ctypes.c_int,
        ]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def compare(self, samples, index, fraction, loop_start, loop_end, looped):
        pcm = (ctypes.c_int16 * len(samples))(*samples)
        phase = (index << 12) | fraction
        actual = self.fetch(
            pcm, len(samples), phase, loop_start, loop_end, int(looped)
        )
        cursor = SpuSampleCursor(
            len(samples), loop_start, loop_end, 4096
        )
        cursor.phase = phase
        cursor.looped = looped
        expected = gaussian_voice_sample(samples, cursor)
        self.assertEqual(
            actual, expected,
            (index, fraction, loop_start, loop_end, looped, samples)
        )

    def test_all_512_coefficients_identical_to_python_source(self):
        native_source = (ROOT / "source/vh_spu_gaussian.c").read_text()
        declaration = re.search(
            r"static const int16_t gauss\[512\]\s*=\s*\{([^}]*)\};",
            native_source, re.S
        )
        self.assertIsNotNone(declaration)
        coeffs = tuple(int(n) for n in re.findall(r"-?\d+", declaration.group(1)))
        self.assertEqual(len(coeffs), 512)
        self.assertEqual(coeffs, GAUSS)

    def test_hardcoded_loop_and_first_sample_vectors(self):
        samples = [4000, 8000, 12000, 16000, 20000, 24000, 28000]
        for index, looped, result in [
            (0, False, -1), (1, False, 593),
            (2, False, 3991), (3, False, 7974),
            (2, True, 15944), (3, True, 18144),
        ]:
            self.compare(samples, index, 0, 2, 5, looped)
            array = (ctypes.c_int16 * len(samples))(*samples)
            self.assertEqual(
                self.fetch(array, len(samples), index << 12, 2, 5, int(looped)),
                result,
            )

    def test_randomized_signed_pcm_fractional_phase_and_loop(self):
        rng = random.Random(446622)
        for case in range(130):
            frames = 5 + (case % 39)
            samples = [rng.randint(-32768, 32767) for _ in range(frames)]
            start = (case * 7) % (frames - 1)
            end = start + 1 + ((case * 3) % (frames - start))
            for looped in (False, True):
                for _ in range(10):
                    index = rng.randrange(frames)
                    fraction = rng.randrange(4096)
                    self.compare(samples, index, fraction,
                                 start, end, looped)
            if case % 5 == 0:
                self.compare(samples, 0, 4095, -1, -1, False)

    def test_null_and_invalid_phase_return_silence(self):
        pcm = (ctypes.c_int16 * 3)(100, 200, 300)
        self.assertEqual(self.fetch(None, 3, 0, -1, -1, 0), 0)
        self.assertEqual(self.fetch(pcm, 0, 0, -1, -1, 0), 0)
        self.assertEqual(self.fetch(pcm, 3, 3 << 12, -1, -1, 0), 0)


if __name__ == "__main__":
    unittest.main()
