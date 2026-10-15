"""Tests for the non-destructive CD-XA payload extractor."""
import sys
import tempfile
import unittest
from unittest import mock
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
            bad_sync = bytearray(sector(marker=0x66))
            bad_sync[0] = 0x01
            src.write_bytes(sector(marker=0x11) + sector(submode=0x00, marker=0x22) +
                            sector(duplicate=False, marker=0x33) + sector(mode=1, marker=0x44) +
                            bytes(bad_sync))
            report = extract_audio_payloads(src, dst, report_path=report_path)
            self.assertEqual(dst.read_bytes(), bytes([0x11]) * 2304)
            self.assertEqual(report["audio_form2_sectors_written"], 1)
            self.assertEqual(report["payload_bytes_written"], 2304)
            self.assertTrue(report_path.is_file())

    def test_report_preserves_source_lbas_and_payload_offsets_across_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst = root / "disc.bin", root / "payload.bin"
            src.write_bytes(sector(marker=0x10) + sector(submode=0x00, marker=0x20) +
                            sector(marker=0x30) + sector(mode=1, marker=0x40) +
                            sector(marker=0x50))
            report = extract_audio_payloads(src, dst)
            self.assertEqual(report["audio_lbas"], [0, 2, 4])
            self.assertEqual(report["audio_lba_offsets"], [
                {"lba": 0, "payload_offset": 0, "missing_source_sectors_before": 0},
                {"lba": 2, "payload_offset": 2304, "missing_source_sectors_before": 1},
                {"lba": 4, "payload_offset": 4608, "missing_source_sectors_before": 1},
            ])
            self.assertEqual(report["noncontiguous_audio_transitions"], 2)

    def test_filters_by_channel_and_file_number(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst = root / "disc.bin", root / "payload.bin"
            src.write_bytes(sector(channel=0, file_no=1, marker=0x10) +
                            sector(channel=1, file_no=1, marker=0x20) +
                            sector(channel=0, file_no=2, marker=0x30))
            extract_audio_payloads(src, dst, channel=1, file_number=1)
            self.assertEqual(dst.read_bytes(), bytes([0x20]) * 2304)

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

    def test_start_lba_and_sector_count_report_absolute_disc_positions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst = root / "disc.bin", root / "payload.bin"
            src.write_bytes(
                sector(marker=0x10) + sector(marker=0x20) +
                sector(marker=0x30) + sector(marker=0x40)
            )
            report = extract_audio_payloads(src, dst, start_lba=1, sector_count=2)
            self.assertEqual(report["start_lba"], 1)
            self.assertEqual(report["sectors_scanned"], 2)
            self.assertEqual(report["audio_lbas"], [1, 2])
            self.assertEqual(report["first_audio_lba"], 1)
            self.assertEqual(report["last_audio_lba"], 2)
            self.assertEqual(dst.read_bytes(), bytes([0x20]) * 2304 + bytes([0x30]) * 2304)

    def test_rejects_empty_and_unaligned_input(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "disc.bin"
            src.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                extract_audio_payloads(src, Path(temp) / "out.bin")
            src.write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "not divisible"):
                extract_audio_payloads(src, Path(temp) / "out.bin")


    def test_failed_report_staging_does_not_publish_partial_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst = root / "disc.bin", root / "payload.bin"
            src.write_bytes(sector(marker=0x31))
            dst.write_bytes(b"keep previous payload")
            blocker = root / "not-a-directory"
            blocker.write_text("file blocks report directory", encoding="utf-8")
            report_path = blocker / "report.json"

            with self.assertRaises(OSError):
                extract_audio_payloads(src, dst, report_path=report_path)

            self.assertEqual(dst.read_bytes(), b"keep previous payload")
            self.assertEqual(list(root.glob(".payload.bin.*.tmp")), [])
            self.assertEqual(list(root.glob(".report.json.*.tmp")), [])



    def test_report_directory_does_not_replace_existing_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst = root / "disc.bin", root / "payload.bin"
            src.write_bytes(sector(marker=0x42))
            dst.write_bytes(b"previous complete payload")
            report_directory = root / "report.json"
            report_directory.mkdir()

            with self.assertRaises(IsADirectoryError):
                extract_audio_payloads(src, dst, report_path=report_directory)

            self.assertEqual(dst.read_bytes(), b"previous complete payload")
            self.assertTrue(report_directory.is_dir())
            self.assertEqual(list(root.glob(".payload.bin.*.tmp")), [])
            self.assertEqual(list(root.glob(".report.json.*.tmp")), [])


    def test_report_replace_failure_restores_previous_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst, report = root / "disc.bin", root / "payload.bin", root / "report.json"
            src.write_bytes(sector(marker=0x77))
            dst.write_bytes(b"previous payload")
            report.write_text("previous report", encoding="utf-8")
            from tools import extract_cdxa_payload as extractor
            real_replace = extractor.os.replace

            def fail_report_publish(source, target):
                if Path(target) == report:
                    raise OSError("injected report publish failure")
                return real_replace(source, target)

            with mock.patch.object(extractor.os, "replace", side_effect=fail_report_publish):
                with self.assertRaisesRegex(OSError, "injected report"):
                    extract_audio_payloads(src, dst, report_path=report)

            self.assertEqual(dst.read_bytes(), b"previous payload")
            self.assertEqual(report.read_text(encoding="utf-8"), "previous report")
            self.assertEqual(list(root.glob("*.tmp")), [])
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_report_replace_failure_removes_new_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst, report = root / "disc.bin", root / "payload.bin", root / "report.json"
            src.write_bytes(sector(marker=0x77))
            from tools import extract_cdxa_payload as extractor
            real_replace = extractor.os.replace

            def fail_report_publish(source, target):
                if Path(target) == report:
                    raise OSError("injected report publish failure")
                return real_replace(source, target)

            with mock.patch.object(extractor.os, "replace", side_effect=fail_report_publish):
                with self.assertRaisesRegex(OSError, "injected report"):
                    extract_audio_payloads(src, dst, report_path=report)

            self.assertFalse(dst.exists())
            self.assertFalse(report.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])


    def test_failed_rollback_preserves_old_payload_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dst, report = root / "disc.bin", root / "payload.bin", root / "report.json"
            src.write_bytes(sector(marker=0x72))
            dst.write_bytes(b"original payload protected")
            report.write_text("previous report", encoding="utf-8")
            from tools import extract_cdxa_payload as extractor
            real_replace = extractor.os.replace

            def fail_report_and_rollback(source, target):
                if Path(target) == report:
                    raise OSError("injected report publication failure")
                if Path(target) == dst and Path(source).name.startswith(".payload.bin."):
                    # First payload publication succeeds, but restoring backup fails.
                    if dst.read_bytes() == bytes([0x72]) * 2304:
                        raise OSError("injected rollback failure")
                return real_replace(source, target)

            with mock.patch.object(extractor.os, "replace", side_effect=fail_report_and_rollback):
                with self.assertRaisesRegex(OSError, "Previous payload preserved at"):
                    extract_audio_payloads(src, dst, report_path=report)

            backups = list(root.glob(".payload.bin.*.tmp"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"original payload protected")
            self.assertEqual(report.read_text(encoding="utf-8"), "previous report")
            self.assertEqual(list(root.glob(".report.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
