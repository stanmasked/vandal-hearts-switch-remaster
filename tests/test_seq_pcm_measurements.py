"""Measure actual offline SEQ/VH/VB renderer PCM (generated bank only).

This tests the Python offline renderer at 44.1 kHz, NOT the native libnx
audout path or original PlayStation fidelity.
"""
import tempfile
import unittest
import wave
from pathlib import Path

from test_render_ps1_seq import seq_example
from test_seq_to_chord_schedule import synthetic_vab
from tools.render_ps1_seq import render_ps1_seq
from tools.analyze_pcm_wav import analyze


class SeqPcmMeasurements(unittest.TestCase):
    def test_decoded_renderer_output_measured_at_native_spu_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vh, vb = synthetic_vab()
            vh_path, vb_path = root / "synthetic.vh", root / "synthetic.vb"
            vh_path.write_bytes(vh)
            vb_path.write_bytes(vb)
            wav_data, render_report = render_ps1_seq(
                seq_example(), vh_path, vb_path,
                interpolation="nearest", release_frames=4,
            )
            wav_path = root / "rendered.wav"
            wav_path.write_bytes(wav_data)
            metrics = analyze(wav_path)
            self.assertEqual(metrics["sample_rate_hz"], 44100)
            self.assertEqual(metrics["channels"], 2)
            self.assertEqual(metrics["frames"], render_report["frames"])
            self.assertEqual(len(metrics["per_channel"]), 2)
            for channel in metrics["per_channel"]:
                self.assertGreaterEqual(channel["clipped_samples"], 0)
                self.assertGreaterEqual(channel["clipped_fraction"], 0)
                self.assertLessEqual(channel["clipped_fraction"], 1)
                self.assertLessEqual(abs(channel["dc_offset"]), 1)
            # Verify no source sample bank was rewritten by rendering.
            self.assertEqual(vh_path.read_bytes(), vh)
            self.assertEqual(vb_path.read_bytes(), vb)

    def test_analyzer_detects_real_renderer_frame_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vh, vb = synthetic_vab()
            (root / "a.vh").write_bytes(vh)
            (root / "a.vb").write_bytes(vb)
            rendered, _ = render_ps1_seq(
                seq_example(), root / "a.vh", root / "a.vb",
                interpolation="nearest", release_frames=4,
            )
            wav = root / "decoded.wav"
            wav.write_bytes(rendered)
            m = analyze(wav)
            self.assertAlmostEqual(m["duration_seconds"], 49 / 44100, places=6)


if __name__ == "__main__":
    unittest.main()
