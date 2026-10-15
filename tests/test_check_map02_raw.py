"""Independent synthetic regressions for raw LAND_DT map-02 observation check."""
import tempfile
import unittest
from pathlib import Path

from tools.inspect_land_dt import BLOCK_SIZE, CLUT_INDEX_OFFSET, inspect_land_dt
from tools.check_map02_raw import check_block_hash, check_raw_records


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

    def test_duplicate_gfx_in_report_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["records"].append(dict(report["records"][0]))
            errors = check_raw_records(report)
            self.assertIn("duplicate GFX 241 in inspection report", errors)

    def test_tampered_texture_offset_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["records"][0]["absolute_input_offset"] += 4
            self.assertTrue(any("absolute_input_offset" in e for e in
                                check_raw_records(report)))

    def test_tampered_clut_offset_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["records"][1]["absolute_clut_index_offset"] -= 1
            self.assertTrue(any("absolute_clut_index_offset" in e for e in
                                check_raw_records(report)))

    def test_tampered_block_base_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["block_base_offset"] = -1
            self.assertIn("invalid LAND_DT block base offset",
                          check_raw_records(report))

    def test_rejects_wrong_full_stream_block_base(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "land.bin"
            path.write_bytes(bytes(BLOCK_SIZE * 3))
            report = inspect_land_dt(path, map_number=2)
            report["block_base_offset"] = BLOCK_SIZE
            errors = check_raw_records(report)
            self.assertIn(f"LAND_DT block base offset expected {2 * BLOCK_SIZE}", errors)

    def test_rejects_nonzero_single_block_base(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["block_base_offset"] = BLOCK_SIZE
            errors = check_raw_records(report)
            self.assertIn("LAND_DT block base offset expected 0", errors)

    def test_raw_hex_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["records"][0]["raw_hex"] = "01 00 00 00"
            self.assertTrue(any("raw_hex does not match bytes" in e for e in
                                check_raw_records(report)))

    def test_invalid_raw_byte_type_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["records"][1]["bytes"] = [False, 0, 0, 0]
            self.assertTrue(any("invalid raw texture bytes" in e for e in
                                check_raw_records(report)))

    def test_boolean_clut_index_is_not_integer_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["records"][0]["clut_index"] = False
            self.assertIn("GFX 241: CLUT index must be integer zero",
                          check_raw_records(report))

    def test_expected_block_hash_matches_extracted_block(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            self.assertEqual(check_block_hash(report, report["block_sha256"]), [])
            self.assertEqual(check_block_hash(report, report["block_sha256"].upper()), [])

    def test_expected_block_hash_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            self.assertTrue(check_block_hash(report, "0" * 64 if report["block_sha256"] != "0" * 64 else "1" * 64))
            self.assertTrue(check_block_hash(report, "not-a-sha256"))

    def test_inconsistent_single_block_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["map_number"] = 2
            self.assertIn("single-block report must have null map_number",
                          check_raw_records(report))

    def test_false_single_block_flag_requires_map_two(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["single_block"] = False
            self.assertIn("expected map block 2", check_raw_records(report))

    def test_nonboolean_single_block_flag_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map02.bin"
            path.write_bytes(bytes(BLOCK_SIZE))
            report = inspect_land_dt(path, single_block=True)
            report["single_block"] = 1
            self.assertIn("single_block flag must be boolean", check_raw_records(report))

    def test_rejects_wrong_map(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "land.bin"
            path.write_bytes(bytes(BLOCK_SIZE * 3))
            self.assertTrue(check_raw_records(inspect_land_dt(path, map_number=1)))


if __name__ == "__main__":
    unittest.main()
