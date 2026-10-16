"""Local-only SEQ/VH/VB transition auditor, synthetic fixture tests.

The CLI does not transmit or serialize any original music source bytes.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.generate_ps1_music_sd_fixture import make_synthetic_files

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = Path(os.environ.get("VH_LOCAL_MUSIC_TRANSITION_PROBE",
                              str(ROOT / "build" / "vh_local_music_transition_probe")))
TONE_OFFSET = 32 + 128 * 16


def synth_dir(directory, wet=False, bank_b=False):
    directory.mkdir()
    files = make_synthetic_files()
    vh = bytearray(files["music.vh"])
    vb = bytearray(files["music.vb"])
    if wet:
        vh[TONE_OFFSET + 1] = 4  # Valid VAB reverb-send mode.
    if bank_b:
        vb[18:32] = b"\x44" * 14
        vb[34:48] = b"\xDD" * 14
    files["music.vh"] = bytes(vh)
    files["music.vb"] = bytes(vb)
    for name, data in files.items():
        (directory / name).write_bytes(data)
    return files


@unittest.skipUnless(PROGRAM.is_file(), "build the native host tool first")
class NativeLocalMusicTransitionTests(unittest.TestCase):
    def test_private_banks_and_continuous_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "bank-a", Path(tmp) / "bank-b"
            originals_a = synth_dir(a, wet=True)
            originals_b = synth_dir(b, bank_b=True)
            cmd = [str(PROGRAM), str(a), str(b), "4", "16"]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertNotIn(str(tmp), first.stdout)
            self.assertNotIn(str(tmp), first.stderr)
            self.assertNotIn("pQES", first.stdout)
            self.assertNotIn("pBAV", first.stdout)
            result = json.loads(first.stdout)
            self.assertEqual(result["schema"], "vh_local_music_transition_v1")
            self.assertEqual(result["provenance"], "user-local")
            self.assertFalse(result["music_bytes_exported"])
            self.assertFalse(result["audible_audio_verified"])
            self.assertFalse(result["original_ps1_parity_verified"])
            self.assertEqual(result["sample_rate_hz"], 48000)
            self.assertEqual(result["scenes"], 4)
            self.assertEqual(result["input_frames"], 4 * 16 * 512)
            self.assertGreater(result["output_frames"], result["input_frames"])
            readings = result["measurements"]
            self.assertEqual([x["bank"] for x in readings], ["A", "B", "A", "B"])
            self.assertEqual([x["scene"] for x in readings], [0, 1, 2, 3])
            self.assertEqual([x["reverb_send_seen"] for x in readings],
                             [True, False, True, False])
            self.assertTrue(all(x["resolved_notes"] > 0 for x in readings))
            self.assertTrue(all(x["events"] >= x["resolved_notes"] for x in readings))
            self.assertEqual(sum(x["output_frames"] for x in readings),
                             result["output_frames"])
            self.assertTrue(all(x["input_frames"] == 8192 for x in readings))
            self.assertEqual(readings[0]["audout_boundary_delta_pcm16"], 0)
            self.assertTrue(all(x["spu_boundary_delta_pcm16"] >= 0
                                for x in readings))
            for folder, original in ((a, originals_a), (b, originals_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, original)

    def test_missing_bank_file_fails_without_partial_json_or_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            synth_dir(a)
            synth_dir(b)
            (b / "music.vb").unlink()
            result = subprocess.run(
                [str(PROGRAM), str(a), str(b)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertFalse(result.stdout)
            self.assertNotIn(str(tmp), result.stderr)
            self.assertIn("Invalid, incomplete", result.stderr)

    def test_invalid_numeric_options_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for tail in (("1",), ("33",), ("4", "0"), ("4", "4097"),
                         ("4", "abc")):
                result = subprocess.run(
                    [str(PROGRAM), str(a), str(b), *tail],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(result.stdout)


if __name__ == "__main__":
    unittest.main()
