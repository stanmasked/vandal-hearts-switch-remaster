"""Generated-data tests for offline Stage263; no game ROM or licensed audio."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_map02_cpal_alsa_boundary import (
    SOURCE, RUN, audit, raw_monitor
)
from classify_map02_guest_evidence import classify
from decode_map02_prejoin_stage import crc8_atm, decode_image


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def guest_image(stage, entered, returned):
    data = [0xa5, 0x5a, stage, entered & 255, entered >> 8,
            returned & 255, returned >> 8, 1]
    parity = 0
    for byte in data:
        parity ^= byte
    data += [parity, crc8_atm(data)]
    img = Image.new("RGB", (1280, 720))
    draw = ImageDraw.Draw(img)
    draw.rectangle((244, 154, 335, 265), fill=(255, 0, 255))
    draw.rectangle((246, 156, 333, 263), fill=(0, 0, 0))
    for row, value in enumerate(data):
        for bit in range(8):
            x, y = 250 + 10 * bit, 160 + 10 * row
            draw.rectangle((x, y, x + 7, y + 7),
                           fill=(255, 255, 255) if value & (1 << bit)
                           else (0, 0, 0))
    return img


def make_fixture(root):
    binary = b"\0" * 16 + b"NRO0" + b"\1" * 128
    digest = hashlib.sha256(binary).hexdigest()
    nro = root / "map02-audout-presubmit-research-nro"
    nro.mkdir()
    (nro / "vandal-hearts-map02-audio.nro").write_bytes(binary)
    (nro / "nro.sha256").write_text(digest + "  file.nro\n")
    common = {"schema": "vh-map02-presubmit-guest-nro/v1",
              "source_sha": SOURCE, "run_id": RUN, "attempt": 1,
              "nro_sha256": digest}
    save_json(nro / "manifest.json", common)

    for ms in (21, 22):
        for repeat in (1, 2, 3):
            d = root / f"map02-presubmit-nexium-guest-proof-{ms}-r{repeat}"
            d.mkdir()
            save_json(d / "manifest.json", common)
            save_json(d / "pulse-client-trial.json", {
                "schema": "vh-map02-pulse-client-latency-trial/v1",
                "source_sha": SOURCE, "run_id": RUN, "attempt": 1,
                "nro_sha256": digest,
                "variant": str(ms), "independent_repeat": repeat
            })
            succeeded = ms == 22
            png = d / "presubmit-guest-prejoin-stage.png"
            guest_image(6 if succeeded else 3,
                        123 if succeeded else 1,
                        123 if succeeded else 0).save(png)
            stage = decode_image(png)
            save_json(d / "presubmit-guest-prejoin-stage.json", stage)
            pcm = struct.pack("<hh", 7 if succeeded else 0, 0)
            audio = d / "presubmit-virtual-sink-s16le-48k.pcm"
            audio.write_bytes(pcm)
            observed = raw_monitor(audio)
            monitor = {
                "schema": "vh-map02-latency-monitor-health/v1",
                "valid_pcm16le_stereo": True,
                "raw_pcm_sha256": observed["sha256"],
                "raw_bytes": observed["bytes"],
                "stereo_frames": observed["frames"],
                "nonzero_pcm16_samples": observed["nonzero_samples"],
                "all_zero_monitor_pcm": not bool(observed["nonzero_samples"])
            }
            save_json(d / "presubmit-monitor-health.json", monitor)
            pulse = {
                "schema": "vh-map02-pulse-sink-input-observation/v1",
                "unique_target_each_snapshot": True,
                "buffer_latency_us": {
                    "during": 16000 if succeeded else 10666,
                    "after": 15332 if succeeded else 10666
                }
            }
            save_json(d / "pulse-sink-input-observed.json", pulse)
            optical = None
            sink = None
            if succeeded:
                optical = {
                    "schema": "vh-map02-presubmit-optical/v1",
                    "result": "GUEST_PRESUBMIT_PCM_PAGES_MATCHED",
                    "observed_pages": 8, "mismatches": 0,
                    "actual_audout_call_observed": True,
                    "pages": [
                        {"index": i, "descriptor_released_returns": 1}
                        for i in range(8)]
                }
                sink = {"schema": "vh-map02-presubmit-sink-audit/v1",
                        "per_page_matches": [1] * 8}
                save_json(d / "presubmit-guest.json", optical)
                save_json(d / "presubmit-sink-parity.json", sink)
            save_json(d / "presubmit-guest-evidence-conjunction.json",
                      classify(optical, monitor, sink=sink, pulse=pulse,
                               prejoin=stage))


class BoundaryAuditTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        # Generate all six CRC-8/XOR images once per test case.
        make_fixture(self.root)

    def case(self, ms=21, repeat=1):
        return self.root / f"map02-presubmit-nexium-guest-proof-{ms}-r{repeat}"

    def fast_decode(self, path):
        # Mutating tests use the independently captured original decoded
        # fixture JSON; the positive test below runs the real PNG decoder.
        return self.original_stage[path.parent.name]

    def initialize_fast(self):
        self.original_stage = {
            self.case(ms, r).name:
            json.loads((self.case(ms, r) /
                        "presubmit-guest-prejoin-stage.json").read_text())
            for ms in (21, 22) for r in (1, 2, 3)
        }

    def test_real_images_and_pcm_sixway_audit(self):
        data = audit(self.root)
        self.assertTrue(data["all_six_artifact_provenance_and_pcm_integrity_verified"])
        self.assertEqual(len(data["trials"]), 6)
        self.assertEqual(data["by_hint"]["21"]["zero_monitor_pcm_trials"], 3)
        self.assertEqual(data["by_hint"]["22"]["completed_cleanup_trials"], 3)
        self.assertTrue(all(
            row["classification"] ==
            ("EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK"
             if row["hint_ms"] == 22 else "OPTICAL_MISSING_ZERO_VIRTUAL_SINK")
            for row in data["trials"]))
        self.assertFalse(data["audout_service_deadlock_proven"])
        self.assertFalse(data["buffer_hint_causality_proven"])
        self.assertTrue(data["same_guest_nro_sha256_all_six_verified"])
        self.assertFalse(data["nexium_release_asset_digest_pinned_in_original_workflow"])
        self.assertFalse(data["same_nexium_host_binary_all_six_verified"])
        self.assertFalse(data["nexium_host_binary_sha256_available_in_original_artifacts"])
        self.assertTrue(all(r["nexium_host_binary_sha256"] is None
                            for r in data["trials"]))

    def test_forged_boolean_pcm_success_in_stored_receipt_rejected(self):
        self.initialize_fast()
        path = self.case(22, 1) / "presubmit-guest-evidence-conjunction.json"
        obj = json.loads(path.read_text())
        self.assertTrue(obj["guest_8page_receipt_valid"])
        obj["guest_8page_receipt_valid"] = False
        save_json(path, obj)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            audit(self.root, decode=self.fast_decode)

    def test_forged_virtual_pcm_presence_rejected(self):
        self.initialize_fast()
        path = self.case(21, 2) / "presubmit-guest-evidence-conjunction.json"
        obj = json.loads(path.read_text())
        self.assertFalse(obj["virtual_48k_pcm_nonzero"])
        obj["virtual_48k_pcm_nonzero"] = True
        save_json(path, obj)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            audit(self.root, decode=self.fast_decode)

    def test_wrong_source_manifest_is_rejected(self):
        self.initialize_fast()
        path = self.case() / "manifest.json"
        obj = json.loads(path.read_text())
        obj["source_sha"] = "bad"
        save_json(path, obj)
        with self.assertRaisesRegex(ValueError, "source"):
            audit(self.root, decode=self.fast_decode)

    def test_tampered_raw_pcm_is_rejected(self):
        self.initialize_fast()
        path = self.case(22, 2) / "presubmit-virtual-sink-s16le-48k.pcm"
        path.write_bytes(struct.pack("<hh", 8, 0))
        with self.assertRaisesRegex(ValueError, "PCM bytes"):
            audit(self.root, decode=self.fast_decode)

    def test_forged_stage_json_is_rejected(self):
        self.initialize_fast()
        path = self.case(21, 3) / "presubmit-guest-prejoin-stage.json"
        obj = json.loads(path.read_text())
        obj["audout_playbuffer_call_returns"] = 1
        save_json(path, obj)
        with self.assertRaisesRegex(ValueError, "CRC-8/XOR"):
            audit(self.root, decode=self.fast_decode)

    def test_missing_independent_repetition_is_rejected(self):
        self.initialize_fast()
        shutil.rmtree(self.case(22, 3))
        with self.assertRaisesRegex(ValueError, "six"):
            audit(self.root, decode=self.fast_decode)

    def test_ambiguous_host_buffer_client_is_rejected(self):
        self.initialize_fast()
        path = self.case(21, 1) / "pulse-sink-input-observed.json"
        obj = json.loads(path.read_text())
        obj["unique_target_each_snapshot"] = False
        save_json(path, obj)
        with self.assertRaisesRegex(ValueError, "uniquely"):
            audit(self.root, decode=self.fast_decode)

    def test_classification_corruption_cannot_pass(self):
        self.initialize_fast()
        path = self.case(21, 2) / "presubmit-guest-evidence-conjunction.json"
        obj = json.loads(path.read_text())
        obj["classification"] = "EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK"
        save_json(path, obj)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            audit(self.root, decode=self.fast_decode)


if __name__ == "__main__":
    unittest.main()
