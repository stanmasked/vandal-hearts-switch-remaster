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
    sector[24 + AUDIO_BYTES_PER_SECTOR:2328] = bytes(20)
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


if __name__ == "__main__":
    unittest.main()
