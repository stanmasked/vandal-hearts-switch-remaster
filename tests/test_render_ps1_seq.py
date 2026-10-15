"""End-to-end PS1 SEQ + synthetic VH/VB -> stereo WAV regression."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.render_ps1_seq import render_ps1_seq
from test_seq_to_chord_schedule import hdr, synthetic_vab


def seq_example():
    return (hdr()
            + bytes([0, 0xC0, 7,
                     0, 0xB0, 0x0A, 0,
                     0, 0x90, 60, 110,
                     1, 0x80, 60, 0,
                     0, 0xFF, 0x2F]))


class RenderSeqTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.folder = Path(root.name)
        self.seq = self.folder / "local.seq"
        self.vh = self.folder / "local.vh"
        self.vb = self.folder / "local.vb"
        self.wav = self.folder / "note.wav"
        self.source = seq_example()
        self.original_vh, self.original_vb = synthetic_vab()
        self.seq.write_bytes(self.source)
        self.vh.write_bytes(self.original_vh)
        self.vb.write_bytes(self.original_vb)

    def test_render_directly_without_intermediate_json(self):
        wav, report = render_ps1_seq(
            self.source, self.vh, self.vb,
            interpolation="nearest", release_frames=4
        )
        self.assertEqual(report["seq_ppqn"], 480)
        self.assertEqual(report["seq_end_frame"], 45)
        self.assertEqual(report["frames"], 49)
        self.assertEqual(report["seq_events"], 5)
        self.assertEqual(report["voices"][0]["program"] if
                         "program" in report["voices"][0] else
                         report["voices"][0]["requested_program"], 7)
        self.assertEqual(report["voices"][0]["vag"], 2)
        self.assertEqual(report["channels"], 2)
        with wave.open(io.BytesIO(wav), "rb") as stream:
            self.assertEqual(
                (stream.getnchannels(), stream.getframerate(),
                 stream.getnframes()), (2, 44100, 49)
            )
            first = stream.readframes(1)
            self.assertEqual(len(first), 4)
        self.assertEqual(self.seq.read_bytes(), self.source)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_direct_cli_exclusive_output_and_source_protection(self):
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "tools/render_ps1_seq.py"),
            str(self.seq), str(self.vh), str(self.vb), str(self.wav),
            "--release-frames", "4", "--interpolation", "nearest",
        ]
        first = subprocess.run(command, capture_output=True, text=True, check=True)
        result = json.loads(first.stdout)
        self.assertEqual((result["frames"], result["channels"]), (49, 2))
        saved = self.wav.read_bytes()
        again = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(self.wav.read_bytes(), saved)
        for source in (self.seq, self.vh, self.vb):
            args = list(command)
            args[5] = str(source)
            rejected = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.seq.read_bytes(), self.source)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_invalid_seq_before_output_creation(self):
        with self.assertRaisesRegex(ValueError, "pQES"):
            render_ps1_seq(b"not a song" + bytes(50),
                           self.vh, self.vb, release_frames=4)
        with self.assertRaisesRegex(ValueError, "release_frames"):
            render_ps1_seq(self.source, self.vh, self.vb, release_frames=True)
        self.assertFalse(self.wav.exists())


if __name__ == "__main__":
    unittest.main()
