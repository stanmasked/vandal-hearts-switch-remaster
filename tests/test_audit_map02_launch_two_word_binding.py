"""Asset-free unit cross-joins plus the actual synthetic two-word FT4 replay.

The mocked launch result models an already independently verified private
subprocess receipt; the FT4/OT/VRAM/PutPixel side is checked end-to-end.
This cannot authenticate actual retail process execution.
"""
import json
import unittest
from unittest.mock import patch

import test_verify_map02_putpixel_multi_scope as fixture_module
from tools.audit_map02_launch_two_word_binding import audit_launch_two_word
from tools.verify_map02_putpixel_multi_scope import verify_multi_pixel_ot


class TwoWordPrivateLauncherBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.TwoWordPutPixelTests(
            methodName="test_interleaved_two_coordinates_bound_to_same_drawotag")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source, self.native = self.fixture.source, self.fixture.native
        checked = verify_multi_pixel_ot(self.source, self.native)
        self.claimed_launch = {
            "frame": checked["native_gpu_frame"],
            "original_receipt_sha256": "a" * 64,
            "native_gpu_event_log_sha256": checked["native_gpu_event_log_sha256"],
            "raw_evidence_matches_original_receipt": True,
        }

    def check(self):
        with patch("tools.audit_map02_launch_two_word_binding.replay_receipt",
                   return_value=dict(self.claimed_launch)) as mocked:
            report = audit_launch_two_word(
                self.native, self.source,
                launch_receipt=self.source / "fake-private-process-receipt.json",
                preflight_report=self.source / "fake-preflight.json",
                executable=self.source / "fake-executable",
            )
        self.assertEqual(mocked.call_count, 1)
        return report

    def test_same_native_gpu_log_frame_and_full_ft4_replay_accepted(self):
        report = self.check()
        self.assertEqual(report["source_frame"], 411)
        self.assertEqual(report["native_gpu_frame"], 12)
        self.assertEqual(report["source_keyed_ft4_draws_checked"], 2)
        self.assertTrue(report["same_native_gpu_log_sha256_verified"])
        self.assertTrue(report["preflight_executable_and_original_receipt_replayed"])
        self.assertTrue(report["source_gte_ft4_ot_vram_putpixel_replayed"])
        self.assertTrue(report["two_distinct_private_words_verified"])
        for key in (
            "native_process_to_log_causality_authenticated",
            "retail_map02_gameplay_authenticated",
            "ps1_or_switch_pixel_equivalence_verified",
            "hd_replacement_authorized",
            "raw_pixel_coordinates_or_colors_emitted",
        ):
            self.assertFalse(report[key])
        public = json.dumps(report)
        for private in ('"x"', '"y"', '"before"', '"front"', '"after"',
                        "0x801f", "fake-executable", str(self.native),
                        str(self.source)):
            self.assertNotIn(private, public)

    def test_reject_identical_native_gpu_log_bytes_but_different_frame(self):
        self.claimed_launch["frame"] += 1
        with self.assertRaisesRegex(ValueError, "target frames disagree"):
            self.check()

    def test_reject_nonmatching_native_gpu_sha_even_if_both_replays_claim_valid(self):
        self.claimed_launch["native_gpu_event_log_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "native GPU log digests differ"):
            self.check()

    def test_reject_false_original_launch_evidence(self):
        self.claimed_launch["raw_evidence_matches_original_receipt"] = False
        with self.assertRaisesRegex(ValueError, "not replayable"):
            self.check()

    def test_private_same_directory_or_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "directories must differ"):
            audit_launch_two_word(
                self.native, self.native, launch_receipt=self.source/"x",
                preflight_report=self.source/"y", executable=self.source/"z")
        link = self.source.parent / "source-alias"
        link.symlink_to(self.source, target_is_directory=True)
        self.addCleanup(link.unlink)
        with self.assertRaisesRegex(ValueError, "unavailable or linked"):
            audit_launch_two_word(
                self.native, link, launch_receipt=self.source/"x",
                preflight_report=self.source/"y", executable=self.source/"z")

    def test_private_source_ft4_or_gpu_mutation_still_fails_validation(self):
        source_log = self.source / "gpu-events.jsonl"
        source_log.write_bytes(source_log.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
