"""Read-only VAB/VB size-table regressions using wholly synthetic assets."""
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_vab_header import inspect_vab_header


def fixture():
    header = bytearray(32)
    header[:4] = b"pBAV"
    struct.pack_into("<HHHH", header, 16, 0, 2, 3, 3)
    programs = bytearray(128 * 16)
    programs[0] = 2
    programs[7 * 16] = 1
    tones = bytearray(2 * 16 * 32)
    for start, parent, vag in ((0, 0, 1), (32, 0, 2), (16 * 32, 7, 3)):
        tones[start + 6] = 25
        tones[start + 7] = 100
        struct.pack_into("<HHhh", tones, start + 16, 0x101, 0x202, parent, vag)
    units = [0] * 256
    # Entry 0 is a leading region that must shift all playable VAG offsets.
    units[:4] = [2, 4, 6, 2]
    table = struct.pack("<256H", *units)
    return bytes(header + programs + tones), table


class VabSizesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vh = Path(self.tmp.name) / "bank.vh"
        self.vb = Path(self.tmp.name) / "bank.vb"

    def test_complete_table_and_vb_padding(self):
        vh, table = fixture()
        self.vh.write_bytes(vh + table)
        body = bytes(112 + 17)
        self.vb.write_bytes(body)
        result = inspect_vab_header(self.vh, self.vb)
        self.assertTrue(result["vag_size_table_complete"])
        self.assertTrue(result["vb_bounds_verified"])
        self.assertEqual(result["vag_size_table_sha256"], hashlib.sha256(table).hexdigest())
        self.assertEqual(result["vag_size_table_offset"], 3104)
        self.assertEqual(result["vag_zero_entry_bytes"], 16)
        self.assertEqual(result["required_vb_bytes"], 112)
        self.assertEqual(result["vb_trailing_bytes"], 17)
        self.assertEqual(
            [(item["vag"], item["offset_bytes"], item["size_bytes"])
             for item in result["vag_entries"]],
            [(1, 16, 32), (2, 48, 48), (3, 96, 16)]
        )
        self.assertEqual(self.vh.read_bytes(), vh + table)
        self.assertEqual(self.vb.read_bytes(), body)

    def test_incomplete_table_must_not_be_marked_valid(self):
        vh, table = fixture()
        self.vh.write_bytes(vh + table[:-1])
        result = inspect_vab_header(self.vh)
        self.assertFalse(result["vag_size_table_complete"])
        self.assertFalse(result["vb_bounds_verified"])
        self.vb.write_bytes(bytes(112))
        with self.assertRaisesRegex(ValueError, "cannot verify VB"):
            inspect_vab_header(self.vh, self.vb)

    def test_rejects_odd_units_and_empty_referenced_sample(self):
        vh, table = fixture()
        for entry, units, message in (
            (1, 3, "16-byte aligned"),
            (2, 0, "has no sample data"),
        ):
            with self.subTest(entry=entry):
                corrupt = bytearray(table)
                struct.pack_into("<H", corrupt, entry * 2, units)
                self.vh.write_bytes(vh + corrupt)
                with self.assertRaisesRegex(ValueError, message):
                    inspect_vab_header(self.vh)

    def test_rejects_truncated_vb_without_touching_source(self):
        vh, table = fixture()
        self.vh.write_bytes(vh + table)
        self.vb.write_bytes(bytes(111))
        with self.assertRaisesRegex(ValueError, "VB is truncated"):
            inspect_vab_header(self.vh, self.vb)
        self.assertEqual(self.vb.stat().st_size, 111)

    def test_rejects_vag_index_beyond_256_entry_table(self):
        vh, table = fixture()
        corrupt = bytearray(vh)
        struct.pack_into("<H", corrupt, 22, 256)
        self.vh.write_bytes(corrupt + table)
        with self.assertRaisesRegex(ValueError, "exceeds format limits"):
            inspect_vab_header(self.vh)


if __name__ == "__main__":
    unittest.main()
