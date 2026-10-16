"""Independent integer STUDIO_C SPU reverb reference vs the native C11 module.

Reference behavior follows HalmyLyseas/VandalHearts-PcPort's
platform/pc/src/pc_spu.c RevProcess and the PS1 STUDIO_C preset.
Input is fully synthetic; no game recordings or VH/VB assets.
Tests signed truncation, circular buffer wrap, stereo feedback,
39-tap 44.1k/22.05k FIR resampling and lingering silent tails.
"""
from __future__ import annotations

import ctypes
import math
import random
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = 0x37F0
TAPS = 39

# Independent source-defined constants, not imported from C.
REG = [
    0x00E3, 0x00A9, 0x6F60, 0x4FA8, 0xBCE0, 0x4510, 0xBEF0, 0xA680,
    0x5680, 0x52C0, 0x0DFB, 0x0B58, 0x0D09, 0x0A3C, 0x0BD9, 0x0973,
    0x0B59, 0x08DA, 0x08D9, 0x05E9, 0x07EC, 0x04B0, 0x06EF, 0x03D2,
    0x05EA, 0x031D, 0x031C, 0x0238, 0x0154, 0x00AA, 0x8000, 0x8000,
]
FIR = [
    -1, 0, 2, 0, -10, 0, 35, 0, -103, 0, 266, 0, -616, 0, 1332,
    0, -2960, 0, 10246, 16384, 10246, 0, -2960, 0, 1332, 0,
    -616, 0, 266, 0, -103, 0, 35, 0, -10, 0, 2, 0, -1,
]
(
    DAPF1, DAPF2, VIIR, VCOMB1, VCOMB2, VCOMB3, VCOMB4, VWALL,
    VAPF1, VAPF2, MLSAME, MRSAME, MLCOMB1, MRCOMB1, MLCOMB2,
    MRCOMB2, DLSAME, DRSAME, MLDIFF, MRDIFF, MLCOMB3, MRCOMB3,
    MLCOMB4, MRCOMB4, DLDIFF, DRDIFF, MLAPF1, MRAPF1, MLAPF2,
    MRAPF2, VLIN, VRIN,
) = range(32)


def s16(value: int) -> int:
    return value if value < 32768 else value - 65536


def clip(value: int) -> int:
    return min(32767, max(-32768, value))


def truncdiv(value: int, denom: int) -> int:
    return value // denom if value >= 0 else -((-value) // denom)


def mul(value: int, reg: int) -> int:
    return truncdiv(value * s16(REG[reg]), 32768)


class StudioC:
    def __init__(self):
        self.work = [0] * WORK
        self.in_l = [0] * TAPS
        self.in_r = [0] * TAPS
        self.out_l = [0] * TAPS
        self.out_r = [0] * TAPS
        self.cursor = self.icur = self.ocur = self.phase = 0

    def off(self, reg: int) -> int:
        return REG[reg] * 4

    def rd(self, reg: int, delta: int = 0) -> int:
        return self.work[(self.cursor + self.off(reg) + delta) % WORK]

    def rd_at(self, delta: int) -> int:
        return self.work[(self.cursor + delta) % WORK]

    def wr(self, reg: int, value: int) -> None:
        self.work[(self.cursor + self.off(reg)) % WORK] = clip(value)

    @staticmethod
    def fir(hist: list[int], cursor: int) -> int:
        return clip(truncdiv(sum(FIR[i] * hist[(cursor+i) % TAPS]
                                 for i in range(TAPS)), 32768))

    def reflect(self, source: int, feedback: int, target: int) -> int:
        prev = self.rd(target, -1)
        fb = mul(self.rd(feedback), VWALL)
        return mul(source + fb - prev, VIIR) + prev

    def comb(self, first: int) -> int:
        return sum(mul(self.rd(first+delta), vol) for delta, vol in
                   ((0, VCOMB1), (2, VCOMB2),
                    (8, VCOMB3), (10, VCOMB4)))

    def allpass(self, value: int, apf: int, delay: int, volume: int) -> int:
        offset = self.off(apf) - self.off(delay)
        delayed = self.rd_at(offset)
        stored = value - mul(delayed, volume)
        self.wr(apf, stored)
        delayed = self.rd_at(offset)
        return delayed + mul(stored, volume)

    def step(self, left: int, right: int, depth: float) -> tuple[int, int]:
        self.in_l[self.icur] = clip(left)
        self.in_r[self.icur] = clip(right)
        self.icur = (self.icur + 1) % TAPS
        self.phase ^= 1
        if self.phase == 0:
            il = mul(self.fir(self.in_l, self.icur), VLIN)
            ir = mul(self.fir(self.in_r, self.icur), VRIN)
            sl = self.reflect(il, DLSAME, MLSAME)
            sr = self.reflect(ir, DRSAME, MRSAME)
            dl = self.reflect(il, DRDIFF, MLDIFF)
            dr = self.reflect(ir, DLDIFF, MRDIFF)
            for reg, value in ((MLSAME, sl), (MRSAME, sr),
                               (MLDIFF, dl), (MRDIFF, dr)):
                self.wr(reg, value)
            l = self.comb(MLCOMB1)
            r = self.comb(MRCOMB1)
            l = self.allpass(l, MLAPF1, DAPF1, VAPF1)
            r = self.allpass(r, MRAPF1, DAPF1, VAPF1)
            l = self.allpass(l, MLAPF2, DAPF2, VAPF2)
            r = self.allpass(r, MRAPF2, DAPF2, VAPF2)
            self.out_l[self.ocur] = clip(l)
            self.out_r[self.ocur] = clip(r)
            self.ocur = (self.ocur + 1) % TAPS
            self.cursor = (self.cursor + 1) % WORK
        else:
            self.out_l[self.ocur] = 0
            self.out_r[self.ocur] = 0
            self.ocur = (self.ocur + 1) % TAPS
        l = clip(self.fir(self.out_l, self.ocur) * 2)
        r = clip(self.fir(self.out_r, self.ocur) * 2)
        return math.trunc(l * depth), math.trunc(r * depth)


