"""Unit tests for the experimental CD-XA ADPCM decoder."""
import struct
import sys
import tempfile
import wave
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.decode_cdxa_adpcm import (
    AUDIO_BYTES_PER_SECTOR, GROUP_SIZE, SECTOR_PAYLOAD, decode_group,
    decode_payload_file,
)


class DecodeCdXaAdpcmTests(unittest.TestCase):
    def test_silent_group_decodes_to_112_stereo_frames(self):
        group = bytes(GROUP_SIZE)
        pcm = decode_group(group, [[0, 0], [0, 0]])
        self.assertEqual(len(pcm), 112 * 2 * 2)
        self.assertEqual(pcm, bytes(len(pcm)))

    def test_decodes_low_nibble_left_and_high_nibble_right(self):
        group = bytearray(GROUP_SIZE)
        # Filter 0, shift 0 (parameter low nibble 12); duplicate parameters.
        group[:16] = bytes([0x0C]) * 16
        for row in range(28):
            for chunk in range(4):
                group[16 + row * 4 + chunk] = 0x21
        pcm = decode_group(bytes(group), [[0, 0], [0, 0]])
        self.assertEqual(len(pcm), 112 * 2 * 2)
        samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
        self.assertEqual(samples, (1, 2) * 112)

    def test_applies_reference_predictor_filter(self):
        group = bytearray(GROUP_SIZE)
        # Filter 1 has coefficients (60, 0); shift is zero at low nibble 12.
        group[:16] = bytes([0x1C]) * 16
        group[16:] = bytes([0x11]) * (GROUP_SIZE - 16)
        pcm = decode_group(bytes(group), [[0, 0], [0, 0]])
        samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
        # For each channel, the first chunk starts 1, 2, 3, 4, ...
        self.assertEqual(samples[0:8:2], (1, 2, 3, 4))
        self.assertEqual(samples[1:8:2], (1, 2, 3, 4))

    def test_keeps_unclipped_predictor_history_but_clips_pcm(self):
        group = bytearray(GROUP_SIZE)
        # Filter 2 can drive the internal predictor outside signed 16-bit range.
        group[:16] = bytes([0x2C]) * 16
        group[16:] = bytes([0x77]) * (GROUP_SIZE - 16)
        history = [[32767, -32768], [0, 0]]
        pcm = decode_group(bytes(group), history)
        samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
        self.assertEqual(samples[0], 32767)
        self.assertIn(32767, samples)
        # Independently compute the final left-channel predictor state without
        # clipping feedback. The first samples clip in PCM, but history must
        # retain the unbounded predictor values throughout the group.
        h1, h2 = 32767, -32768
        for _ in range(112):
            sample = 7 + ((115 * h1 - 52 * h2 + 32) >> 6)
            h2, h1 = h1, sample
        self.assertEqual(history[0], [h1, h2])


    def test_mixed_filter_reference_vector_across_two_groups(self):
        # An independent scalar oracle: build samples in playback order from
        # nibble values, without calling the production decode_group routine.
        # Distinct left/right filters and negative values exercise predictors,
        # nibble signs, group boundaries, and history carry-over.
        coeff = ((0, 0), (60, 0), (115, -52), (98, -55))
        history = [[0, 0], [0, 0]]
        production_history = [[0, 0], [0, 0]]
        expected = bytearray()
        for group_index in range(2):
            group = bytearray(GROUP_SIZE)
            params = (
                (0x1B, 0x2C, 0x3B, 0x0C, 0x2B, 0x1C, 0x3C, 0x0B)
                if group_index == 0 else
                (0x2A, 0x3C, 0x1C, 0x0B, 0x3A, 0x2C, 0x1B, 0x0C)
            )
            # Four chunks * two channels = eight parameters. Each four-byte
            # half has a separate duplicate within the XA header.
            group[0:4] = bytes(params[:4])
            group[4:8] = bytes(params[:4])
            group[8:12] = bytes(params[4:])
            group[12:16] = bytes(params[4:])
            for row in range(28):
                for chunk in range(4):
                    low = (row + chunk + group_index * 3) & 15
                    high = (15 - row + chunk * 3 + group_index) & 15
                    group[16 + row * 4 + chunk] = (high << 4) | low

            reference_channels = [[], []]
            for chunk in range(4):
                for channel in range(2):
                    p = params[chunk * 2 + channel]
                    factor = 1 << (12 - (p & 15))
                    k0, k1 = coeff[p >> 4]
                    old1, old2 = history[channel]
                    for row in range(28):
                        byte = group[16 + row * 4 + chunk]
                        code = (byte & 15) if channel == 0 else (byte >> 4)
                        if code >= 8:
                            code -= 16
                        predicted = (old1 * k0 + old2 * k1 + 32) // 64
                        value = code * factor + predicted
                        reference_channels[channel].append(min(32767, max(-32768, value)))
                        old2, old1 = old1, value
                    history[channel] = [old1, old2]
            for left, right in zip(*reference_channels):
                expected.extend(struct.pack("<hh", left, right))
            self.assertEqual(
                decode_group(bytes(group), production_history),
                bytes(expected[-112 * 4:]),
            )
            self.assertEqual(production_history, history)

    def test_vgmstream_style_reference_subframes_and_history(self):
        # Independent algorithmic cross-check of the vgmstream xa_decoder.c
        # channel-first, subframe-first traversal. Unlike decode_group, this
        # oracle sign-extends the high four bits of a signed 16-bit word.
        # https://github.com/vgmstream/vgmstream/blob/master/src/coding/xa_decoder.c
        gain0 = (0, 60, 115, 98)
        gain1 = (0, 0, -52, -55)
        reference_history = [[0, 0], [0, 0]]
        decoder_history = [[0, 0], [0, 0]]
        for group_number in range(3):
            frame = bytearray(GROUP_SIZE)
            params = bytes(
                ((group_number * 3 + subframe) % 4) * 16
                + ((group_number + subframe * 2) % 13)
                for subframe in range(8)
            )
            frame[0:4] = frame[4:8] = params[0:4]
            frame[8:12] = frame[12:16] = params[4:8]
            for row in range(28):
                for column in range(4):
                    lo = (row * 7 + column + group_number) % 16
                    hi = (row * 3 + column * 5 + group_number * 2) % 16
                    frame[16 + 4 * row + column] = lo | (hi << 4)

            expected_channels = [[], []]
            for channel in (0, 1):
                h1, h2 = reference_history[channel]
                for subframe in range(4):
                    param = frame[4 + 2 * subframe + channel]
                    filt, shift = param >> 4, param & 15
                    for row in range(28):
                        packed = frame[16 + 4 * row + subframe]
                        nib = (packed >> (channel * 4)) & 15
                        # C reference: (int16_t)((nib << 12) & 0xf000) >> shift
                        signed = struct.unpack("<h", (nib << 12).to_bytes(2, "little"))[0]
                        sample = signed >> shift
                        sample += (gain0[filt] * h1 + gain1[filt] * h2 + 32) >> 6
                        h2, h1 = h1, sample
                        expected_channels[channel].append(max(-32768, min(32767, sample)))
                reference_history[channel] = [h1, h2]

            expected = b"".join(
                struct.pack("<hh", left, right)
                for left, right in zip(*expected_channels)
            )
            actual = decode_group(bytes(frame), decoder_history)
            self.assertEqual(actual, expected)
            self.assertEqual(decoder_history, reference_history)

    def test_rejects_bad_group_length_and_parameter_copy(self):
        with self.assertRaisesRegex(ValueError, "exactly 128"):
            decode_group(bytes(127), [[0, 0], [0, 0]])
        bad = bytearray(GROUP_SIZE)
        bad[4] = 1
        with self.assertRaisesRegex(ValueError, "copies do not match"):
            decode_group(bytes(bad), [[0, 0], [0, 0]])

    def test_rejects_unsupported_filter_and_shift_parameters(self):
        for parameter, message in ((0x4C, "invalid XA filter"), (0x0D, "invalid XA shift")):
            with self.subTest(parameter=hex(parameter)):
                group = bytearray(GROUP_SIZE)
                group[:16] = bytes([parameter]) * 16
                with self.assertRaisesRegex(ValueError, message):
                    decode_group(bytes(group), [[0, 0], [0, 0]])

    def test_writes_wav_with_expected_format_and_frame_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "payload.bin", root / "out.wav"
            # One sector: 18 silent groups plus the 20-byte padding area.
            source.write_bytes(bytes(AUDIO_BYTES_PER_SECTOR) + bytes(SECTOR_PAYLOAD - AUDIO_BYTES_PER_SECTOR))
            report = decode_payload_file(source, output)
            self.assertEqual(report, {"sectors": 1, "groups": 18, "frames": 2016})
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 37800)
                self.assertEqual(wav.getnframes(), 2016)
                self.assertEqual(wav.readframes(2016), bytes(2016 * 4))

    def test_decodes_extracted_2304_byte_sound_group_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "extracted.bin", root / "out.wav"
            source.write_bytes(bytes(AUDIO_BYTES_PER_SECTOR))
            report = decode_payload_file(source, output, extracted_groups=True)
            self.assertEqual(report, {"sectors": 1, "groups": 18, "frames": 2016})
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnframes(), 2016)
                self.assertEqual(wav.readframes(2016), bytes(2016 * 4))

    def test_rejects_bad_size_nonzero_padding_and_in_place_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "payload.bin", root / "out.wav"
            source.write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "divisible"):
                decode_payload_file(source, output)
            source.write_bytes(bytes(AUDIO_BYTES_PER_SECTOR) + bytes([1]) + bytes(19))
            with self.assertRaisesRegex(ValueError, "non-zero padding"):
                decode_payload_file(source, output)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                decode_payload_file(source, source)


    def test_refuses_hard_link_alias_as_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "payload.bin"
            original = bytes(AUDIO_BYTES_PER_SECTOR)
            source.write_bytes(original)
            alias = root / "payload-hardlink.bin"
            try:
                alias.hardlink_to(source)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"hard-link creation unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "overwrite the input payload"):
                decode_payload_file(source, alias, extracted_groups=True)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(alias.read_bytes(), original)


    def test_decode_failure_does_not_publish_partial_wav_or_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "payload.bin"
            output = root / "out.wav"
            malformed = bytearray(AUDIO_BYTES_PER_SECTOR)
            malformed[GROUP_SIZE + 4] = 1  # Break the duplicate parameter copies in group 2.
            source.write_bytes(bytes(malformed))
            output.write_bytes(b"preserve existing output")

            with self.assertRaisesRegex(ValueError, "copies do not match"):
                decode_payload_file(source, output, extracted_groups=True)
            self.assertEqual(output.read_bytes(), b"preserve existing output")
            self.assertEqual(list(root.glob(".out.wav.*.tmp")), [])

            output.unlink()
            with self.assertRaisesRegex(ValueError, "copies do not match"):
                decode_payload_file(source, output, extracted_groups=True)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".out.wav.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
