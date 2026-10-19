"""Asset-free regressions for experimental WET_TAIL=0/1 guest PCM gating."""
import array
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools/audit_map02_nexium_wet_tail_ab.py"
spec = importlib.util.spec_from_file_location("wet_tail_guest_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class GuestWetTailAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sha = "a" * 40
        self.make_binary(0, b"LEGACY")
        self.make_binary(1, b"WET")
        self.make_manifest()
        for mode in (0, 1):
            self.make_audio(mode, 1024)
            (self.root / f"wet-tail-{mode}-sinks.txt").write_text(
                'application.name = "NeXium"\n', encoding="utf-8")
            (self.root / f"wet-tail-{mode}-scene.json").write_text(
                json.dumps({"screen_size": [1280, 720],
                            "status_blue_pixels": 85,
                            "selection_range_pixels": 3660,
                            "cancelled_range_pixels": 0}))

    def make_binary(self, mode, suffix):
        (self.root / f"map02-wet-tail-{mode}.nro").write_bytes(
            b"\0" * 16 + b"NRO0" + suffix)

    def make_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps({
            "schema": "vh-map02-wet-tail-pair/v1",
            "git_sha": self.sha, "run_id": 42, "run_attempt": 1,
            "legacy_sha256": mod.sha(
                (self.root / "map02-wet-tail-0.nro").read_bytes()),
            "wet_tail_sha256": mod.sha(
                (self.root / "map02-wet-tail-1.nro").read_bytes())}))

    def make_audio(self, mode, amplitude):
        pcm = array.array("h", [amplitude]) * (96000)
        (self.root / f"wet-tail-{mode}.pcm").write_bytes(pcm.tobytes())

    def verify(self):
        return mod.audit(self.root, 42, 1, self.sha, minimum_seconds=0.5)

    def test_valid_pair_checks_guest_not_causality(self):
        result = self.verify()
        self.assertEqual(result["result"], "TWO_MODES_GUEST_AUDIO_AND_SCENE_INPUT_OBSERVED")
        self.assertFalse(result["sample_aligned"])
        self.assertFalse(result["reverb_tail_causally_proven_by_guest_pcm"])
        self.assertFalse(result["physical_switch_audio_tested"])

    def test_quiet_mode_does_not_pass(self):
        self.make_audio(1, 0)
        self.assertEqual(self.verify()["result"], "WET_TAIL_GUEST_AB_UNVERIFIED")

    def test_missing_sink_does_not_pass(self):
        (self.root / "wet-tail-0-sinks.txt").write_text("No sink inputs")
        self.assertFalse(self.verify()["checks"]["both_guest_sink_inputs_observed"])

    def test_missing_selection_does_not_pass(self):
        file = self.root / "wet-tail-1-scene.json"
        scene = json.loads(file.read_text())
        scene["selection_range_pixels"] = 0
        file.write_text(json.dumps(scene))
        self.assertFalse(self.verify()["checks"]["both_guest_scene_inputs_observed"])

    def test_cancel_highlight_not_removed_does_not_pass(self):
        file = self.root / "wet-tail-0-scene.json"
        scene = json.loads(file.read_text())
        scene["cancelled_range_pixels"] = 3500
        file.write_text(json.dumps(scene))
        self.assertFalse(self.verify()["checks"]["both_guest_scene_inputs_observed"])

    def test_binary_hash_tampering_fails_closed(self):
        self.make_binary(1, b"TAMPER")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.verify()

    def test_wrong_run_or_attempt_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "run/attempt"):
            mod.audit(self.root, 43, 1, self.sha, 0.5)
        with self.assertRaisesRegex(ValueError, "run/attempt"):
            mod.audit(self.root, 42, 2, self.sha, 0.5)

    def test_truncated_stereo_frame_fails_closed(self):
        (self.root / "wet-tail-1.pcm").write_bytes(b"xyz")
        with self.assertRaisesRegex(ValueError, "partial"):
            self.verify()

    def test_duration_gate_fails_closed(self):
        self.assertEqual(mod.audit(self.root, 42, 1, self.sha, 2)["result"],
                         "WET_TAIL_GUEST_AB_UNVERIFIED")

if __name__ == "__main__":
    unittest.main()
