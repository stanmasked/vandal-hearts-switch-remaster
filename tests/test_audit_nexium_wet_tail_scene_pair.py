"""Negative controls for the source-bound legacy/opt-in scene comparison."""
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import analyze_nexium_scene_audio as scene
from audit_nexium_wet_tail_scene_pair import audit, PairEvidenceError

SHA = "0123456789abcdef0123456789abcdef01234567"
H0 = "a" * 64
H1 = "b" * 64


def generate(folder, phase=0.0, focus=106):
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    pcm = bytearray()
    for index, (label, hz) in enumerate(zip(
            scene.EXPECTED, (61, focus, 61, focus, 61))):
        rows.append((label, len(pcm), 1000 + index * 7000))
        for frame in range(6200):
            value = int(1100 * math.sin(
                2 * math.pi * hz * frame / 1000 + phase))
            pcm.extend(struct.pack("<hh", value, round(value * 0.85)))
    (folder / "nexium-scenes-s16le-48k.pcm").write_bytes(pcm)
    with (folder / "scene-events.csv").open("w", newline="", encoding="ascii") as f:
        out = csv.writer(f)
        out.writerow(("scene", "pcm_bytes", "epoch_ms"))
        out.writerows(rows)
    report = scene.analyze(folder / "nexium-scenes-s16le-48k.pcm",
                           folder / "scene-events.csv")
    (folder / "scene-audio-report.json").write_text(
        json.dumps(report) + "\n", encoding="utf-8")
    return report


class ScenePairAuditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(scene, "RATE", 1000)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.legacy = generate(self.root / "runtime-evidence", 0.0)
        self.experimental = generate(
            self.root / "runtime-evidence" / "wet-tail-scenes", 0.37)
        self.prov = self.root / "pair.json"
        self.provenance = {
            "result": "SAME_RUN_WET_TAIL_NRO_PAIR_VERIFIED",
            "git_sha": SHA, "run_id": 42, "run_attempt": 1,
            "legacy_sha256": H0, "wet_tail_sha256": H1,
        }
        self.write(self.prov, self.provenance)
        self.witness_file = (self.root / "runtime-evidence"
                             / "wet-tail-scenes" / "opt-in-scene-witness.json")
        self.witness = {
            "schema": "vh-nexium-opt-in-scene-pcm/v1",
            "result": "SAME_RUN_OPT_IN_VIRTUAL_PCM_SCENES_OBSERVED",
            "git_sha": SHA, "run_id": 42,
            "wet_tail_nro_sha256": H1,
            "scene_pcm_sha256": self.experimental["pcm_sha256"],
            "music_label_changed_pixels": [47, 47, 47, 47],
            "hardware_status": "HARDWARE NOT TESTED",
            "speaker_audio_not_verified": True,
            "host_timing_not_guest_sample_accurate": True,
            "wet_tail_effect_causality_not_proven": True,
        }
        self.write(self.witness_file, self.witness)

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    def check(self):
        return audit(self.root / "runtime-evidence", self.prov)

    def test_valid_two_independent_buffered_captures(self):
        result = self.check()
        self.assertEqual(len(result["per_scene_descriptive_observations"]), 5)
        self.assertEqual(result["opt_in_pcm_sha256"],
                         self.experimental["pcm_sha256"])
        self.assertFalse(result["sample_aligned_A_B_comparison"])
        self.assertFalse(result["reverb_effect_causally_proven"])
        self.assertFalse(result["audible_audio_confirmed"])

    def test_wrong_committed_nro_digest_rejected(self):
        self.witness["wet_tail_nro_sha256"] = H0
        self.write(self.witness_file, self.witness)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_false_sample_accuracy_flag_rejected(self):
        self.witness["host_timing_not_guest_sample_accurate"] = False
        self.write(self.witness_file, self.witness)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_wrong_run_rejected(self):
        self.witness["run_id"] = 43
        self.write(self.witness_file, self.witness)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_copied_pcm_without_updated_report_rejected(self):
        path = self.root / "runtime-evidence" / "wet-tail-scenes" / "nexium-scenes-s16le-48k.pcm"
        data = path.read_bytes()
        path.write_bytes(data[:-4] + b"\0\0\0\0")
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_forged_report_rejected(self):
        path = self.root / "runtime-evidence" / "scene-audio-report.json"
        wrong = dict(self.legacy, pcm_sha256="0" * 64)
        self.write(path, wrong)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_identical_scene_music_rejected(self):
        wet_dir = self.root / "runtime-evidence" / "wet-tail-scenes"
        with patch.object(scene, "RATE", 1000):
            report = generate(wet_dir, 0.0, focus=61)
        self.witness["scene_pcm_sha256"] = report["pcm_sha256"]
        self.write(self.witness_file, self.witness)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_wrong_screenshot_label_pixels_rejected(self):
        self.witness["music_label_changed_pixels"] = [47, 0, 47, 47]
        self.write(self.witness_file, self.witness)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_symlink_experimental_root_rejected(self):
        wet_dir = self.root / "runtime-evidence" / "wet-tail-scenes"
        other = self.root / "moved"
        wet_dir.rename(other)
        wet_dir.symlink_to(other, target_is_directory=True)
        with self.assertRaises(PairEvidenceError):
            self.check()

    def test_identical_nro_pair_provenance_rejected(self):
        self.provenance["wet_tail_sha256"] = H0
        self.write(self.prov, self.provenance)
        with self.assertRaises(PairEvidenceError):
            self.check()


if __name__ == "__main__":
    unittest.main()
