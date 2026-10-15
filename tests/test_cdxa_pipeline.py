"""End-to-end tests for extracting CD-XA sectors and decoding their audio payload."""
import hashlib
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.extract_cdxa_payload import SECTOR_SIZE, SYNC, extract_audio_payloads
from tools.decode_cdxa_adpcm import AUDIO_BYTES_PER_SECTOR, SAMPLE_RATE, decode_payload_file
from tools.validate_cdxa_extraction import validate_extraction
from tools.compare_cdxa_wavs import compare_wavs


def xa_audio_sector(payload_marker: int = 0) -> bytes:
    sector = bytearray([payload_marker] * SECTOR_SIZE)
    sector[:12] = SYNC
    sector[15] = 2  # Mode 2
    subheader = bytes((1, 0, 0x64, 0x01))  # file, channel, audio + Form 2, 4-bit stereo at 37.8 kHz
    sector[16:20] = subheader
    sector[20:24] = subheader
    sector[24:24 + AUDIO_BYTES_PER_SECTOR] = bytes([payload_marker]) * AUDIO_BYTES_PER_SECTOR
    return bytes(sector)


def set_xa_file_channel(sector: bytes, file_number: int, channel: int) -> bytes:
    updated = bytearray(sector)
    subheader = bytes((file_number, channel, 0x64, 0x01))
    updated[16:20] = subheader
    updated[20:24] = subheader
    return bytes(updated)


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
            self.assertEqual(extraction["file_channel_counts"], {"1:0": 1})
            self.assertEqual(extraction["audio_lbas"], [0])
            self.assertEqual(extraction["audio_lba_offsets"], [
                {"lba": 0, "payload_offset": 0, "missing_source_sectors_before": 0}
            ])
            self.assertEqual(payload.stat().st_size, AUDIO_BYTES_PER_SECTOR)
            self.assertEqual(extraction["payload_sha256"], hashlib.sha256(payload.read_bytes()).hexdigest())

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
            # The pipeline must fail clearly rather than create a silent WAV
            # when extraction found no eligible audio sectors.
            with self.assertRaisesRegex(ValueError, "empty"):
                decode_payload_file(payload, root / "decoded.wav", extracted_groups=True)

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

    def test_file_and_channel_filters_select_only_matching_audio_sector(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            first = set_xa_file_channel(xa_audio_sector(0x11), file_number=7, channel=0)
            selected = set_xa_file_channel(xa_audio_sector(0x22), file_number=7, channel=1)
            other_channel = set_xa_file_channel(xa_audio_sector(0x33), file_number=7, channel=2)
            other_file = set_xa_file_channel(xa_audio_sector(0x44), file_number=8, channel=1)
            source.write_bytes(first + selected + other_channel + other_file)

            report = extract_audio_payloads(
                source, payload, channel=1, file_number=7
            )
            self.assertEqual(report["sectors_scanned"], 4)
            self.assertEqual(report["audio_form2_sectors_written"], 1)
            self.assertEqual(report["audio_lbas"], [1])
            self.assertEqual(report["file_channel_counts"], {"7:1": 1})
            self.assertEqual(report["first_audio_lba"], 1)
            self.assertEqual(report["last_audio_lba"], 1)
            self.assertEqual(payload.read_bytes(), selected[24:24 + AUDIO_BYTES_PER_SECTOR])


    def test_lba_range_uses_absolute_source_sector_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            payload = root / "audio-payload.bin"
            source.write_bytes(
                xa_audio_sector(0x10)
                + xa_audio_sector(0x20)
                + xa_audio_sector(0x30)
                + xa_audio_sector(0x40)
            )

            report = extract_audio_payloads(
                source, payload, start_lba=1, sector_count=2
            )
            self.assertEqual(report["start_lba"], 1)
            self.assertEqual(report["sectors_scanned"], 2)
            self.assertEqual(report["audio_lbas"], [1, 2])
            self.assertEqual(
                payload.read_bytes(),
                source.read_bytes()[SECTOR_SIZE + 24:SECTOR_SIZE + 24 + AUDIO_BYTES_PER_SECTOR]
                + source.read_bytes()[2 * SECTOR_SIZE + 24:2 * SECTOR_SIZE + 24 + AUDIO_BYTES_PER_SECTOR],
            )

    def test_invalid_lba_ranges_fail_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            source.write_bytes(xa_audio_sector() * 2)

            invalid_ranges = (
                {"start_lba": -1},
                {"start_lba": 2},
                {"start_lba": 0, "sector_count": 0},
                {"start_lba": 1, "sector_count": 2},
            )
            for index, kwargs in enumerate(invalid_ranges):
                with self.subTest(kwargs=kwargs):
                    payload = root / f"invalid-{index}.bin"
                    with self.assertRaises(ValueError):
                        extract_audio_payloads(source, payload, **kwargs)
                    self.assertFalse(payload.exists())
            self.assertEqual(source.stat().st_size, SECTOR_SIZE * 2)


    def test_extractor_refuses_source_and_report_path_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            source.write_bytes(xa_audio_sector())
            payload = root / "audio-payload.bin"
            report = root / "report.json"

            with self.assertRaisesRegex(ValueError, "overwrite the source"):
                extract_audio_payloads(source, source)
            self.assertEqual(source.stat().st_size, SECTOR_SIZE)

            with self.assertRaisesRegex(ValueError, "Report path"):
                extract_audio_payloads(source, payload, report_path=source)
            self.assertFalse(payload.exists())

            with self.assertRaisesRegex(ValueError, "Report path"):
                extract_audio_payloads(source, payload, report_path=payload)
            self.assertFalse(payload.exists())



    def test_extractor_refuses_symlink_alias_of_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            source.write_bytes(xa_audio_sector())
            alias = root / "source-alias.bin"
            try:
                alias.symlink_to(source)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "overwrite the source"):
                extract_audio_payloads(source, alias)
            self.assertEqual(source.stat().st_size, SECTOR_SIZE)
            self.assertEqual(alias.resolve(), source.resolve())


    def test_extractor_refuses_hard_link_aliases_of_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-disc.bin"
            original = xa_audio_sector()
            source.write_bytes(original)
            alias = root / "source-hardlink.bin"
            try:
                alias.hardlink_to(source)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"hard-link creation unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "overwrite the source"):
                extract_audio_payloads(source, alias)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(alias.read_bytes(), original)

            payload = root / "audio-payload.bin"
            with self.assertRaisesRegex(ValueError, "Report path"):
                extract_audio_payloads(source, payload, report_path=alias)
            self.assertFalse(payload.exists())
            self.assertEqual(source.read_bytes(), original)


    def test_interleaved_channels_must_be_isolated_before_decoding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "interleaved-disc.bin"
            mixed_payload = root / "mixed.bin"
            mixed_report = root / "mixed.json"
            isolated_payload = root / "isolated.bin"
            isolated_report = root / "isolated.json"
            wav_path = root / "isolated.wav"

            # Synthetic silent XA sound groups; channels alternate by sector.
            source.write_bytes(
                set_xa_file_channel(xa_audio_sector(), 1, 0)
                + set_xa_file_channel(xa_audio_sector(), 1, 1)
                + set_xa_file_channel(xa_audio_sector(), 1, 0)
                + set_xa_file_channel(xa_audio_sector(), 1, 1)
            )

            mixed = extract_audio_payloads(
                source, mixed_payload, report_path=mixed_report
            )
            self.assertEqual(mixed["file_channel_counts"], {"1:0": 2, "1:1": 2})
            with self.assertRaisesRegex(ValueError, "multiple CD-XA"):
                validate_extraction(mixed_report, mixed_payload)
            self.assertFalse(wav_path.exists())

            isolated = extract_audio_payloads(
                source, isolated_payload, file_number=1, channel=0,
                report_path=isolated_report
            )
            self.assertEqual(isolated["audio_lbas"], [0, 2])
            self.assertEqual(isolated["file_channel_counts"], {"1:0": 2})
            self.assertEqual(validate_extraction(isolated_report, isolated_payload)["pcm_frames"], 4032)
            decoded = decode_payload_file(isolated_payload, wav_path, extracted_groups=True)
            self.assertEqual(decoded["frames"], 4032)
            self.assertEqual(
                validate_extraction(isolated_report, isolated_payload, wav_path)["pcm_frames"],
                4032,
            )
            with wave.open(str(wav_path), "rb") as wav:
                self.assertEqual(wav.readframes(4032), bytes(4032 * 4))


    def test_end_to_end_nonzero_pcm_matches_independent_expected_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            disc = root / "synthetic.bin"
            compressed = root / "groups.bin"
            report_path = root / "groups.json"
            decoded_path = root / "decoded.wav"
            reference_path = root / "expected.wav"

            # Filter 0, low shift nibble 12: signed ADPCM nibbles map
            # directly to signed PCM integers. The reference below is made
            # without running the ADPCM decoder or using its output.
            raw = bytearray(xa_audio_sector())
            expected_frames = []
            for group_index in range(18):
                group_start = 24 + group_index * 128
                raw[group_start:group_start + 16] = bytes([0x0C]) * 16
                for row in range(28):
                    for chunk in range(4):
                        left = (row + group_index + chunk) % 16
                        right = (row * 3 + group_index + chunk) % 16
                        raw[group_start + 16 + row * 4 + chunk] = left | (right << 4)
                for chunk in range(4):
                    for row in range(28):
                        left = (row + group_index + chunk) % 16
                        right = (row * 3 + group_index + chunk) % 16
                        expected_frames.append((
                            left - 16 if left >= 8 else left,
                            right - 16 if right >= 8 else right,
                        ))
            self.assertEqual(len(expected_frames), 2016)
            disc.write_bytes(bytes(raw))
            extracted = extract_audio_payloads(disc, compressed, report_path=report_path)
            self.assertEqual(extracted["audio_form2_sectors_written"], 1)
            self.assertEqual(validate_extraction(report_path, compressed)["pcm_frames"], 2016)
            decoded = decode_payload_file(compressed, decoded_path, extracted_groups=True)
            self.assertEqual(decoded["frames"], 2016)
            with wave.open(str(reference_path), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(b"".join(struct.pack("<hh", left, right)
                                         for left, right in expected_frames))

            self.assertEqual(
                validate_extraction(report_path, compressed, decoded_path)["pcm_frames"],
                2016,
            )
            comparison = compare_wavs(decoded_path, reference_path)
            self.assertTrue(comparison["exact_match"])
            self.assertEqual(comparison["different_channel_samples"], 0)
            self.assertEqual(comparison["frames_compared"], 2016)


    def test_predictive_adpcm_state_survives_sector_boundary(self):
        # Construct two 2352-byte XA sectors using 4-bit stereo filter 1.
        # The reference recurrence below does not call the decoder and
        # retains each channel's predictor state across all 36 groups.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            disc, payload, report_path = (
                root / "disc.bin", root / "payload.bin", root / "report.json"
            )
            decoded_path, reference_path = root / "actual.wav", root / "reference.wav"
            frames_expected = []
            history = [[0, 0], [0, 0]]
            raw_sectors = []
            for sector_index in range(2):
                sector = bytearray(xa_audio_sector())
                for group_index in range(18):
                    base = 24 + group_index * 128
                    sector[base:base + 16] = bytes([0x1C]) * 16
                    for row in range(28):
                        for chunk in range(4):
                            left_code = (row + chunk + sector_index + group_index) % 16
                            right_code = (3 * row + chunk + sector_index + group_index) % 16
                            sector[base + 16 + row * 4 + chunk] = (
                                left_code | (right_code << 4)
                            )
                    samples = [[], []]
                    for chunk in range(4):
                        for channel in (0, 1):
                            prev, older = history[channel]
                            for row in range(28):
                                code = (
                                    (row + chunk + sector_index + group_index) % 16
                                    if channel == 0 else
                                    (3 * row + chunk + sector_index + group_index) % 16
                                )
                                signed = code if code < 8 else code - 16
                                value = signed + ((60 * prev + 32) // 64)
                                older, prev = prev, value
                                samples[channel].append(max(-32768, min(32767, value)))
                            history[channel] = [prev, older]
                    frames_expected.extend(zip(*samples))
                raw_sectors.append(bytes(sector))
            disc.write_bytes(b"".join(raw_sectors))
            result = extract_audio_payloads(
                disc, payload, report_path=report_path
            )
            self.assertEqual(result["audio_lbas"], [0, 1])
            self.assertEqual(result["file_channel_counts"], {"1:0": 2})
            self.assertEqual(validate_extraction(report_path, payload)["pcm_frames"], 4032)
            self.assertEqual(
                decode_payload_file(payload, decoded_path, extracted_groups=True)["frames"],
                4032,
            )
            with wave.open(str(reference_path), "wb") as ref:
                ref.setnchannels(2)
                ref.setsampwidth(2)
                ref.setframerate(SAMPLE_RATE)
                ref.writeframes(b"".join(
                    struct.pack("<hh", left, right)
                    for left, right in frames_expected
                ))
            self.assertEqual(len(frames_expected), 4032)
            comparison = compare_wavs(decoded_path, reference_path)
            self.assertTrue(comparison["exact_match"], comparison)
            self.assertEqual(comparison["frames_compared"], 4032)


    def test_two_tap_predictive_filters_across_sector_boundary(self):
        # Filter 2 (115,-52) and filter 3 (98,-55) use two prior
        # samples. This independent scalar oracle maintains each channel's
        # history across all groups, both sectors, and filter changes.
        coeffs = {2: (115, -52), 3: (98, -55)}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            disc = root / "disc.bin"
            payload = root / "xa.bin"
            report_path = root / "xa.json"
            decoded = root / "decoded.wav"
            reference = root / "expected.wav"
            history = [[0, 0], [0, 0]]
            expected_frames = []
            sectors = []
            for sector_index in range(2):
                sector = bytearray(xa_audio_sector())
                for group_index in range(18):
                    start = 24 + group_index * 128
                    params = []
                    for chunk in range(4):
                        for channel in range(2):
                            predictor = 2 + ((group_index + sector_index + chunk + channel) % 2)
                            params.append((predictor << 4) | 12)
                    sector[start:start + 4] = bytes(params[:4])
                    sector[start + 4:start + 8] = bytes(params[:4])
                    sector[start + 8:start + 12] = bytes(params[4:])
                    sector[start + 12:start + 16] = bytes(params[4:])
                    for row in range(28):
                        for chunk in range(4):
                            low = (row * 5 + chunk + group_index + sector_index) % 16
                            high = (row * 3 + chunk * 2 + group_index + sector_index) % 16
                            sector[start + 16 + row * 4 + chunk] = low | (high << 4)

                    channel_samples = [[], []]
                    for chunk in range(4):
                        for channel in range(2):
                            coefficient0, coefficient1 = coeffs[params[chunk * 2 + channel] >> 4]
                            h1, h2 = history[channel]
                            for row in range(28):
                                packed = sector[start + 16 + row * 4 + chunk]
                                nibble = (packed >> (channel * 4)) & 15
                                signed = nibble if nibble < 8 else nibble - 16
                                predicted = (coefficient0 * h1 + coefficient1 * h2 + 32) // 64
                                value = signed + predicted
                                channel_samples[channel].append(max(-32768, min(32767, value)))
                                h2, h1 = h1, value
                            history[channel] = [h1, h2]
                    expected_frames.extend(zip(*channel_samples))
                sectors.append(bytes(sector))

            disc.write_bytes(b"".join(sectors))
            extract_audio_payloads(disc, payload, report_path=report_path)
            self.assertEqual(validate_extraction(report_path, payload)["pcm_frames"], 4032)
            self.assertEqual(
                decode_payload_file(payload, decoded, extracted_groups=True)["frames"], 4032
            )
            with wave.open(str(reference), "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(SAMPLE_RATE)
                output.writeframes(b"".join(
                    struct.pack("<hh", left, right)
                    for left, right in expected_frames
                ))
            self.assertEqual(len(expected_frames), 4032)
            self.assertEqual(
                validate_extraction(report_path, payload, decoded)["pcm_frames"], 4032
            )
            comparison = compare_wavs(decoded, reference)
            self.assertTrue(comparison["exact_match"], comparison)


    def test_partial_lba_range_and_interleaved_channels_verify_against_source(self):
        # The report has absolute LBAs even when extraction starts in the
        # middle of the disc. Only the requested (file, channel) is selected.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "disc.bin"
            output = root / "payload.bin"
            report_path = root / "report.json"
            target_a = set_xa_file_channel(xa_audio_sector(), 2, 1)
            other = set_xa_file_channel(xa_audio_sector(), 2, 0)
            target_b = set_xa_file_channel(xa_audio_sector(), 2, 1)
            source.write_bytes(
                set_xa_file_channel(xa_audio_sector(), 7, 7)
                + set_xa_file_channel(xa_audio_sector(), 8, 8)
                + target_a + other + target_b
                + set_xa_file_channel(xa_audio_sector(), 2, 1)
            )
            report = extract_audio_payloads(
                source, output, start_lba=2, sector_count=3,
                file_number=2, channel=1, report_path=report_path,
            )
            self.assertEqual(report["start_lba"], 2)
            self.assertEqual(report["sectors_scanned"], 3)
            self.assertEqual(report["audio_lbas"], [2, 4])
            self.assertEqual(report["file_channel_counts"], {"2:1": 2})
            self.assertEqual(report["noncontiguous_audio_transitions"], 1)
            self.assertEqual(
                validate_extraction(report_path, output, source_bin=source)["audio_sectors"], 2
            )
            # The target sector just *outside* the scanned range must not be
            # treated as omitted by source verification.
            self.assertEqual(output.read_bytes(), bytes(AUDIO_BYTES_PER_SECTOR * 2))
            # Re-pointing the metadata at a different range must not pass.
            import json
            altered_report = json.loads(report_path.read_text(encoding="utf-8"))
            altered_report["start_lba"] = 1
            altered_report["sectors_scanned"] = 4
            report_path.write_text(json.dumps(altered_report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sector/header counts"):
                validate_extraction(report_path, output, source_bin=source)


if __name__ == "__main__":
    unittest.main()