class NativeReverb(ctypes.Structure):
    _fields_ = [
        ("work", ctypes.c_int16 * WORK),
        ("in_l", ctypes.c_int16 * TAPS),
        ("in_r", ctypes.c_int16 * TAPS),
        ("out_l", ctypes.c_int16 * TAPS),
        ("out_r", ctypes.c_int16 * TAPS),
        ("cursor", ctypes.c_int),
        ("in_cursor", ctypes.c_int),
        ("out_cursor", ctypes.c_int),
        ("phase", ctypes.c_int),
    ]


class NativeStudioCReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="vh-native-reverb-")
        dll = Path(cls.tmp.name) / "studio_c.so"
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-O2", "-shared", "-fPIC", "-Isource",
             "source/vh_spu_reverb.c", "-lm", "-o", str(dll)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        lib = ctypes.CDLL(str(dll))
        cls.reset = lib.vh_spu_reverb_reset
        cls.reset.argtypes = [ctypes.POINTER(NativeReverb)]
        cls.step_native = lib.vh_spu_reverb_process
        cls.step_native.argtypes = [
            ctypes.POINTER(NativeReverb), ctypes.c_int, ctypes.c_int,
            ctypes.c_float, ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_studio_c_coefficients_are_identical_to_source_reference(self):
        source = (ROOT / "source/vh_spu_reverb.c").read_text()
        def read_array(name: str) -> list[int]:
            match = re.search(
                r"static const int16_t\s+" + name +
                r"\[[^]]+\]\s*=\s*\{([^}]*)\};", source, re.S)
            self.assertIsNotNone(match)
            return [int(x) for x in re.findall(r"-?\d+", match.group(1))]
        self.assertEqual(read_array("studio_c"), [s16(n) for n in REG])
        self.assertEqual(read_array("fir"), FIR)
        self.assertEqual(ctypes.sizeof(NativeReverb),
                         2*(WORK+4*TAPS)+16)

    def test_integer_pcm_matches_pc_studio_c_reference_through_wrap_and_tail(self):
        ref = StudioC()
        native = NativeReverb()
        self.reset(ctypes.byref(native))
        rng = random.Random(1730173)
        out_l = ctypes.c_int(0)
        out_r = ctypes.c_int(0)
        heard_tail = False
        # Cursor wraps after 2*0x37f0 input frames (28640 frames).
        # Continue well beyond this and compare its silent tail.
        for i in range(48000):
            if i < 4500:
                left, right = 12000, -9400
            elif i < 14500:
                left, right = rng.randint(-18000, 18000), rng.randint(-18000, 18000)
            else:
                left = right = 0
            depth = 1.0 if i < 20000 else 0.5
            expected = ref.step(left, right, depth)
            self.step_native(ctypes.byref(native), left, right, depth,
                             ctypes.byref(out_l), ctypes.byref(out_r))
            self.assertEqual((out_l.value, out_r.value), expected,
                             f"at source frame {i}")
            if i >= 14500 and (out_l.value or out_r.value):
                heard_tail = True
            if i % 1024 == 0 or i == 47999:
                self.assertEqual(native.cursor, ref.cursor)
                self.assertEqual(native.phase, ref.phase)
                self.assertEqual(native.in_cursor, ref.icur)
                self.assertEqual(native.out_cursor, ref.ocur)
                self.assertEqual(list(native.work), ref.work)
        self.assertTrue(heard_tail)
        self.assertEqual(ref.cursor, 48000//2 % WORK)
        self.assertEqual(native.cursor, ref.cursor)


if __name__ == "__main__":
    unittest.main()
