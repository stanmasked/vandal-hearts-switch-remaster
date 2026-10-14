"""Tests for raw LAND_DT texture-record inspection."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_land_dt import BLOCK_SIZE, CLUT_DATA_OFFSET, CLUT_INDEX_OFFSET, inspect_land_dt


class InspectLandDtTests(unittest.TestCase):
    def test_reads_target_records_from_selected_map_block(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "LAND_DT.DAT"
            data = bytearray(BLOCK_SIZE * 3)
            data[2 * BLOCK_SIZE + 241 * 4:2 * BLOCK_SIZE + 241 * 4 + 4] = bytes((7, 8, 9, 10))
            data[2 * BLOCK_SIZE + 243 * 4:2 * BLOCK_SIZE + 243 * 4 + 4] = bytes((11, 12, 13, 14))
            data[2 * BLOCK_SIZE + CLUT_INDEX_OFFSET + 241] = 40
            data[2 * BLOCK_SIZE + CLUT_INDEX_OFFSET + 243] = 41
            path.write_bytes(data)

            report = inspect_land_dt(path, map_number=2)
            first, second = report["records"]
            self.assertEqual(first["block_offset"], 964)
            self.assertEqual(first["absolute_input_offset"], 2 * BLOCK_SIZE + 964)
            self.assertEqual(first["bytes"], [7, 8, 9, 10])
            self.assertEqual(first["clut_index"], 40)
            self.assertEqual(second["block_offset"], 972)
            self.assertEqual(second["bytes"], [11, 12, 13, 14])
            self.assertEqual(second["clut_index"], 41)
            self.assertEqual(report["clut_data_offset"], CLUT_DATA_OFFSET)

    def test_accepts_one_extracted_block(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map02.bin"
            data = bytearray(BLOCK_SIZE)
            data[241 * 4:241 * 4 + 4] = bytes((1, 2, 3, 4))
            path.write_bytes(data)
            report = inspect_land_dt(path, single_block=True)
            self.assertIsNone(report["map_number"])
            self.assertEqual(report["records"][0]["bytes"], [1, 2, 3, 4])
            self.assertEqual(report["records"][0]["absolute_input_offset"], 964)

    def test_rejects_invalid_size_and_map_number(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.bin"
            path.write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "not divisible"):
                inspect_land_dt(path)
            with self.assertRaisesRegex(ValueError, "exactly"):
                inspect_land_dt(path, single_block=True)
            path.write_bytes(bytes(BLOCK_SIZE))
            with self.assertRaisesRegex(ValueError, "outside the input"):
                inspect_land_dt(path, map_number=2)

    def test_rejects_empty_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.bin"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                inspect_land_dt(path)


if __name__ == "__main__":
    unittest.main()
