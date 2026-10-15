"""Synthetic raw-disc tests for read-only CD-XA stream inventory."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inventory_cdxa_streams import inventory_streams


def sector(file_no=1, channel=0, submode=0x64, coding=1, *, valid=True,
           duplicate=True):
    data = bytearray(2352)
    if valid:
        data[:12] = b"\x00" + b"\xff" * 10 + b"\x00"
        data[15] = 2
    data[16:20] = bytes((file_no, channel, submode, coding))
    data[20:24] = data[16:20] if duplicate else b"\x00" * 4
    return bytes(data)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "disc.bin"

    def test_interleaved_streams_and_coding(self):
        self.source.write_bytes(b"".join([
            sector(7, 3), sector(1, 0), sector(1, 1),
            sector(1, 0, 0x65), sector(1, 0, 0xE4, coding=0),
            sector(9, 9, 0x00), sector(5, 4, duplicate=False),
            sector(1, 0), sector(valid=False),
        ]))
        found = inventory_streams(self.source)
        self.assertEqual(found["audio_sectors"], 6)
        self.assertEqual(found["invalid_duplicate_subheaders"], 1)
        self.assertEqual(found["unsupported_coding_sectors"], 1)
        self.assertEqual(
            [(s["file_number"], s["channel"], s["audio_sectors"])
             for s in found["streams"]], [(1, 0, 4), (1, 1, 1), (7, 3, 1)])
        primary = found["streams"][0]
        self.assertEqual((primary["first_lba"], primary["last_lba"]), (1, 7))
        self.assertEqual(primary["contiguous_runs"], 3)
        self.assertEqual(primary["max_gap_sectors"], 2)
        self.assertEqual(primary["coding_counts"], {"0x00": 1, "0x01": 3})
        self.assertEqual(primary["end_of_record_sectors"], 1)
        self.assertEqual(primary["end_of_file_sectors"], 1)
        self.assertEqual(inventory_streams(self.source, start_lba=2, sector_count=2)[
            "audio_sectors"], 2)

    def test_rejects_invalid_ranges_and_alignment(self):
        self.source.write_bytes(sector())
        for options in ({"start_lba": -1}, {"start_lba": 1},
                        {"sector_count": 0}, {"sector_count": 2},
                        {"sector_count": -1}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    inventory_streams(self.source, **options)
        self.source.write_bytes(sector() + b"x")
        with self.assertRaisesRegex(ValueError, "2352"):
            inventory_streams(self.source)
        self.source.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "2352"):
            inventory_streams(self.source)

    def test_empty_metadata_and_read_only(self):
        data = sector(1, 0, submode=0x00) + sector(valid=False)
        self.source.write_bytes(data)
        got = inventory_streams(self.source)
        self.assertEqual(got["audio_sectors"], 0)
        self.assertEqual(got["streams"], [])
        self.assertEqual(self.source.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
