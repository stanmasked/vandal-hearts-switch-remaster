"""Tests for raw CD-XA sector inspection."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_cdxa import SECTOR_SIZE, SYNC, inspect_raw_cd


def sector(submode=0x64, coding=0x01, mode=2, duplicate=True):
    result = bytearray(SECTOR_SIZE)
    result[:12] = SYNC
    result[15] = mode
    result[16:20] = bytes((1, 0, submode, coding))
    result[20:24] = result[16:20] if duplicate else bytes((1, 0, submode ^ 1, coding))
    return bytes(result)


class InspectCdXaTests(unittest.TestCase):
    def test_counts_valid_xa_form2_audio_sector(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "raw.bin"
            path.write_bytes(sector() + sector(submode=0x00))
            report = inspect_raw_cd(path)
            self.assertEqual(report["sectors"], 2)
            self.assertEqual(report["sync_ok"], 2)
            self.assertEqual(report["mode2"], 2)
            self.assertEqual(report["duplicate_subheaders"], 2)
            self.assertEqual(report["xa_audio"], 1)
            self.assertEqual(report["form2_audio"], 1)
            self.assertEqual(report["coding_info"], {1: 1})

    def test_ignores_mismatched_subheaders_for_xa_classification(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.bin"
            path.write_bytes(sector(duplicate=False))
            report = inspect_raw_cd(path)
            self.assertEqual(report["duplicate_subheaders"], 0)
            self.assertEqual(report["xa_audio"], 0)

    def test_ignores_non_mode2_sector(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mode1.bin"
            path.write_bytes(sector(mode=1))
            report = inspect_raw_cd(path)
            self.assertEqual(report["mode2"], 0)
            self.assertEqual(report["xa_audio"], 0)


    def test_inspects_only_requested_sector_range(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "raw.bin"
            path.write_bytes(sector(submode=0x00) + sector() + sector(submode=0x00))
            report = inspect_raw_cd(path, start_lba=1, sector_count=1)
            self.assertEqual(report["sectors"], 1)
            self.assertEqual(report["xa_audio"], 1)
            self.assertEqual(report["form2_audio"], 1)

    def test_rejects_out_of_bounds_sector_range(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "raw.bin"
            path.write_bytes(sector())
            with self.assertRaisesRegex(ValueError, "outside the input"):
                inspect_raw_cd(path, start_lba=1)
            with self.assertRaisesRegex(ValueError, "positive"):
                inspect_raw_cd(path, sector_count=0)
            with self.assertRaisesRegex(ValueError, "beyond input"):
                inspect_raw_cd(path, start_lba=0, sector_count=2)

    def test_rejects_empty_or_unaligned_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.bin"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                inspect_raw_cd(path)
            path.write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "not divisible"):
                inspect_raw_cd(path)


if __name__ == "__main__":
    unittest.main()
