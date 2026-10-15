"""Synthetic-only SPU-ADPCM tests: exact PCM, history, loop metadata, WAV."""
import io
import random
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.decode_spu_adpcm import decode_spu_blocks, wav_bytes


def block(predictor=0, shift=12, flags=0, nibble_bytes=None):
    if nibble_bytes is None:
        nibble_bytes = bytes(14)
    return bytes([(predictor << 4) | shift, flags]) + nibble_bytes


def independent_scalar(raw):
    """Separate index-based reference, modelling signed 16-bit expansion."""
    positive = [0, 60, 115, 98, 122]
    negative = [0, 0, -52, -55, -60]
    first = second = 0
    pcm = []
    for start in range(0, len(raw), 16):
        hdr = raw[start]
        predictor, shift = hdr // 16, hdr % 16
        for sample_index in range(28):
            coded_byte = raw[start + 2 + sample_index // 2]
            nibble = (coded_byte // (16 if sample_index % 2 else 1)) % 16
            expanded = nibble * 4096
            if expanded >= 32768:
                expanded -= 65536
            predicted = (first * positive[predictor]
                         + second * negative[predictor] + 32) // 64
            value = (expanded // (2 ** shift)) + predicted
            value = min(32767, max(-32768, value))
            second, first = first, value
            pcm.append(value)
    return pcm


class SpuDecodeTests(unittest.TestCase):
    def test_signed_nibbles_and_order_without_prediction(self):
        decoded = decode_spu_blocks(block(0, 12, 0, bytes([0x1f] * 14)))
        self.assertEqual(decoded.frames, 28)
        self.assertEqual(list(struct.unpack("<28h", decoded.pcm)), [-1, 1] * 14)
        self.assertIsNone(decoded.loop_start_frame)
        self.assertIsNone(decoded.loop_end_frame)

    def test_all_predictors_clipping_and_state_across_blocks(self):
        random_generator = random.Random(919)
        blocks = []
        for predictor in (0, 1, 2, 3, 4, 3, 2, 1):
            blocks.append(block(predictor, 1, 0, bytes(
                random_generator.randrange(256) for _ in range(14))))
        data = b"".join(blocks)
        decoded = decode_spu_blocks(data)
        actual = list(struct.unpack("<" + "h" * decoded.frames, decoded.pcm))
        self.assertEqual(actual, independent_scalar(data))
        self.assertTrue(any(x == 32767 or x == -32768 for x in actual))
        self.assertEqual(decoded.frames, 28 * len(blocks))

    def test_loop_start_end_and_trailing_blocks(self):
        data = (block(flags=0) + block(flags=4)
                + block(flags=3) + block(flags=0))
        decoded = decode_spu_blocks(data)
        self.assertEqual((decoded.loop_start_frame, decoded.loop_end_frame),
                         (28, 84))
        self.assertEqual(decoded.first_end_block, 2)
        self.assertEqual(decoded.frames, 112)
        # The source C decoder starts a repeating sample at zero if no
        # explicit loop start was encountered.
        no_start = decode_spu_blocks(block(flags=3))
        self.assertEqual((no_start.loop_start_frame, no_start.loop_end_frame),
                         (0, 28))
        end_only = decode_spu_blocks(block(flags=1))
        self.assertIsNone(end_only.loop_end_frame)

    def test_strict_header_rejection(self):
        cases = (
            b"", bytes(15), block(predictor=5),
            block(shift=13), block(flags=0x80),
        )
        for payload in cases:
            with self.subTest(payload=payload[:2]):
                with self.assertRaises(ValueError):
                    decode_spu_blocks(payload)

    def test_mono_wav_requires_rate_and_has_exact_frames(self):
        decoded = decode_spu_blocks(block(0, 12, 0, bytes([0x10] * 14)))
        wav = wav_bytes(decoded, 22050)
        with wave.open(io.BytesIO(wav), "rb") as stream:
            self.assertEqual((stream.getnchannels(), stream.getsampwidth(),
                              stream.getframerate(), stream.getnframes()),
                             (1, 2, 22050, 28))
            self.assertEqual(stream.readframes(28), decoded.pcm)
        for invalid in (0, 192001, True, 22050.0):
            with self.assertRaises(ValueError):
                wav_bytes(decoded, invalid)

    def test_input_does_not_change(self):
        data = block(1, 3, flags=1, nibble_bytes=bytes([0x28] * 14))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.adpcm"
            path.write_bytes(data)
            decoded = decode_spu_blocks(path.read_bytes())
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(decoded.block_count, 1)


if __name__ == "__main__":
    unittest.main()
