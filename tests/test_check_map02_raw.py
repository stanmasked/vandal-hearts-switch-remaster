"""Independent synthetic regressions for raw LAND_DT map-02 observation check."""
import tempfile
import unittest
from pathlib import Path

from tools.inspect_land_dt import BLOCK_SIZE, CLUT_INDEX_OFFSET, inspect_land_dt
from tools.check_map02_raw import check_raw_records


class CheckMap02RawTests(unittest.TestCase):
    def test_zero_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            self.assertEqual(check_raw_records(inspect_land_dt(path, single_block=True)), [])

    def test_nonzero_record_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            data = bytearray(BLOCK_SIZE)
            data[241 * 4] = 1
            path.write_bytes(data)
            self.assertTrue(any("GFX 241" in e for e in
                check_raw_records(inspect_land_dt(path, single_block=True))))

    def test_wrong_clut_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            data = bytearray(BLOCK_SIZE)
            data[CLUT_INDEX_OFFSET + 243] = 33
            path.write_bytes(data)
            self.assertTrue(any("GFX 243" in e for e in
                check_raw_records(inspect_land_dt(path, single_block=True))))

    def test_rejects_wrong_map(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "land.bin"
            path.write_bytes(bytes(BLOCK_SIZE * 3))
            self.assertTrue(check_raw_records(inspect_land_dt(path, map_number=1)))


if __name__ == "__main__":
    unittest.main()
