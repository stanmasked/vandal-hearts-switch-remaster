"""Synthetic tests for standalone VAB VH header metadata."""
import struct
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_vab_header import inspect_vab_header


class VABHeaderTests(unittest.TestCase):
    def test_header_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.vh"
            data = bytearray(32)
            data[:4] = b"pBAV"
            struct.pack_into("<III", data, 4, 7, 2, 4096)
            struct.pack_into("<HHHH", data, 16, 0, 3, 10, 5)
            struct.pack_into("<BBBB", data, 24, 127, 64, 0, 1)
            path.write_bytes(data)
            result = inspect_vab_header(path)
            self.assertEqual(result["header_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual((result["programs"], result["tones"], result["vags"]), (3, 10, 5))
            self.assertEqual((result["master_volume"], result["master_pan"]), (127, 64))
            self.assertFalse(result["program_table_complete"])
            self.assertEqual(path.read_bytes(), data)
            for bad in (b"", bytes(data[:31]), b"xxxx" + bytes(data[4:])):
                path.write_bytes(bad)
                with self.assertRaises(ValueError):
                    inspect_vab_header(path)
            data[18:20] = struct.pack("<H", 129)
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                inspect_vab_header(path)

    def test_fixed_program_table_and_packed_tone_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.vh"
            header = bytearray(32)
            header[:4] = b"pBAV"
            struct.pack_into("<HHHH", header, 16, 0, 2, 0, 3)
            programs = bytearray(128 * 16)
            programs[0:5] = bytes([2, 100, 0, 0, 64])
            programs[7 * 16:7 * 16 + 5] = bytes([1, 80, 0, 0, 32])
            path.write_bytes(header + programs)
            result = inspect_vab_header(path)
            self.assertTrue(result["program_table_complete"])
            self.assertEqual([item["program"] for item in result["populated_programs"]], [0, 7])
            self.assertEqual(result["packed_tone_blocks_bytes"], 1024)
            programs[7 * 16] = 17
            path.write_bytes(header + programs)
            with self.assertRaisesRegex(ValueError, "exceeds 16 tones"):
                inspect_vab_header(path)


    def test_tone_records_sparse_programs_and_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tonebank.vh"
            header = bytearray(32)
            header[:4] = b"pBAV"
            struct.pack_into("<HHHH", header, 16, 0, 2, 3, 3)
            programs = bytearray(128 * 16)
            programs[0] = 2
            programs[7 * 16] = 1
            tones = bytearray(2 * 16 * 32)

            def set_tone(offset, low, high, parent, vag):
                tones[offset + 4] = 60  # centre note
                tones[offset + 6] = low
                tones[offset + 7] = high
                struct.pack_into("<HHhh", tones, offset + 16,
                                 0x1234, 0x5678, parent, vag)

            set_tone(0, 20, 80, 0, 1)
            set_tone(32, 40, 100, 0, 2)
            set_tone(16 * 32, 50, 90, 7, 3)
            complete = bytes(header + programs + tones)
            path.write_bytes(complete)
            result = inspect_vab_header(path)
            self.assertTrue(result["tone_table_complete"])
            self.assertEqual(result["tone_table_sha256"], hashlib.sha256(tones).hexdigest())
            self.assertEqual(result["tone_table_offset"], 2080)
            self.assertEqual(result["vag_size_table_offset"], 3104)
            used = result["populated_programs"]
            self.assertEqual([(p["program"], p["block_index"]) for p in used],
                             [(0, 0), (7, 1)])
            self.assertEqual([t["vag"] for t in used[1]["active_tones"]], [3])
            self.assertEqual(used[1]["active_tones"][0]["key_min"], 50)
            self.assertEqual(used[1]["active_tones"][0]["adsr2"], 0x5678)
            self.assertEqual(path.read_bytes(), complete)

            # A partial transfer is not a fully validated tone table.
            path.write_bytes(complete[:-1])
            self.assertFalse(inspect_vab_header(path)["tone_table_complete"])

            # Invalid active tone references must fail, even after a program hole.
            tones[16 * 32 + 6] = 100
            tones[16 * 32 + 7] = 50
            path.write_bytes(header + programs + tones)
            with self.assertRaisesRegex(ValueError, "invalid key range"):
                inspect_vab_header(path)
            tones[16 * 32 + 6] = 50
            struct.pack_into("<h", tones, 16 * 32 + 20, 6)
            path.write_bytes(header + programs + tones)
            with self.assertRaisesRegex(ValueError, "wrong parent program"):
                inspect_vab_header(path)
            struct.pack_into("<h", tones, 16 * 32 + 20, 7)
            struct.pack_into("<h", tones, 16 * 32 + 22, 4)
            path.write_bytes(header + programs + tones)
            with self.assertRaisesRegex(ValueError, "VAG index out of range"):
                inspect_vab_header(path)


if __name__ == "__main__":
    unittest.main()
