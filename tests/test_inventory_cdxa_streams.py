"""Synthetic raw-disc tests for read-only CD-XA stream inventory."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inventory_cdxa_streams import inventory_streams
from tools.extract_cdxa_payload import extract_audio_payloads
from tools.validate_cdxa_extraction import validate_extraction
from tools.run_cdxa_local_check import run_local_check


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

    def test_inventory_candidates_match_extraction_and_local_decode(self):
        # Nonzero scan window with two interleaved compatible streams.
        # Stream (2, 1) has audio LBAs 2, 4, 6 and a non-audio
        # same-channel sector at LBA 5 which must not be extracted.
        self.source.write_bytes(b"".join([
            sector(99, 99, submode=0x00),
            sector(5, 0),
            sector(2, 1),
            sector(5, 0),
            sector(2, 1),
            sector(2, 1, submode=0x00),
            sector(2, 1, submode=0xE4),
            sector(5, 0),
            sector(valid=False),
        ]))
        start_lba, count = 1, 7
        scanned = inventory_streams(self.source, start_lba=start_lba,
                                    sector_count=count)
        expected_lbas = {(2, 1): [2, 4, 6], (5, 0): [1, 3, 7]}
        self.assertEqual(scanned["audio_sectors"], 6)
        self.assertEqual(len(scanned["streams"]), 2)
        self.assertEqual(sum(item["audio_sectors"] for item in scanned["streams"]), 6)
        for item in scanned["streams"]:
            key = item["file_number"], item["channel"]
            with self.subTest(stream=key):
                output = self.root / f"payload-{key[0]}-{key[1]}.bin"
                report_path = self.root / f"report-{key[0]}-{key[1]}.json"
                report = extract_audio_payloads(
                    self.source, output, start_lba=start_lba,
                    sector_count=count, file_number=key[0],
                    channel=key[1], report_path=report_path,
                )
                self.assertEqual(report["audio_lbas"], expected_lbas[key])
                self.assertEqual(report["audio_form2_sectors_written"],
                                 item["audio_sectors"])
                self.assertEqual(report["first_audio_lba"], item["first_lba"])
                self.assertEqual(report["last_audio_lba"], item["last_lba"])
                verified = validate_extraction(report_path, output,
                                               source_bin=self.source)
                self.assertEqual(verified["audio_sectors"], item["audio_sectors"])
                result_dir = self.root / f"decoded-{key[0]}-{key[1]}"
                result = run_local_check(
                    self.source, result_dir, start_lba=start_lba,
                    sector_count=count, file_number=key[0],
                    channel=key[1],
                )
                self.assertEqual(result["status"], "decoded_and_source_verified")
                self.assertEqual(result["selected_lbas"], expected_lbas[key])
                self.assertEqual(result["pcm_frames"], item["audio_sectors"] * 2016)
                self.assertEqual(
                    json.loads((result_dir / "extraction.json").read_text())[
                        "audio_lbas"], expected_lbas[key],
                )

    def test_inventory_flags_unsupported_stream_before_decoding(self):
        self.source.write_bytes(sector(2, 1, coding=0x01)
                                + sector(2, 1, coding=0x00))
        found = inventory_streams(self.source)
        self.assertEqual(found["unsupported_coding_sectors"], 1)
        self.assertEqual(found["streams"][0]["coding_counts"],
                         {"0x00": 1, "0x01": 1})
        payload = self.root / "mixed.bin"
        report = self.root / "mixed.json"
        extract_audio_payloads(self.source, payload, file_number=2,
                               channel=1, report_path=report)
        with self.assertRaisesRegex(ValueError, "unsupported or mixed XA coding"):
            validate_extraction(report, payload, source_bin=self.source)

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
