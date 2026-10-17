"""Synthetic after-capture validation never authenticates retail game resources."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.preflight_map02_private_dda_capture import preflight
from tools.verify_map02_private_capture_session import verify_session
from tools.verify_map02_vram_timeline import VRAM_BYTES

SPAN = {
    "stage": "native_dda_span", "step": 0, "frame": 3,
    "primitive_ordinal": 0, "primitive_type": 2, "y": 12,
    "x_start": 10, "x_bound": 20, "clip_l": 5, "clip_r": 25,
    "clip_t": 10, "clip_b": 15,
}


class PrivateCaptureSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "capture"
        self.root.mkdir(mode=0o700)
        os.chmod(self.root, 0o700)
        self.binary = Path(self.temp.name) / "pcport-capture"
        self.binary.write_bytes(b"synthetic binary for local test only\x00")
        self.binary.chmod(0o700)
        settings = {
            "VH_MAP02_GPU_CAPTURE_DIR": str(self.root),
            "VH_MAP02_PUTPIXEL_DIR": str(self.root),
            "VH_MAP02_GPU_CAPTURE_FRAME": "3",
            "VH_MAP02_PUTPIXEL_FRAME": "3",
            "VH_MAP02_PUTPIXEL_X": "30",
            "VH_MAP02_PUTPIXEL_Y": "12",
        }
        self.report = preflight(settings, executable=self.binary)
        self.report_path = Path(self.temp.name) / "preflight.json"
        self.save_report()
        (self.root / "dda-native-spans.jsonl").write_text(
            json.dumps(SPAN, sort_keys=True) + "\n", encoding="utf-8")
        for step, phase in enumerate(("before", "after")):
            gpu = {
                "stage": "native_vram", "step": step, "frame": 3,
                "phase": phase, "operation": "draw",
                "snapshot": f"gpu-{step:04d}-vram.bin",
                "rect": None, "dest": [0, 0], "rgb": [0, 0, 0],
                "primitive_type": 2, "semi": 0, "window": [0, 0, 0, 0],
                "draw_mode": [0, 0, 0], "upload": "",
                "ft4": {"tpage":0, "clut":0,
                         "xy":[0,0,1,0,0,1,1,1],
                         "uv":[0,0,1,0,0,1,1,1]},
            }
            with (self.root / "gpu-native-events.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(gpu, sort_keys=True) + "\n")
            (self.root / gpu["snapshot"]).write_bytes(bytes(VRAM_BYTES))

    def save_report(self):
        self.report_path.write_text(json.dumps(self.report, sort_keys=True),
                                    encoding="utf-8")

    def verify(self):
        return verify_session(self.root, native_frame=3,
                              preflight_report=self.report_path,
                              executable=self.binary)

    def test_linked_fingerprints_no_false_game_provenance(self):
        result = self.verify()
        self.assertEqual(result["frame"], 3)
        self.assertTrue(result["executable_bytes_match_preflight"])
        self.assertTrue(result["native_gpu_binding"]["verified"])
        self.assertEqual(result["dda_observation_mode"], "entered_only")
        self.assertFalse(result["all_dda_journal_classes_observed"])
        self.assertEqual(result["native_gpu_pairs_verified"], 1)
        self.assertEqual(result["load_pairs_with_verified_payload"], 0)
        self.assertEqual(result["load_pairs_without_payload"], 0)
        self.assertIsNone(result["upload_payload_sha256_list_sha256"])
        zero_digest = hashlib.sha256(bytes(VRAM_BYTES)).hexdigest()
        expected_chain = hashlib.sha256((zero_digest * 2).encode("ascii")).hexdigest()
        self.assertEqual(result["vram_snapshot_sha256_list_sha256"], expected_chain)
        self.assertEqual(result["native_gpu_binding"]["vram_snapshot_sha256_list_sha256"],
                         expected_chain)
        self.assertEqual(result["executable_sha256"],
                         hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.assertIsNone(result["dda_journal_fingerprints"][
            "dda-rejected-edge-candidates.jsonl"]["event_count"])
        for name in ("executable_actually_launched_verified",
                     "binary_instrumentation_verified", "retail_map02_frame_verified",
                     "hd_replacement_authorized"):
            self.assertIs(result[name], False)
        text = json.dumps(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.binary), text)
        self.assertNotIn('"x_start"', text)

    def test_vram_snapshot_mutation_changes_evidence_chain(self):
        first = self.verify()
        snapshot = self.root / "gpu-0001-vram.bin"
        raw = bytearray(snapshot.read_bytes())
        raw[0] = 77
        snapshot.write_bytes(raw)
        second = self.verify()
        self.assertNotEqual(first["vram_snapshot_sha256_list_sha256"],
                            second["vram_snapshot_sha256_list_sha256"])
        self.assertTrue(second["native_gpu_binding"]["verified"])
        self.assertFalse(second["retail_map02_frame_verified"])

    def test_modified_executable_fails(self):
        self.binary.write_bytes(self.binary.read_bytes() + b"modified")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.verify()

    def test_mismatched_preflight_frame_and_false_provenance_fail(self):
        self.report["capture_frame"] = 4
        self.save_report()
        with self.assertRaisesRegex(ValueError, "frame"):
            self.verify()
        self.report["capture_frame"] = 3
        self.report["hd_replacement_authorized"] = True
        self.save_report()
        with self.assertRaisesRegex(ValueError, "falsely claims"):
            self.verify()

    def test_wrong_preflight_fields_and_duplicate_json_fail(self):
        self.report["game_assets_path"] = "should-never-appear"
        self.save_report()
        with self.assertRaisesRegex(ValueError, "schema"):
            self.verify()
        del self.report["game_assets_path"]
        self.report_path.write_bytes(
            json.dumps(self.report).replace(
                '"capture_frame": 3', '"capture_frame": 3, "capture_frame": 3'
            ).encode())
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.verify()

    def test_missing_gpu_snapshot_and_wrong_frame_fail(self):
        (self.root / "gpu-0001-vram.bin").unlink()
        with self.assertRaises(ValueError):
            self.verify()
        (self.root / "gpu-0001-vram.bin").write_bytes(bytes(VRAM_BYTES))
        with self.assertRaisesRegex(ValueError, "frame"):
            verify_session(self.root, native_frame=4,
                           preflight_report=self.report_path,
                           executable=self.binary)

    def test_preflight_report_symlink_and_missing_fingerprint_refused(self):
        link = Path(self.temp.name) / "link.json"
        link.symlink_to(self.report_path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_session(self.root, native_frame=3, preflight_report=link,
                           executable=self.binary)
        self.report["executable_sha256"] = None
        self.save_report()
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
