"""Unit tests for the PS1 STR sector repacking utility."""
import sys
import tempfile
import unittest
from pathlib import Path

# Support direct execution via `python3 tests/test_restore_ps1_str.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.restore_ps1_str import RAW_CD_SECTOR_SIZE, SECTOR_SIZE, STR_MAGIC, repack


class RepackTests(unittest.TestCase):
    def test_repacks_sector_stream_and_counts_video_sectors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.str"
            destination = root / "repacked.str"
            video = STR_MAGIC + bytes(SECTOR_SIZE - len(STR_MAGIC))
            data = b"DATA" + bytes(SECTOR_SIZE - 4)
            source.write_bytes(video + data)

            sectors, video_sectors = repack(source, destination)

            self.assertEqual((sectors, video_sectors), (2, 1))
            output = destination.read_bytes()
            self.assertEqual(len(output), 2 * RAW_CD_SECTOR_SIZE)
            self.assertEqual(output[24:24 + SECTOR_SIZE], video)
            self.assertEqual(output[RAW_CD_SECTOR_SIZE + 24:RAW_CD_SECTOR_SIZE + 24 + SECTOR_SIZE], data)

    def test_rejects_input_not_aligned_to_sector_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "broken.str"
            destination = root / "out.str"
            source.write_bytes(b"not-a-sector")

            with self.assertRaisesRegex(ValueError, "not divisible"):
                repack(source, destination)

            self.assertFalse(destination.exists())

    def test_rejects_same_input_and_output_path_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.str"
            original = STR_MAGIC + bytes(SECTOR_SIZE - len(STR_MAGIC))
            source.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "must be different"):
                repack(source, source)

            self.assertEqual(source.read_bytes(), original)

    def test_empty_stream_is_valid_and_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "empty.str"
            destination = root / "out.str"
            source.write_bytes(b"")

            self.assertEqual(repack(source, destination), (0, 0))
            self.assertEqual(destination.read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
