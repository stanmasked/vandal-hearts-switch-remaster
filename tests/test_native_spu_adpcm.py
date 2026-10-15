"""Synthetic differential regression for native C11 Sony SPU-ADPCM decoder.

Compile the SAME C source used by the Switch AArch64 build, then compare
its PCM and metadata byte-for-byte to the established Python reference.
No game files, emulator, network or SDL2 dependencies.
"""
from __future__ import annotations
import ctypes
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.decode_spu_adpcm import decode_spu_blocks


class Info(ctypes.Structure):
    _fields_ = [
        ("blocks", ctypes.c_size_t),
        ("frames", ctypes.c_size_t),
        ("loop_start_frame", ctypes.c_int64),
        ("loop_end_frame", ctypes.c_int64),
        ("first_end_block", ctypes.c_int64),
    ]


class NativeSpuAdpcmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-spu-c11-")
        output = Path(cls.temp.name) / "libspu.so"
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-O2", "-fPIC", "-shared", "-Isource",
             "source/vh_spu_adpcm.c", "-o", str(output)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        cls.lib = ctypes.CDLL(str(output))
        cls.call = cls.lib.vh_spu_adpcm_decode
        cls.call.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t,
            ctypes.POINTER(Info),
        ]
        cls.call.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_native(self, raw, *, capacity=None):
        if capacity is None:
            capacity = len(raw) // 16 * 28
        source = (ctypes.c_uint8 * max(1, len(raw)))()
        for i, byte in enumerate(raw):
            source[i] = byte
        pcm = (ctypes.c_int16 * max(1, capacity))()
        info = Info()
        code = self.call(source, len(raw), pcm, capacity, ctypes.byref(info))
        return code, bytes(pcm) if capacity else b"", info

    def test_all_predictors_vs_python(self):
        rng = random.Random(19483)
        for run in range(110):
            blocks = []
            for b in range(1 + run % 9):
                predictor = (b + run) % 5
                shift = (b * 3 + run) % 13
                flags = (0, 4, 3, 1, 2)[(b + run) % 5]
                payload = bytes(rng.randrange(256) for _ in range(14))
                blocks.append(bytes([(predictor << 4) | shift, flags])
                              + payload)
            source = b"".join(blocks)
            expected = decode_spu_blocks(source)
            status, pcm, info = self.run_native(source)
            self.assertEqual(status, 0)
            self.assertEqual(pcm[:len(expected.pcm)], expected.pcm)
            self.assertEqual(info.frames, expected.frames)
            self.assertEqual(info.blocks, expected.block_count)
            self.assertEqual(
                (info.loop_start_frame, info.loop_end_frame,
                 info.first_end_block),
                tuple(-1 if field is None else field for field in
                      (expected.loop_start_frame,
                       expected.loop_end_frame,
                       expected.first_end_block)),
            )

    def test_loop_overrides_and_first_end(self):
        mark = bytes([12, 4] + [0x1f] * 14)
        repeat = bytes([12, 3] + [0x1f] * 14)
        trailing = bytes([12, 0] + [0x1f] * 14)
        native, pcm, info = self.run_native(mark + repeat + trailing)
        self.assertEqual(native, 0)
        self.assertEqual((info.loop_start_frame, info.loop_end_frame,
                          info.first_end_block), (0, 56, 1))
        self.assertEqual(struct.unpack_from("<hh", pcm), (-1, 1))

    def test_truncated_and_invalid_headers_never_partial_write(self):
        bad = [
            b"", bytes(15), bytes(17),
            bytes([0x50, 0] + [0] * 14),
            bytes([0x0d, 0] + [0] * 14),
            bytes([0x0c, 0x80] + [0] * 14),
        ]
        for raw in bad:
            with self.subTest(raw=raw[:2]):
                code, pcm, info = self.run_native(raw)
                self.assertEqual(code, -1)
        good = bytes([12, 0] + [0] * 14)
        self.assertEqual(self.run_native(good, capacity=27)[0], -1)
        mix = good + bytes([0x60, 0] + [0] * 14)
        self.assertEqual(self.run_native(mix)[0], -1)


if __name__ == "__main__":
    unittest.main()
