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

    def test_full_keyspace_across_synthetic_sparse_bank_variants(self):
        """Compare C PCM selection with the PC-port-style Python resolver.

        Six constructed VH layouts exercise inclusive key edges,
        overlapping tone slots, sparse programs, singleton regions,
        key_min-distance ties, and first-global-range precedence.
        VAG PCM pointers distinguish tones even when ADSR matches.
        """
        key_layouts = (
            ("baseline", ((40, 60), (40, 70), (80, 100), (40, 50))),
            ("all_overlap", ((0, 127), (0, 127), (0, 127), (0, 127))),
            ("single_notes", ((0, 0), (127, 127), (64, 64), (65, 65))),
            ("nearest_ties", ((10, 15), (30, 35), (50, 55), (70, 75))),
            ("cross_program", ((0, 30), (80, 100), (40, 60), (20, 45))),
            ("outer_edges", ((0, 0), (0, 0), (127, 127), (127, 127))),
        )
        tone_offsets = (2080, 2080 + 32, 2080 + 512, 2080 + 1024)
        pcm_base = ctypes.addressof(self.pcm)
        checks = 0
        for label, ranges in key_layouts:
            with self.subTest(bank=label):
                vh = bytearray(self.vh)
                for offset, (low, high) in zip(tone_offsets, ranges):
                    vh[offset + 6] = low
                    vh[offset + 7] = high
                self.file_vh.write_bytes(vh)
                native_vh = (ctypes.c_uint8 * len(vh)).from_buffer_copy(vh)
                self.assertEqual(
                    self.load(
                        self.bank, native_vh, len(vh),
                        self.source_vb, len(self.vb),
                        self.pcm, len(self.pcm),
                    ), 0, label,
                )
                # 0/7/10 are populated; 99 and 127 are sparse and must
                # use a global match or nearest lower-bound fallback.
                for program in (0, 7, 10, 99, 127):
                    for note in range(128):
                        reference = resolve_note(
                            self.file_vh, program=program, note=note,
                            vb=self.file_vb,
                        )
                        native = SeqTone()
                        self.assertEqual(
                            self.resolve(self.bank, program, note,
                                         127, 127, 64, ctypes.byref(native)),
                            0, (label, program, note),
                        )
                        vag = reference["vag"]
                        self.assertEqual(
                            ctypes.cast(native.pcm, ctypes.c_void_p).value,
                            pcm_base + (vag - 1) * 28 * ctypes.sizeof(ctypes.c_int16),
                            (label, program, note, reference["lookup"],
                             reference["selected_program"],
                             reference["tone"], vag),
                        )
                        self.assertEqual(native.frames, 28)
                        self.assertEqual(native.adsr1, reference["adsr1"])
                        self.assertEqual(native.adsr2, reference["adsr2"])
                        expected_pitch = min(
                            16384, max(1, reference["pitch_step_approx"])
                        )
                        self.assertLessEqual(
                            abs(native.pitch_step - expected_pitch), 1,
                            (label, program, note),
                        )
                        checks += 1
        self.assertEqual(checks, 6 * 5 * 128)

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

    def test_sparse_alias_gain_pan_matches_python_oracle(self):
        """Same VAG, different ProgAtr: compare all gain/pan stages."""
        vh = bytearray(self.vh)
        for program, volume, pan in (
            (1, 95, 0), (7, 127, 127),
            (8, 63, 64), (10, 127, 127),
        ):
            offset = 32 + program * 16
            vh[offset + 1] = volume
            vh[offset + 4] = pan
        source = (ctypes.c_uint8 * len(vh)).from_buffer_copy(vh)
        self.assertEqual(self.load(
            self.bank, source, len(vh), self.source_vb, len(self.vb),
            self.pcm, len(self.pcm),
        ), 0)
        # p2 keeps its zero-valued ProgAtr, but aliases the same
        # VAG3 used by audible p1/p7. p8 aliases p10's VAG4.
        cases = (
            (1, 90, 3, 95, 0),
            (7, 90, 3, 127, 127),
            (2, 90, 3, 0, 0),
            (8, 45, 4, 63, 64),
            (10, 45, 4, 127, 127),
        )
        base = ctypes.addressof(self.pcm)
        compared = 0
        for program, note, vag, program_volume, program_pan in cases:
            for velocity in (40, 100, 127):
                for channel_volume in (40, 90, 127):
                    for channel_pan in (0, 32, 64, 96, 127):
                        with self.subTest(
                            program=program, note=note,
                            velocity=velocity, volume=channel_volume,
                            pan=channel_pan,
                        ):
                            tone = SeqTone()
                            self.assertEqual(
                                self.resolve(self.bank, program, note,
                                             velocity, channel_volume,
                                             channel_pan,
                                             ctypes.byref(tone)), 0,
                            )
                            self.assertEqual(
                                ctypes.cast(tone.pcm, ctypes.c_void_p).value,
                                base + (vag - 1) * 28 * 2,
                            )
                            left, right = seq_voice_gains(
                                velocity=velocity,
                                channel_volume=channel_volume,
                                bank_volume=127,
                                program_volume=program_volume,
                                tone_volume=117,
                                tone_pan=64,
                                program_pan=program_pan,
                                channel_pan=channel_pan,
                            )
                            self.assertAlmostEqual(
                                tone.gain_left, left, places=5,
                            )
                            self.assertAlmostEqual(
                                tone.gain_right, right, places=5,
                            )
                            compared += 1
        self.assertEqual(compared, 225)

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


if __name__ == "__main__":
    unittest.main()
