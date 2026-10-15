"""Read-only validation tests for XA extraction report and payload."""
import hashlib
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.validate_cdxa_extraction import validate_extraction


class ValidateXaExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.report = root / "report.json"
        self.payload = root / "audio.bin"
        self.data = {
            "audio_form2_sectors_written": 2,
            "payload_bytes_written": 4608,
            "payload_sha256": hashlib.sha256(bytes(4608)).hexdigest(),
            "coding_info_counts": {"0x01": 2},
            "file_channel_counts": {"1:0": 2},
            "audio_lbas": [10, 12],
            "audio_lba_offsets": [
                {"lba": 10, "payload_offset": 0, "missing_source_sectors_before": 0},
                {"lba": 12, "payload_offset": 2304, "missing_source_sectors_before": 1},
            ],
            "noncontiguous_audio_transitions": 1,
        }
        self.payload.write_bytes(bytes(4608))

    def check(self):
        self.report.write_text(json.dumps(self.data), encoding="utf-8")
        return validate_extraction(self.report, self.payload)

    def test_valid_sample_reports_frames_duration_and_gap(self):
        result = self.check()
        self.assertEqual(result["pcm_frames"], 4032)
        self.assertEqual(result["audio_sectors"], 2)
        self.assertEqual(result["lba_gap_transitions"], 1)
        self.assertAlmostEqual(result["decoded_seconds"], 4032 / 37800)

    def test_payload_size_mismatch_fails(self):
        self.payload.write_bytes(bytes(2304))
        with self.assertRaisesRegex(ValueError, "payload size mismatch"):
            self.check()

    def test_payload_same_size_but_wrong_contents_fails(self):
        self.payload.write_bytes(bytes([1]) * 4608)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.check()

    def test_missing_digest_fails(self):
        del self.data["payload_sha256"]
        with self.assertRaisesRegex(ValueError, "SHA-256 payload digest"):
            self.check()

    def test_mixed_profiles_fail(self):
        self.data["coding_info_counts"] = {"0x01": 1, "0x05": 1}
        with self.assertRaisesRegex(ValueError, "unsupported or mixed"):
            self.check()

    def test_incorrect_coding_count_fails(self):
        self.data["coding_info_counts"] = {"0x01": 1}
        with self.assertRaisesRegex(ValueError, "coding-info sector count"):
            self.check()

    def test_mixed_file_channels_rejected(self):
        self.data["file_channel_counts"] = {"1:0": 1, "1:1": 1}
        with self.assertRaisesRegex(ValueError, "multiple CD-XA"):
            self.check()

    def test_incorrect_stream_count_rejected(self):
        self.data["file_channel_counts"] = {"1:0": 1}
        with self.assertRaisesRegex(ValueError, "file/channel count metadata"):
            self.check()

    def test_missing_stream_counts_rejected(self):
        del self.data["file_channel_counts"]
        with self.assertRaisesRegex(ValueError, "file/channel counts"):
            self.check()

    def test_source_lba_range_metadata_accepted(self):
        self.data.update({
            "start_lba": 10, "sectors_scanned": 3,
            "first_audio_lba": 10, "last_audio_lba": 12,
        })
        self.assertEqual(self.check()["audio_sectors"], 2)

    def test_out_of_range_audio_lba_rejected(self):
        self.data.update({
            "start_lba": 11, "sectors_scanned": 2,
            "first_audio_lba": 10, "last_audio_lba": 12,
        })
        with self.assertRaisesRegex(ValueError, "outside reported scanned range"):
            self.check()

    def test_inconsistent_first_or_last_lba_rejected(self):
        self.data.update({
            "start_lba": 10, "sectors_scanned": 3,
            "first_audio_lba": 11, "last_audio_lba": 12,
        })
        with self.assertRaisesRegex(ValueError, "first/last audio LBA"):
            self.check()

    def test_incomplete_source_range_rejected(self):
        self.data["start_lba"] = 10
        with self.assertRaisesRegex(ValueError, "incomplete source LBA"):
            self.check()

    def test_source_range_must_fit_selected_sector_count(self):
        self.data.update({
            "start_lba": 10, "sectors_scanned": 1,
            "first_audio_lba": 10, "last_audio_lba": 12,
        })
        with self.assertRaisesRegex(ValueError, "outside reported scanned range"):
            self.check()

    def test_read_only_source_bin_matches_exact_selected_stream(self):
        # Construct two selected XA sectors, separated by a different channel.
        # Source bytes must equal the report's local payload, not just its hash.
        root = self.report.parent
        raw_path = root / "source.bin"

        def sector(channel, fill):
            data = bytearray(2352)
            data[:12] = bytes([0]) + bytes([255]) * 10 + bytes([0])
            data[15] = 2
            data[16:20] = data[20:24] = bytes((1, channel, 0x64, 0x01))
            data[24:2328] = bytes([fill]) * 2304
            return bytes(data)

        self.data.update({
            "start_lba": 0, "sectors_scanned": 3,
            "first_audio_lba": 0, "last_audio_lba": 2,
            "audio_lbas": [0, 2],
            "audio_lba_offsets": [
                {"lba": 0, "payload_offset": 0, "missing_source_sectors_before": 0},
                {"lba": 2, "payload_offset": 2304, "missing_source_sectors_before": 1},
            ],
        })
        raw_path.write_bytes(sector(0, 17) + sector(1, 55) + sector(0, 33))
        payload = bytes([17]) * 2304 + bytes([33]) * 2304
        self.payload.write_bytes(payload)
        self.data["payload_sha256"] = hashlib.sha256(payload).hexdigest()
        self.report.write_text(json.dumps(self.data), encoding="utf-8")
        original = raw_path.read_bytes()
        self.assertEqual(
            validate_extraction(self.report, self.payload, source_bin=raw_path)["audio_sectors"], 2
        )
        self.assertEqual(raw_path.read_bytes(), original)

        changed = bytearray(original)
        changed[24] ^= 1
        raw_path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "source BIN payload mismatch"):
            validate_extraction(self.report, self.payload, source_bin=raw_path)

        # Hidden eligible sector in a previously interleaved channel slot.
        raw_path.write_bytes(sector(0, 17) + sector(0, 55) + sector(0, 33))
        with self.assertRaisesRegex(ValueError, "selection differs"):
            validate_extraction(self.report, self.payload, source_bin=raw_path)

        raw_path.write_bytes(original[:-1])
        with self.assertRaisesRegex(ValueError, "not aligned"):
            validate_extraction(self.report, self.payload, source_bin=raw_path)

    def test_source_bin_needs_full_scan_range(self):
        raw = self.report.parent / "source.bin"
        raw.write_bytes(bytes(2352))
        self.report.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "requires scan-range metadata"):
            validate_extraction(self.report, self.payload, source_bin=raw)

    def test_invalid_offsets_fail(self):
        self.data["audio_lba_offsets"][1]["payload_offset"] = 2305
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.check()

    def test_boolean_and_fractional_offset_metadata_rejected(self):
        # In Python False == 0 and True == 1: report fields must use
        # genuine JSON integers, not values that compare equal to them.
        mutations = (
            (0, "payload_offset", False),
            (0, "missing_source_sectors_before", False),
            (1, "missing_source_sectors_before", True),
            (1, "payload_offset", 2304.0),
            (0, "lba", 10.0),
        )
        for index, field, replacement in mutations:
            with self.subTest(index=index, field=field, replacement=replacement):
                original = self.data["audio_lba_offsets"][index][field]
                self.data["audio_lba_offsets"][index][field] = replacement
                try:
                    with self.assertRaisesRegex(ValueError, "LBA/offset mapping"):
                        self.check()
                finally:
                    self.data["audio_lba_offsets"][index][field] = original

    def test_misreported_gaps_fail(self):
        self.data["noncontiguous_audio_transitions"] = 0
        with self.assertRaisesRegex(ValueError, "gaps"):
            self.check()

    def test_nonascending_lbas_fail(self):
        self.data["audio_lbas"] = [10, 10]
        with self.assertRaisesRegex(ValueError, "nonascending"):
            self.check()

    def test_empty_extraction_rejected(self):
        self.data.update({
            "audio_form2_sectors_written": 0,
            "payload_bytes_written": 0,
            "coding_info_counts": {},
            "audio_lbas": [],
            "audio_lba_offsets": [],
            "noncontiguous_audio_transitions": 0,
        })
        self.payload.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "no audio sectors"):
            self.check()


    def write_wav(self, path, frames=4032, rate=37800, channels=2):
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames * channels * 2))

    def test_matching_wav_is_accepted(self):
        self.check()
        wav = self.report.parent / "decoded.wav"
        self.write_wav(wav)
        result = validate_extraction(self.report, self.payload, wav)
        self.assertEqual(result["pcm_frames"], 4032)

    def test_wav_wrong_frame_count_rejected(self):
        self.check()
        wav = self.report.parent / "decoded.wav"
        self.write_wav(wav, frames=2016)
        with self.assertRaisesRegex(ValueError, "frame count"):
            validate_extraction(self.report, self.payload, wav)

    def test_wav_wrong_sample_rate_rejected(self):
        self.check()
        wav = self.report.parent / "decoded.wav"
        self.write_wav(wav, rate=44100)
        with self.assertRaisesRegex(ValueError, "37800"):
            validate_extraction(self.report, self.payload, wav)

    def test_wav_truncated_data_rejected(self):
        self.check()
        wav = self.report.parent / "decoded.wav"
        self.write_wav(wav)
        with wav.open("r+b") as stream:
            stream.truncate(wav.stat().st_size - 20)
        with self.assertRaisesRegex(ValueError, "truncated"):
            validate_extraction(self.report, self.payload, wav)


if __name__ == "__main__":
    unittest.main()
