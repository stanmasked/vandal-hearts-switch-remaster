"""Tests for integrity checks on native PCM capture WAV files."""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("capture", Path(__file__).resolve().parents[1] / "tools/inspect_native_pcm_capture.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fake_capture(frames=71332):
    payload = b"\0\0\0\0" * frames
    header = (b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, 48000, 192000, 4, 16)
              + b"data" + struct.pack("<I", len(payload)))
    return header + payload


class NativeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "capture.wav"

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_capture(self):
        self.path.write_bytes(fake_capture())
        report = module.inspect(self.path)
        self.assertEqual(report["frames"], 71332)
        self.assertEqual(len(report["payload_sha256"]), 64)

    def test_truncated_payload(self):
        self.path.write_bytes(fake_capture()[:-4])
        with self.assertRaisesRegex(ValueError, "RIFF size"):
            module.inspect(self.path)

    def test_wrong_sample_rate(self):
        capture = bytearray(fake_capture())
        struct.pack_into("<I", capture, 24, 44100)
        self.path.write_bytes(capture)
        with self.assertRaisesRegex(ValueError, "transport format"):
            module.inspect(self.path)

    def test_wrong_frame_count(self):
        self.path.write_bytes(fake_capture(100))
        with self.assertRaisesRegex(ValueError, "frame count"):
            module.inspect(self.path)


if __name__ == "__main__":
    unittest.main()
