"""Synthetic differential checks: native VAB bank versus Python note resolver.

Uses the same VH/VB fixture as test_resolve_vab_note. All audio data is
fabricated, memory-resident and never written to the repository.
"""
from __future__ import annotations

import ctypes
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_resolve_vab_note import make_sparse_bank
from tools.resolve_vab_note import resolve_note
from tools.mix_spu_stereo import seq_voice_gains
from tools.decode_spu_adpcm import decode_spu_blocks


class SeqTone(ctypes.Structure):
    _fields_ = [
        ("pcm", ctypes.POINTER(ctypes.c_int16)),
        ("frames", ctypes.c_size_t),
        ("loop_start", ctypes.c_int64),
        ("loop_end", ctypes.c_int64),
        ("pitch_step", ctypes.c_uint32),
        ("adsr1", ctypes.c_uint16),
        ("adsr2", ctypes.c_uint16),
        ("reverb_send", ctypes.c_uint),
        ("gain_left", ctypes.c_float),
        ("gain_right", ctypes.c_float),
    ]


class NativeVabDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-native-vab-")
        library = Path(cls.temp.name) / "libvab.so"
        subprocess.run(
            [
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                "-fPIC", "-shared", "-Isource",
                "source/vh_native_vab.c", "source/vh_spu_adpcm.c",
                "-lm", "-o", str(library),
            ],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        lib = ctypes.CDLL(str(library))
        cls.load = lib.vh_native_vab_load
        cls.load.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t,
        ]
        cls.load.restype = ctypes.c_int
        cls.resolve = lib.vh_native_vab_resolve
        cls.resolve.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(SeqTone),
        ]
        cls.resolve.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        vh, vb = make_sparse_bank()
        vh = bytearray(vh)
        # Give the sparse programs an audible master level for gain tests.
        for program in (0, 7, 10):
            vh[32 + program * 16 + 1] = 127
            vh[32 + program * 16 + 4] = 64
        self.vh = bytes(vh)
        self.vb = vb
        self.file_vh = Path(self.temp.name) / "synthetic.vh"
        self.file_vb = Path(self.temp.name) / "synthetic.vb"
        self.file_vh.write_bytes(self.vh)
        self.file_vb.write_bytes(self.vb)
        self.source_vh = (ctypes.c_uint8 * len(self.vh)).from_buffer_copy(self.vh)
        self.source_vb = (ctypes.c_uint8 * len(self.vb)).from_buffer_copy(self.vb)
        # Deliberately oversized aligned storage for opaque VhNativeVab,
        # whose native layout is owned by the C implementation.
        self.bank = (ctypes.c_longdouble * 16384)()
        self.pcm = (ctypes.c_int16 * 112)()
        self.assertEqual(
            self.load(
                self.bank, self.source_vh, len(self.vh),
                self.source_vb, len(self.vb), self.pcm, len(self.pcm),
            ), 0,
        )

    def test_requested_global_and_nearest_matches_python(self):
        for program, note in [
            (0, 45), (0, 65), (10, 45), (7, 45), (99, 90),
            (0, 75), (99, 15), (7, 95), (0, 60), (10, 51),
        ]:
            with self.subTest(program=program, note=note):
                python = resolve_note(
                    self.file_vh, program=program, note=note,
                    vb=self.file_vb,
                )
                result = SeqTone()
                self.assertEqual(self.resolve(
                    self.bank, program, note, 127, 127, 64,
                    ctypes.byref(result),
                ), 0)
                self.assertEqual(result.adsr1, python["adsr1"])
                self.assertEqual(result.adsr2, python["adsr2"])
                self.assertEqual(result.frames,
                                 python["adpcm_size_bytes"] // 16 * 28)
                self.assertLessEqual(
                    abs(result.pitch_step - min(16384, max(1, python["pitch_step_approx"]))),
                    1,
                )

    def test_pan_volume_velocity_matches_python_gain_law(self):
        for volume, velocity, pan in [
            (127, 127, 64), (90, 100, 32), (40, 80, 0),
            (127, 127, 127), (0, 100, 64),
        ]:
            with self.subTest(volume=volume, velocity=velocity, pan=pan):
                chosen = resolve_note(
                    self.file_vh, program=0, note=45, vb=self.file_vb,
                )
                result = SeqTone()
                self.assertEqual(self.resolve(
                    self.bank, 0, 45, velocity, volume, pan,
                    ctypes.byref(result),
                ), 0)
                left, right = seq_voice_gains(
                    velocity=velocity,
                    channel_volume=volume,
                    bank_volume=chosen["bank_master_volume"],
                    program_volume=chosen["program_volume"],
                    tone_volume=chosen["volume"],
                    tone_pan=chosen["pan"],
                    program_pan=chosen["program_pan"],
                    channel_pan=pan,
                )
                self.assertAlmostEqual(result.gain_left, left, places=5)
                self.assertAlmostEqual(result.gain_right, right, places=5)

    def test_bad_capacity_does_not_modify_bank_or_input(self):
        snapshot = bytes(self.bank)
        short = (ctypes.c_int16 * 111)()
        self.assertEqual(
            self.load(self.bank, self.source_vh, len(self.vh),
                      self.source_vb, len(self.vb), short, 111), -1
        )
        self.assertEqual(bytes(self.bank), snapshot)
        self.assertEqual(bytes(self.source_vh), self.vh)
        self.assertEqual(bytes(self.source_vb), self.vb)



def make_scene_switch_bank(bank_index: int) -> tuple[bytes, bytes]:
    """Exact 2-block synthetic pBAV/VB structure from the native
    decoded-bank audout integration, reconstructed independently in
    Python. VAG slot zero is intentionally empty: the playable sample
    is VB[16:48], with two ADPCM blocks and explicit loop flags.
    """
    if bank_index not in (0, 1):
        raise ValueError("synthetic bank index must be 0 or 1")
    vh = bytearray(32 + 128 * 16 + 512 + 512)
    vh[:4] = b"pBAV"
    vh[18], vh[20], vh[22], vh[24] = 8, 1, 1, 127
    program = 32 + 7 * 16
    vh[program] = 1
    vh[program + 1] = 127
    vh[program + 4] = 64
    tone = 32 + 128 * 16
    vh[tone + 1] = 4  # VagAtr.mode bit 2: STUDIO_C reverb send
    vh[tone + 2], vh[tone + 3], vh[tone + 4] = 127, 64, 60
    vh[tone + 6], vh[tone + 7], vh[tone + 16] = 40, 100, 15
    vh[tone + 20], vh[tone + 22] = 7, 1
    vh[tone + 512], vh[tone + 514] = 2, 4
    vb = bytearray(48)
    vb[16:18] = bytes((2, 4))
    vb[18:32] = bytes([0x44 if bank_index else 0x22] * 14)
    vb[32:34] = bytes((2, 3))
    vb[34:48] = bytes([0xDD if bank_index else 0xEE] * 14)
    return bytes(vh), bytes(vb)


class DecodedSceneBankPcmReferenceTests(unittest.TestCase):
    """Independent Python SPU-ADPCM reconstruction of the EXACT two
    synthetic banks sent through native SEQ/SPU/audout in the C test.
    Full mono PCM16 samples are checked, not only note metadata.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-scene-vb-")
        dll = Path(cls.temp.name) / "scene-vab.so"
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
             "-fPIC", "-shared", "-Isource", "source/vh_native_vab.c",
             "source/vh_spu_adpcm.c", "-lm", "-o", str(dll)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        lib = ctypes.CDLL(str(dll))
        cls.load = lib.vh_native_vab_load
        cls.load.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t,
        ]
        cls.load.restype = ctypes.c_int
        cls.resolve = lib.vh_native_vab_resolve
        cls.resolve.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.POINTER(SeqTone),
        ]
        cls.resolve.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def native_bank(self, vh: bytes, vb: bytes):
        bank = (ctypes.c_longdouble * 16384)()
        pcm = (ctypes.c_int16 * 56)()
        h = (ctypes.c_uint8 * len(vh)).from_buffer_copy(vh)
        b = (ctypes.c_uint8 * len(vb)).from_buffer_copy(vb)
        self.assertEqual(self.load(bank, h, len(h), b, len(b),
                                   pcm, len(pcm)), 0)
        tone = SeqTone()
        self.assertEqual(self.resolve(bank, 7, 60, 110, 127, 64,
                                      ctypes.byref(tone)), 0)
        self.assertEqual(tone.frames, 56)
        self.assertEqual(tone.reverb_send, 1)
        self.assertEqual(tone.adsr1, 15)
        self.assertEqual(tone.loop_start, 0)
        self.assertEqual(tone.loop_end, 56)
        self.assertEqual(ctypes.addressof(pcm),
                         ctypes.addressof(tone.pcm.contents))
        return pcm, tone

    def test_two_decoded_scene_banks_match_independent_python_adpcm(self):
        reference_pcm = []
        for bank_index in (0, 1):
            with self.subTest(bank=bank_index):
                vh, vb = make_scene_switch_bank(bank_index)
                native_pcm, tone = self.native_bank(vh, vb)
                independently_decoded = decode_spu_blocks(vb[16:48])
                self.assertEqual(independently_decoded.block_count, 2)
                self.assertEqual(independently_decoded.frames, 56)
                self.assertEqual(independently_decoded.loop_start_frame, 0)
                self.assertEqual(independently_decoded.loop_end_frame, 56)
                expected = struct.unpack("<56h", independently_decoded.pcm)
                self.assertEqual(list(native_pcm), list(expected))
                self.assertEqual([tone.pcm[i] for i in range(56)],
                                 list(expected))
                self.assertNotEqual(set(expected), {0})
                reference_pcm.append(tuple(expected))

                # Mutate a single nibble in the source VB, so both
                # algorithms must change the corresponding decoded
                # PCM sample. This proves the oracle is sensitive.
                modified = bytearray(vb)
                modified[18] ^= 1
                altered_python = decode_spu_blocks(bytes(modified[16:48]))
                altered_native, _ = self.native_bank(vh, bytes(modified))
                self.assertNotEqual(altered_python.pcm,
                                    independently_decoded.pcm)
                self.assertEqual(list(altered_native),
                                 list(struct.unpack("<56h",
                                                    altered_python.pcm)))
                self.assertNotEqual(list(altered_native), list(native_pcm))
        self.assertNotEqual(reference_pcm[0], reference_pcm[1])

    def test_alternating_scene_rebind_keeps_each_reference_bank_immutable(self):
        fixtures = [make_scene_switch_bank(i) for i in (0, 1)]
        native = [self.native_bank(*pair) for pair in fixtures]
        oracles = [struct.unpack(
            "<56h", decode_spu_blocks(pair[1][16:48]).pcm
        ) for pair in fixtures]
        for scene in range(16):
            selected = scene % 2
            with self.subTest(scene=scene):
                pcm, tone = native[selected]
                self.assertEqual(tuple(pcm), oracles[selected])
                self.assertEqual(tuple(tone.pcm[i] for i in range(56)),
                                 oracles[selected])
                self.assertEqual(tone.reverb_send, 1)
        # The alternate bank is never modified by a scene selection.
        for selected in (0, 1):
            self.assertEqual(tuple(native[selected][0]), oracles[selected])


if __name__ == "__main__":
    unittest.main()
