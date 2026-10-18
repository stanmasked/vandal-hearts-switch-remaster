"""Asset-free bridge between private BGR555 comparison and native MAP02 replay."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import bridge_map02_private_frame_native as bridge
from tools import compare_map02_private_bgr555_frames as frames


class PrivateFrameNativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-frame-native-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.pair = self.dir / "frames"
        self.pair.mkdir()
        self.frame = 123
        self.ref = [0, 0x7fff, 1, 2]
        self.cand = list(self.ref)
        self.draws = 2
        self.native = {
            "schema": "vh.map02.private-launch-two-word-join.v1",
            "source_frame": self.frame,
            "native_gpu_frame": self.frame,
            "source_keyed_ft4_draws_checked": self.draws,
            "original_launch_receipt_sha256": "1" * 64,
            "two_word_manifest_sha256": "2" * 64,
            "native_gpu_event_log_sha256": "3" * 64,
            **{field: True for field in bridge.TRUE_FIELDS},
            **{field: False for field in bridge.FALSE_FIELDS},
        }
        self.write_pair()

    def write_pair(self):
        images = {}
        for name, words, origin in (
                ("reference.bgr555", self.ref, "ps1_reference_claimed"),
                ("candidate.bgr555", self.cand, "pc_port_candidate_claimed")):
            raw = struct.pack("<" + "H" * len(words), *words)
            (self.pair / name).write_bytes(raw)
            images[name] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "frame": self.frame, "origin": origin}
        meta = {
            "schema": frames.SCHEMA, "frame": self.frame,
            "width": 2, "height": 2, "pixel_format": "bgr555_le",
            "images": images,
        }
        (self.pair / "frames.json").write_text(json.dumps(meta), encoding="utf-8")

    def run_bridge(self, side_effect=None, **kwargs):
        def fake(*args, **params):
            self.assertTrue(params["require_native_elf_image"])
            self.assertTrue(params["require_native_probe_symbols"])
            self.assertEqual(params["compiler"], kwargs.get("compiler", "gcc"))
            if side_effect:
                side_effect()
            return dict(self.native)
        with patch.object(bridge, "audit_launch_two_word", side_effect=fake) as audit:
            result = bridge.bridge(
                self.pair, self.dir / "native", self.dir / "source",
                launch_receipt=self.dir / "launch.json",
                preflight_report=self.dir / "preflight.json",
                executable=self.dir / "user-owned-elf",
                compiler=kwargs.get("compiler", "gcc"))
        self.assertEqual(audit.call_count, 1)
        return result

    def test_identical_frames_strict_probes_are_label_join_only(self):
        result = self.run_bridge()
        self.assertEqual(result["different_bgr555_pixels"], 0)
        self.assertEqual(result["exact_bgr555_pixel_matches"], 4)
        self.assertTrue(result["strict_native_elf_probe_replay_verified"])
        self.assertTrue(result["private_frame_pair_stable_through_native_replay"])
        self.assertTrue(result["same_frame_labels_verified"])
        for key in ("frame_bytes_causally_bound_to_executed_game",
                    "retail_disc_resources_authenticated",
                    "ps1_reference_capture_authenticated",
                    "pc_port_frame_capture_authenticated",
                    "ps1_hardware_pixel_equivalence_verified",
                    "hd_replacement_authorized",
                    "raw_pixel_values_or_private_paths_emitted"):
            self.assertFalse(result[key])
        public = json.dumps(result)
        self.assertNotIn(str(self.dir), public)
        self.assertNotIn("0x7fff", public)

    def test_changed_pixel_counts_preserved(self):
        self.cand[0] = 0x8000
        self.write_pair()
        result = self.run_bridge(compiler="clang")
        self.assertEqual(result["different_bgr555_pixels"], 1)
        self.assertEqual(result["stp_bit_differences"], 1)

    def test_reference_and_native_frame_disagree(self):
        self.native["source_frame"] += 1
        with self.assertRaisesRegex(ValueError, "frame and native GPU capture"):
            self.run_bridge()

    def test_native_and_reference_frame_disagree(self):
        self.native["native_gpu_frame"] += 1
        with self.assertRaisesRegex(ValueError, "frame and native GPU capture"):
            self.run_bridge()

    def test_incomplete_native_elf_witness_refused(self):
        self.native["native_elf_image_observed"] = False
        with self.assertRaisesRegex(ValueError, "witness incomplete"):
            self.run_bridge()

    def test_static_probe_symbols_missing_refused(self):
        self.native["native_probe_symbols_inspected"] = False
        with self.assertRaisesRegex(ValueError, "witness incomplete"):
            self.run_bridge()

    def test_source_native_log_digest_gate_missing(self):
        self.native["same_native_gpu_log_sha256_verified"] = False
        with self.assertRaisesRegex(ValueError, "witness incomplete"):
            self.run_bridge()

    def test_missing_source_keyed_ft4_draws_refused(self):
        self.native["source_keyed_ft4_draws_checked"] = 0
        with self.assertRaisesRegex(ValueError, "draw evidence missing"):
            self.run_bridge()

    def test_fake_approved_hd_flag_rejected(self):
        self.native["hd_replacement_authorized"] = True
        with self.assertRaisesRegex(ValueError, "unexpectedly asserted"):
            self.run_bridge()

    def test_falsely_authenticated_gameplay_rejected(self):
        self.native["retail_map02_gameplay_authenticated"] = True
        with self.assertRaisesRegex(ValueError, "unexpectedly asserted"):
            self.run_bridge()

    def test_changed_candidate_and_hash_during_native_replay_refused(self):
        def swap():
            self.cand[0] = 7
            self.write_pair()
        with self.assertRaisesRegex(ValueError, "changed during native witness"):
            self.run_bridge(side_effect=swap)

    def test_changed_reference_and_hash_during_native_replay_refused(self):
        def swap():
            self.ref[1] = 0x1234
            self.write_pair()
        with self.assertRaisesRegex(ValueError, "changed during native witness"):
            self.run_bridge(side_effect=swap)

    def test_changed_candidate_without_hash_cannot_pass(self):
        def corrupt():
            (self.pair / "candidate.bgr555").write_bytes(b"\xff\xff" * 4)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.run_bridge(side_effect=corrupt)

    def test_symlink_replacement_of_pair_denied(self):
        path = self.pair / "candidate.bgr555"
        backup = self.pair / "another-image"
        path.rename(backup)
        path.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.run_bridge()

    def test_wrong_native_schema_rejected(self):
        self.native["schema"] = "fake-native"
        with self.assertRaisesRegex(ValueError, "schema invalid"):
            self.run_bridge()

    def test_invalid_compiler_rejected_before_native_replay(self):
        with self.assertRaisesRegex(ValueError, "compiler selector invalid"):
            self.run_bridge(compiler="not-a-compiler")


if __name__ == "__main__":
    unittest.main()
