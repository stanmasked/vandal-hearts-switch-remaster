"""Synthetic-only regression for the SEQ -> VAB note selection procedure."""
import io
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.resolve_vab_note import resolve_note


def make_sparse_bank():
    header = bytearray(32)
    header[:4] = b"pBAV"
    struct.pack_into("<HHHH", header, 16, 0, 3, 4, 4)
    header[24] = 127
    progs = bytearray(128 * 16)
    for program, count in ((0, 2), (7, 1), (10, 1)):
        progs[program * 16] = count
    tones = bytearray(3 * 16 * 32)
    specs = [
        (0, 0, 40, 60, 60, 0, 1),
        (0, 1, 40, 70, 70, 0x80, 2),
        (1, 0, 80, 100, 0xfe, 0x80, 3),
        (2, 0, 40, 50, 55, 0, 4),
    ]
    for block, slot, low, high, center, shift, vag in specs:
        offset = block * 16 * 32 + slot * 32
        tones[offset + 2] = 117
        tones[offset + 3] = 64
        tones[offset + 4] = center
        tones[offset + 5] = shift
        tones[offset + 6] = low
        tones[offset + 7] = high
        program = (0, 7, 10)[block]
        struct.pack_into("<HHhh", tones, offset + 16, 0x202, 0x303, program, vag)
    sizes = [0] * 256
    sizes[:5] = [2, 2, 2, 2, 2]
    vh = bytes(header + progs + tones + struct.pack("<256H", *sizes))
    vb = bytes(80)
    return vh, vb


class NoteSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vh = Path(self.temp.name) / "instruments.vh"
        self.vb = Path(self.temp.name) / "instruments.vb"
        self.original_vh, self.original_vb = make_sparse_bank()
        self.vh.write_bytes(self.original_vh)
        self.vb.write_bytes(self.original_vb)

    def pick(self, program, note, verify=True):
        return resolve_note(
            self.vh, program=program, note=note,
            vb=self.vb if verify else None
        )

    def test_first_range_match_in_requested_program(self):
        first = self.pick(0, 45)
        self.assertEqual((first["lookup"], first["selected_program"],
                          first["tone"], first["vag"]),
                         ("requested_program_range", 0, 0, 1))
        second = self.pick(0, 65)
        self.assertEqual((second["selected_program"], second["tone"], second["vag"]),
                         (0, 1, 2))
        self.assertEqual((second["center_signed"], second["shift_signed"]),
                         (70, -128))
        self.assertAlmostEqual(second["pitch_ratio_approx"], 2 ** (-4 / 12))
        self.assertEqual(second["pitch_step_approx"],
                         int(4096 * 2 ** (-4 / 12)))
        third = self.pick(10, 45)
        self.assertEqual((third["selected_program"], third["tone"], third["vag"]),
                         (10, 0, 4))

    def test_global_fallback_is_first_exact_range_in_sparse_program_order(self):
        result = self.pick(7, 45)
        self.assertEqual((result["lookup"], result["selected_program"],
                          result["tone"], result["vag"]),
                         ("global_range", 0, 0, 1))
        result = self.pick(99, 90)
        self.assertEqual((result["lookup"], result["selected_program"],
                          result["vag"]), ("global_range", 7, 3))
        self.assertEqual(result["center_signed"], -2)
        self.assertEqual(result["shift_signed"], -128)

    def test_nearest_fallback_measures_distance_to_lower_key_only(self):
        # Key 75 is closer to the *upper* bound of P0/T1 (70), but the
        # PC-port intentionally compares distance only to key_min.
        selected = self.pick(0, 75)
        self.assertEqual(
            (selected["lookup"], selected["selected_program"], selected["vag"]),
            ("global_nearest_lower_bound", 7, 3)
        )
        # Ties preserve earlier program and tone positions.
        tied = self.pick(99, 15)
        self.assertEqual((tied["selected_program"], tied["tone"]), (0, 0))

    def test_offsets_fingerprints_and_read_only(self):
        selected = self.pick(99, 42)
        self.assertEqual((selected["adpcm_offset_in_vb"],
                          selected["adpcm_size_bytes"]), (16, 16))
        self.assertTrue(selected["vb_bounds_verified"])
        self.assertEqual(len(selected["vh_header_sha256"]), 64)
        self.assertEqual(len(selected["tone_table_sha256"]), 64)
        self.assertEqual(len(selected["vag_size_table_sha256"]), 64)
        self.assertFalse(self.pick(99, 42, verify=False)["vb_bounds_verified"])
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_validation_and_incomplete_banks(self):
        for program, note in ((-1, 60), (128, 60), (True, 60),
                              (0, -1), (0, 128), (0, False)):
            with self.subTest(program=program, note=note):
                with self.assertRaises(ValueError):
                    self.pick(program, note)
        self.vh.write_bytes(self.original_vh[:-1])
        with self.assertRaisesRegex(ValueError, "cannot verify VB"):
            self.pick(0, 60)
        with self.assertRaisesRegex(ValueError, "complete VH"):
            self.pick(0, 60, verify=False)
        self.vh.write_bytes(self.original_vh)
        self.vb.write_bytes(self.original_vb[:-1])
        with self.assertRaisesRegex(ValueError, "VB is truncated"):
            self.pick(0, 60)

    def test_no_tones_is_not_a_selected_instrument(self):
        hdr = bytearray(32)
        hdr[:4] = b"pBAV"
        hdr += bytes(128 * 16 + 512)
        self.vh.write_bytes(hdr)
        with self.assertRaisesRegex(ValueError, "no playable tones"):
            self.pick(0, 60, verify=False)

    def test_json_cli_is_read_only(self):
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "tools/resolve_vab_note.py"),
            str(self.vh), "--vb", str(self.vb),
            "--program", "7", "--note", "45",
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["lookup"], "global_range")
        self.assertEqual(data["vag"], 1)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)


if __name__ == "__main__":
    unittest.main()
