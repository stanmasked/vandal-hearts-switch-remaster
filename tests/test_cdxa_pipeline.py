"""End-to-end tests for extracting CD-XA sectors and decoding their audio payload."""
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.extract_cdxa_payload import SECTOR_SIZE, SYNC, extract_audio_payloads
from tools.decode_cdxa_adpcm import AUDIO_BYTES_PER_SECTOR, SAMPLE_RATE, decode_payload_file


def xa_audio_sector(payload_marker: int = 0) -> bytes:
    sector = bytearray([payload_marker] * SECTOR_SIZE)
    sector[:12] = SYNC
    sector[15] = 2  # Mode 2
    subheader = bytes((1, 0, 0x64, 0x01))  # file, channel, audio + Form 2, 4-bit stereo profile
    sector[16:20] = subheader
    sector[20:24] = subheader
    sector[24:24 + AUDIO_BYTES_PER_SECTOR] = bytes(AUDIO_BYTES_PER_SECTOR)
    return bytes(sector)


class CdXaPipelineTests(unittest.TestCase):
    def test_extracts_sector_payload_and_decodes_it_to_expected_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            output = root / "decoded.wav"
            source.write_bytes(xa_audio_sector())

            extraction = extract_audio_payloads(source, payload)
            self.assertEqual(extraction["audio_form2_sectors_written"], 1)
            self.assertEqual(extraction["coding_info_counts"], {"0x01": 1})
            self.assertEqual(extraction["audio_lbas"], [0])
            self.assertEqual(extraction["audio_lba_offsets"], [
                {"lba": 0, "payload_offset": 0, "missing_source_sectors_before": 0}
            ])
            self.assertEqual(payload.stat().st_size, AUDIO_BYTES_PER_SECTOR)

            decoded = decode_payload_file(payload, output, extracted_groups=True)
            self.assertEqual(decoded, {"sectors": 1, "groups": 18, "frames": 2016})
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), SAMPLE_RATE)
                self.assertEqual(wav.getnframes(), 2016)
                self.assertEqual(wav.readframes(2016), bytes(2016 * 4))

    def test_non_audio_sector_is_not_passed_to_decoder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            sector = bytearray(xa_audio_sector())
            sector[18] = 0x00  # Clear XA audio submode bit in the first subheader copy.
            sector[22] = 0x00  # Keep the duplicated subheader consistent.
            source.write_bytes(bytes(sector))

            report = extract_audio_payloads(source, payload)
            self.assertEqual(report["audio_form2_sectors_written"], 0)
            self.assertEqual(payload.read_bytes(), b"")


    def test_report_preserves_source_lba_gap_when_non_audio_sector_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            non_audio = bytearray(xa_audio_sector())
            non_audio[18] = 0x00
            non_audio[22] = 0x00
            source.write_bytes(xa_audio_sector() + bytes(non_audio) + xa_audio_sector())

            report = extract_audio_payloads(source, payload)
            self.assertEqual(report["audio_form2_sectors_written"], 2)
            self.assertEqual(report["noncontiguous_audio_transitions"], 1)
            self.assertEqual(report["audio_lbas"], [0, 2])
            self.assertEqual(report["audio_lba_offsets"], [
                {"lba": 0, "payload_offset": 0, "missing_source_sectors_before": 0},
                {
                    "lba": 2,
                    "payload_offset": AUDIO_BYTES_PER_SECTOR,
                    "missing_source_sectors_before": 1,
                },
            ])
            self.assertEqual(payload.stat().st_size, AUDIO_BYTES_PER_SECTOR * 2)


    def test_mismatched_duplicate_subheader_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            sector = bytearray(xa_audio_sector())
            sector[20] = 2  # Make the second subheader copy disagree with the first.
            source.write_bytes(bytes(sector))

            report = extract_audio_payloads(source, payload)
            self.assertEqual(report["mode2_sectors"], 1)
            self.assertEqual(report["matching_subheaders"], 0)
            self.assertEqual(report["audio_form2_sectors_written"], 0)
            self.assertEqual(report["payload_bytes_written"], 0)
            self.assertEqual(payload.read_bytes(), b"")


    def test_invalid_sync_and_non_mode2_sectors_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            bad_sync = bytearray(xa_audio_sector())
            bad_sync[0] = 1
            wrong_mode = bytearray(xa_audio_sector())
            wrong_mode[15] = 1
            source.write_bytes(bytes(bad_sync) + bytes(wrong_mode) + xa_audio_sector())

            report = extract_audio_payloads(source, payload)
            self.assertEqual(report["sectors_scanned"], 3)
            self.assertEqual(report["mode2_sectors"], 1)
            self.assertEqual(report["matching_subheaders"], 1)
            self.assertEqual(report["audio_form2_sectors_written"], 1)
            self.assertEqual(report["audio_lbas"], [2])
            self.assertEqual(payload.stat().st_size, AUDIO_BYTES_PER_SECTOR)


if __name__ == "__main__":
    unittest.main()
