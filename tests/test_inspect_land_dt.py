"""Tests for raw LAND_DT texture-record inspection and comparison."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_land_dt import (
    BLOCK_SIZE,
    CLUT_DATA_OFFSET,
    CLUT_INDEX_OFFSET,
    compare_land_dt,
    inspect_land_dt,
)


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
            self.assertEqual(report["input_sha256"], hashlib.sha256(data).hexdigest())
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

    def test_accepts_custom_gfx_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map02.bin"
            data = bytearray(BLOCK_SIZE)
            data[78 * 4:78 * 4 + 4] = bytes((21, 22, 23, 24))
            data[95 * 4:95 * 4 + 4] = bytes((31, 32, 33, 34))
            data[CLUT_INDEX_OFFSET + 78] = 6
            data[CLUT_INDEX_OFFSET + 95] = 7
            path.write_bytes(data)

            report = inspect_land_dt(path, single_block=True, gfx_ids=(78, 95))
            self.assertEqual([r["gfx"] for r in report["records"]], [78, 95])
            self.assertEqual(report["records"][0]["bytes"], [21, 22, 23, 24])
            self.assertEqual(report["records"][1]["bytes"], [31, 32, 33, 34])
            self.assertEqual([r["clut_index"] for r in report["records"]], [6, 7])

    def test_compare_maps_reports_record_and_clut_differences(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "LAND_DT.DAT"
            data = bytearray(BLOCK_SIZE * 3)
            data[0 * BLOCK_SIZE + 241 * 4:0 * BLOCK_SIZE + 241 * 4 + 4] = bytes((1, 2, 3, 4))
            data[1 * BLOCK_SIZE + 241 * 4:1 * BLOCK_SIZE + 241 * 4 + 4] = bytes((1, 2, 3, 4))
            data[2 * BLOCK_SIZE + 241 * 4:2 * BLOCK_SIZE + 241 * 4 + 4] = bytes((0, 0, 0, 0))
            data[0 * BLOCK_SIZE + CLUT_INDEX_OFFSET + 241] = 5
            data[1 * BLOCK_SIZE + CLUT_INDEX_OFFSET + 241] = 5
            data[2 * BLOCK_SIZE + CLUT_INDEX_OFFSET + 241] = 0
            path.write_bytes(data)

            report = compare_land_dt(path, map_numbers=(0, 1, 2), gfx_ids=(241,))
            self.assertEqual(report["input_sha256"], hashlib.sha256(data).hexdigest())
            diff = report["differences"][0]
            self.assertTrue(diff["differs_between_maps"])
            self.assertEqual([v["raw_hex"] for v in diff["values"]], ["01 02 03 04", "01 02 03 04", "00 00 00 00"])
            self.assertEqual([v["clut_index"] for v in diff["values"]], [5, 5, 0])

    def test_compare_maps_reports_identical_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "LAND_DT.DAT"
            path.write_bytes(bytes(BLOCK_SIZE * 2))
            report = compare_land_dt(path, map_numbers=(0, 1), gfx_ids=(241, 243))
            self.assertFalse(any(d["differs_between_maps"] for d in report["differences"]))

    def test_compare_rejects_invalid_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "LAND_DT.DAT"
            path.write_bytes(bytes(BLOCK_SIZE))
            with self.assertRaisesRegex(ValueError, "at least two"):
                compare_land_dt(path, map_numbers=(0,))
            with self.assertRaisesRegex(ValueError, "outside the input"):
                compare_land_dt(path, map_numbers=(0, 1))
            with self.assertRaisesRegex(ValueError, "unique"):
                compare_land_dt(path, map_numbers=(0, 0))

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

    def test_rejects_invalid_gfx_index(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            with self.assertRaisesRegex(ValueError, "between 0 and 256"):
                inspect_land_dt(path, single_block=True, gfx_ids=(257,))

    def test_rejects_duplicate_gfx_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            with self.assertRaisesRegex(ValueError, "unique"):
                inspect_land_dt(path, single_block=True, gfx_ids=(241, 241))
            with self.assertRaisesRegex(ValueError, "unique"):
                compare_land_dt(path, map_numbers=(0, 1), gfx_ids=(241, 241))

    def test_rejects_noninteger_gfx_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            with self.assertRaisesRegex(ValueError, "integers"):
                inspect_land_dt(path, single_block=True, gfx_ids=(True, 243))
            with self.assertRaisesRegex(ValueError, "integers"):
                inspect_land_dt(path, single_block=True, gfx_ids=("241", 243))

    def test_rejects_empty_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.bin"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                inspect_land_dt(path)


if __name__ == "__main__":
    unittest.main()
