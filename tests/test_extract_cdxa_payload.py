"""Tests for the non-destructive CD-XA payload extractor."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.extract_cdxa_payload import SECTOR_SIZE, SYNC, extract_audio_payloads


def sector(file_no=1, channel=0, submode=0x64, coding=0x01, mode=2, duplicate=True, marker=0x55):
    data = bytearray([marker] * SECTOR_SIZE)
    data[:12] = SYNC
    data[15] = mode
    header = bytes((file_no, channel, submode, coding))
    data[16:20] = header
    data[20:24] = header if duplicate else bytes((file_no, channel, submode ^ 1, coding))
    return bytes(data)


class ExtractCdXaPayloadTests(unittest.TestCase):
    def test_writes_only_valid_audio_form2_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst, report_path = root / "disc.bin", root / "payload.bin", root / "report.json"
            src.write_bytes(sector(marker=0x11) + sector(submode=0x00, marker=0x22) +
                            sector(duplicate=False, marker=0x33) + sector(mode=1, marker=0x44))
            report = extract_audio_payloads(src, dst, report_path=report_path)
            self.assertEqual(dst.read_bytes(), bytes([0x11]) * 2324)
            self.assertEqual(report["audio_form2_sectors_written"], 1)
            self.assertEqual(report["payload_bytes_written"], 2324)
            self.assertTrue(report_path.is_file())

    def test_filters_by_channel_and_file_number(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst = root / "disc.bin", root / "payload.bin"
            src.write_bytes(sector(channel=0, file_no=1, marker=0x10) +
                            sector(channel=1, file_no=1, marker=0x20) +
                            sector(channel=0, file_no=2, marker=0x30))
            extract_audio_payloads(src, dst, channel=1, file_number=1)
            self.assertEqual(dst.read_bytes(), bytes([0x20]) * 2324)

    def test_rejects_bad_ranges_and_source_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "disc.bin"
            src.write_bytes(sector())
            with self.assertRaisesRegex(ValueError, "outside the input"):
                extract_audio_payloads(src, Path(temp) / "out.bin", start_lba=1)
            with self.assertRaisesRegex(ValueError, "beyond input"):
                extract_audio_payloads(src, Path(temp) / "out.bin", sector_count=2)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                extract_audio_payloads(src, src)

    def test_rejects_empty_and_unaligned_input(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "disc.bin"
            src.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                extract_audio_payloads(src, Path(temp) / "out.bin")
            src.write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "not divisible"):
                extract_audio_payloads(src, Path(temp) / "out.bin")


if __name__ == "__main__":
    unittest.main()
