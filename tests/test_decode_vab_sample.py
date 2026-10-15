"""Synthetic end-to-end VH/VB -> selected VAG -> PCM WAV regression."""
import hashlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.decode_vab_sample import decode_vab_sample


def make_bank():
    header = bytearray(32)
    header[:4] = b"pBAV"
    struct.pack_into("<HHHH", header, 16, 0, 2, 2, 3)
    programs = bytearray(128 * 16)
    programs[0] = 1
    programs[7 * 16] = 1
    tones = bytearray(2 * 16 * 32)
    for offset, parent, vag in ((0, 0, 1), (16 * 32, 7, 2)):
        tones[offset + 6] = 20
        tones[offset + 7] = 90
        struct.pack_into("<HHhh", tones, offset + 16, 0x1234, 0x5678,
                         parent, vag)
    sizes = [0] * 256
    # Entry zero is a 16-byte prefix, VAG 1 uses two blocks, VAG 2 one.
    sizes[:4] = [2, 4, 2, 0]
    vh = bytes(header + programs + tones + struct.pack("<256H", *sizes))
    # Each low nibble is -1 and each high nibble is +1 at shift 12.
    first = bytes([0x0c, 4] + [0x1f] * 14)
    second = bytes([0x0c, 3] + [0x1f] * 14)
    third = bytes([0x0c, 1] + [0x22] * 14)
    vb = bytes(16) + first + second + third + bytes(17)
    return vh, vb, first + second, third


class VabDecodeSampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vh = self.root / "bank.vh"
        self.vb = self.root / "bank.vb"
        self.wav = self.root / "output.wav"
        self.original_vh, self.original_vb, self.raw1, self.raw2 = make_bank()
        self.vh.write_bytes(self.original_vh)
        self.vb.write_bytes(self.original_vb)

    def test_two_samples_and_reference_metadata(self):
        one_wav, one = decode_vab_sample(self.vh, self.vb, vag=1, sample_rate=22050)
        self.assertEqual(one["adpcm_offset_in_vb"], 16)
        self.assertEqual(one["adpcm_size_bytes"], 32)
        self.assertEqual(one["adpcm_sha256"], hashlib.sha256(self.raw1).hexdigest())
        self.assertEqual(one["loop_start_frame"], 0)
        self.assertEqual(one["loop_end_frame"], 56)
        self.assertEqual(one["pcm_frames"], 56)
        self.assertEqual([(r["program"], r["tone"]) for r in one["referencing_tones"]],
                         [(0, 0)])
        with wave.open(io.BytesIO(one_wav), "rb") as audio:
            self.assertEqual((audio.getnchannels(), audio.getsampwidth(),
                              audio.getframerate(), audio.getnframes()),
                             (1, 2, 22050, 56))
            samples = struct.unpack("<56h", audio.readframes(56))
            self.assertEqual(samples, (-1, 1) * 28)

        two_wav, two = decode_vab_sample(self.vh, self.vb, vag=2, sample_rate=32000)
        self.assertEqual(two["adpcm_offset_in_vb"], 48)
        self.assertEqual(two["adpcm_size_bytes"], 16)
        self.assertEqual(two["adpcm_sha256"], hashlib.sha256(self.raw2).hexdigest())
        self.assertEqual([r["program"] for r in two["referencing_tones"]], [7])
        self.assertEqual(two["pcm_frames"], 28)
        with wave.open(io.BytesIO(two_wav), "rb") as audio:
            self.assertEqual(audio.getframerate(), 32000)
            self.assertEqual(struct.unpack("<28h", audio.readframes(28)), (2,) * 28)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_bad_selection_rate_and_unreferenced_empty_vag(self):
        for invalid in (-1, 0, 4, True):
            with self.subTest(vag=invalid):
                with self.assertRaises(ValueError):
                    decode_vab_sample(self.vh, self.vb, vag=invalid, sample_rate=22050)
        for invalid in (0, 192001, True, 22050.0):
            with self.subTest(rate=invalid):
                with self.assertRaises(ValueError):
                    decode_vab_sample(self.vh, self.vb, vag=1, sample_rate=invalid)
        with self.assertRaisesRegex(ValueError, "has no sample data"):
            decode_vab_sample(self.vh, self.vb, vag=3, sample_rate=22050)

    def test_rejects_corrupted_or_truncated_source(self):
        self.vb.write_bytes(self.original_vb[:47])
        with self.assertRaisesRegex(ValueError, "VB is truncated"):
            decode_vab_sample(self.vh, self.vb, vag=1, sample_rate=22050)
        self.vb.write_bytes(self.original_vb)
        damaged = bytearray(self.original_vb)
        damaged[16] = 0x5c  # invalid predictor 5 in selected first block
        self.vb.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "invalid predictor"):
            decode_vab_sample(self.vh, self.vb, vag=1, sample_rate=22050)
        self.assertEqual(self.vb.read_bytes(), damaged)
        self.vb.write_bytes(self.original_vb)
        self.vh.write_bytes(self.original_vh[:-1])
        with self.assertRaisesRegex(ValueError, "cannot verify VB"):
            decode_vab_sample(self.vh, self.vb, vag=1, sample_rate=22050)

    def test_command_writes_new_wav_and_wont_overwrite(self):
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "tools/decode_vab_sample.py"),
            str(self.vh), str(self.vb), str(self.wav),
            "--vag", "1", "--sample-rate", "22050",
        ]
        first = subprocess.run(command, text=True, capture_output=True, check=True)
        report = json.loads(first.stdout)
        self.assertEqual(report["pcm_frames"], 56)
        saved = self.wav.read_bytes()
        second = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.wav.read_bytes(), saved)
        # Refusing to make the VB or VH into an output is critical.
        for target in (self.vb, self.vh):
            rejected = subprocess.run(
                [*command[:4], str(target), *command[5:]],
                text=True, capture_output=True
            )
            self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)


if __name__ == "__main__":
    unittest.main()
