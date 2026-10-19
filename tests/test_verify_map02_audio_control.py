"""Synthetic, asset-free false-positive controls for two-NRO PCM audit."""
import array
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/verify_map02_audio_control.py"
spec = importlib.util.spec_from_file_location("map02_virtual_control", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class VirtualAudioNegativeControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.control_nro = self.root / "video.nro"
        self.audio_nro = self.root / "audio.nro"
        self.control_nro.write_bytes(b"NRO0 video baseline fixture")
        self.audio_nro.write_bytes(b"NRO0 native audout fixture")
        self.control_pcm = self.root / "video.pcm"
        self.audio_pcm = self.root / "audio.pcm"
        self.control_sinks = self.root / "audio-sink.txt"
        self.control_sinks.write_text('application.name = "ALSA plug-in [nexium]"',
                                      encoding="utf-8")
        self.manifest = self.root / "manifest.json"
        self.write_pcm(self.control_pcm, 0)
        self.write_pcm(self.audio_pcm, 1200)
        self.rebuild_manifest()

    @staticmethod
    def write_pcm(path, sample, seconds=2):
        values = array.array("h", [sample]) * (48000 * 2 * seconds)
        path.write_bytes(values.tobytes())

    def rebuild_manifest(self):
        self.manifest.write_text(json.dumps({
            "schema": "vh-map02-nro-pair/v1",
            "git_sha": "a" * 40,
            "run_id": 1234567,
            "run_attempt": 1,
            "control_nro_sha256": audit.sha256(self.control_nro.read_bytes()),
            "audio_nro_sha256": audit.sha256(self.audio_nro.read_bytes()),
        }), encoding="utf-8")

    def evaluate(self, seconds=1):
        return audit.evaluate(self.control_pcm, self.audio_pcm,
                              self.control_nro, self.audio_nro,
                              self.manifest, self.control_sinks,
                              min_seconds=seconds)

    def test_quiet_control_vs_audio_passes_without_claiming_original_music(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "CONTROLLED_VIRTUAL_AUDIO_CONTRAST")
        self.assertFalse(result["sample_aligned_comparison"])
        self.assertFalse(result["original_music_or_studio_c_causality_proven"])
        self.assertFalse(result["physical_switch_audio_tested"])

    def test_no_audio_fails(self):
        self.write_pcm(self.audio_pcm, 0)
        result = self.evaluate()
        self.assertEqual(result["status"], "VIRTUAL_AUDIO_CAUSAL_CONTROL_NOT_ESTABLISHED")
        self.assertFalse(result["checks"]["opt_in_nro_nonzero"])

    def test_loud_control_fails(self):
        self.write_pcm(self.control_pcm, 1400)
        result = self.evaluate()
        self.assertEqual(result["status"], "VIRTUAL_AUDIO_CAUSAL_CONTROL_NOT_ESTABLISHED")
        self.assertFalse(result["checks"]["video_only_control_quiet"])

    def test_guest_sink_absent_fails(self):
        self.control_sinks.write_text("No sink inputs", encoding="utf-8")
        result = self.evaluate()
        self.assertFalse(result["checks"]["experimental_guest_sink_observed"])
        self.assertEqual(result["status"], "VIRTUAL_AUDIO_CAUSAL_CONTROL_NOT_ESTABLISHED")

    def test_not_long_enough_fails(self):
        result = self.evaluate(seconds=3)
        self.assertFalse(result["checks"]["both_recordings_long_enough"])

    def test_audio_nro_hash_mismatch_fails_closed(self):
        self.audio_nro.write_bytes(b"tampered after manifest")
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.evaluate()

    def test_control_nro_hash_mismatch_fails_closed(self):
        self.control_nro.write_bytes(b"tampered control")
        with self.assertRaisesRegex(ValueError, "Control NRO"):
            self.evaluate()

    def test_identical_control_and_audio_nros_rejected(self):
        self.control_nro.write_bytes(self.audio_nro.read_bytes())
        self.rebuild_manifest()
        with self.assertRaisesRegex(ValueError, "identical"):
            self.evaluate()

    def test_partial_stereo_frame_rejected(self):
        self.audio_pcm.write_bytes(b"x" * 7)
        with self.assertRaisesRegex(ValueError, "misaligned"):
            self.evaluate()

    def test_empty_pcm_rejected(self):
        self.control_pcm.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "Missing or misaligned"):
            self.evaluate()

    def test_bad_manifest_run_id_rejected(self):
        d = json.loads(self.manifest.read_text(encoding="utf-8"))
        d["run_id"] = 0
        self.manifest.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "run ID"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
