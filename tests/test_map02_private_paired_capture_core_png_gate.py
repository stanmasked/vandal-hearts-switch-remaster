"""Stage507 fictional two-run core+PNG gate; no original game content."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_paired_capture_core_png_gate import (
    RUN_NAMES, main, review_owner_capture,
)
from tools.map02_private_process_witness_binding import (
    MAGIC as START_MAGIC, NAME as START_NAME,
)

TICKS_A = 639000000000000001
TICKS_B = 639000000000000002
PAIR = {
    "two_private_capture_chains_passed": True,
    "both_runs_reported_psx_core_fallback_disabled": True,
    "screenshot_pairs_checked": 3,
    "decoded_pixel_equal_pairs": 3,
    "decoded_pixel_different_pairs": 0,
    "decoded_pixel_unsupported_pairs": 0,
    "all_supported_png_pixel_content_equal": True,
}


def start_receipt(pid: int, birth: int) -> bytes:
    return (f"{START_MAGIC}\nprocess_id={pid}\n"
            f"process_start_utc_ticks={birth}\n").encode("ascii")


def core_receipt(pid: int, birth: int) -> bytes:
    return ("VH_MAP02_RUNTIME_CORE_WITNESS_V1\n"
            "system=PSX\nloaded_core=Octoshock\n"
            "core_source=IEmulator.Attributes.CoreName\n"
            f"process_id={pid}\nprocess_start_utc_ticks={birth}\n"
            "frame_count=1800\nbios=unverified\ndisc=unverified\n"
            "movie_sync=unverified\n").encode("ascii")


class OwnerCombinedGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workspace = self.root / "private-workspace"
        self.workspace.mkdir(mode=0o700)
        self.workspace.chmod(0o700)
        self.runs = [self.workspace / name for name in RUN_NAMES]
        for directory in self.runs:
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)
        self.movie = self.root / "fictional.bk2"
        self.plan = self.root / "fictional-plan.txt"
        self.movie.write_bytes(b"fictional movie only")
        self.plan.write_bytes(b"fictional plan only")
        self.witness = [
            self.root / "fictional-core-1.txt",
            self.root / "fictional-core-2.txt",
        ]
        for folder, target, pid, ticks in zip(
            self.runs, self.witness, (3011, 3012), (TICKS_A, TICKS_B)
        ):
            (folder / START_NAME).write_bytes(start_receipt(pid, ticks))
            target.write_bytes(core_receipt(pid, ticks))

    def review(self, pair=None):
        with patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=dict(PAIR if pair is None else pair),
        ) as paired:
            result = review_owner_capture(
                self.movie, self.plan, self.workspace,
                self.witness[0], self.witness[1],
            )
        paired.assert_called_once_with(
            self.movie, self.plan, self.runs[0].resolve(strict=True),
            self.runs[1].resolve(strict=True),
        )
        return result

    def test_two_independent_process_bound_witnesses_and_rgb_audit(self):
        result = self.review()
        self.assertEqual(result["owner_private_capture_chains_reaudited"], 2)
        self.assertEqual(result["manual_psx_octoshock_core_witnesses_process_matched"], 2)
        self.assertTrue(result["all_reviewed_decoded_png_pixels_equal"])
        self.assertFalse(result["authentic_map02_scene_identified"])
        self.assertFalse(result["actual_emuhawk_loaded_bios_authenticated"])
        self.assertFalse(result["original_bk2_controller_delivery_authenticated"])
        serialized = json.dumps(result)
        for secret in ("3011", str(TICKS_A), str(self.root), "fictional.bk2"):
            self.assertNotIn(secret, serialized)

    def test_swapped_core_witnesses_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            with patch(
                "tools.map02_private_paired_capture_core_png_gate.audit_pair",
                return_value=dict(PAIR),
            ):
                review_owner_capture(
                    self.movie, self.plan, self.workspace,
                    self.witness[1], self.witness[0],
                )

    def test_missing_manual_witness_fails(self):
        self.witness[1].unlink()
        with self.assertRaises((OSError, ValueError)):
            self.review()

    def test_stale_process_start_fails(self):
        self.witness[0].write_bytes(core_receipt(3011, TICKS_B))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.review()

    def test_claimed_core_cannot_be_faked_as_nymashock(self):
        self.witness[0].write_bytes(
            core_receipt(3011, TICKS_A).replace(b"Octoshock", b"Nymashock"))
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            self.review()

    def test_duplicate_launch_receipt_fails(self):
        (self.runs[1] / START_NAME).write_bytes(start_receipt(3011, TICKS_A))
        with self.assertRaisesRegex(ValueError, "reuse"):
            self.review()

    def test_pixel_divergence_reported_not_authentic_parity(self):
        pair = dict(PAIR, decoded_pixel_equal_pairs=2,
                    decoded_pixel_different_pairs=1,
                    all_supported_png_pixel_content_equal=False)
        report = self.review(pair)
        self.assertFalse(report["all_reviewed_decoded_png_pixels_equal"])
        self.assertEqual(report["decoded_pixel_different_pairs"], 1)
        self.assertFalse(report["switch_renderer_parity_authenticated"])

    def test_unsupported_png_pixels_reported(self):
        pair = dict(PAIR, decoded_pixel_equal_pairs=2,
                    decoded_pixel_unsupported_pairs=1,
                    all_supported_png_pixel_content_equal=False)
        result = self.review(pair)
        self.assertFalse(result["all_reviewed_decoded_png_pixels_equal"])

    def test_reject_inconsistent_png_statistics(self):
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.review(dict(PAIR, decoded_pixel_equal_pairs=2))

    def test_reject_inconsistent_png_boolean(self):
        with self.assertRaisesRegex(ValueError, "summary inconsistent"):
            self.review(dict(PAIR, all_supported_png_pixel_content_equal=False))

    def test_reject_fake_unverified_capture_audit(self):
        with self.assertRaisesRegex(ValueError, "independent re-audit"):
            self.review(dict(PAIR, two_private_capture_chains_passed=False))

    def test_reject_missing_fallback_block(self):
        with self.assertRaisesRegex(ValueError, "fallback"):
            self.review(dict(PAIR, both_runs_reported_psx_core_fallback_disabled=False))

    def test_reject_zero_or_boolean_frame_count(self):
        for invalid in (0, True, 31):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "pair count"):
                    self.review(dict(PAIR, screenshot_pairs_checked=invalid))

    def test_reject_missing_or_insecure_private_run_dir(self):
        (self.runs[1] / START_NAME).unlink()
        self.runs[1].rmdir()
        with self.assertRaisesRegex(ValueError, "existing absolute"):
            self.review()

    def test_git_checkout_is_not_valid_capture_workspace(self):
        (self.workspace / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            self.review()

    def test_cli_only_prints_redacted_json(self):
        output = io.StringIO()
        with patch.object(sys, "argv", [
            "private-paired-gate", str(self.movie), str(self.plan),
            str(self.workspace), str(self.witness[0]), str(self.witness[1]),
        ]), patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=dict(PAIR),
        ), contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        payload = output.getvalue()
        self.assertEqual(json.loads(payload)["screenshot_pairs_checked"], 3)
        for secret in (str(self.root), "3011", str(TICKS_A)):
            self.assertNotIn(secret, payload)

    def test_cli_nonzero_for_pixel_mismatch_without_private_values(self):
        output = io.StringIO()
        pair = dict(PAIR, decoded_pixel_equal_pairs=2,
                    decoded_pixel_different_pairs=1,
                    all_supported_png_pixel_content_equal=False)
        with patch.object(sys, "argv", [
            "private-paired-gate", str(self.movie), str(self.plan),
            str(self.workspace), str(self.witness[0]), str(self.witness[1]),
        ]), patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=pair,
        ), contextlib.redirect_stdout(output):
            self.assertEqual(main(), 2)
        self.assertFalse(json.loads(output.getvalue())[
            "all_reviewed_decoded_png_pixels_equal"])


    def test_automatic_core_witnesses_in_run_folders_are_locally_bound(self):
        from tools.map02_private_bizhawk_poweron_launch import AUTO_WITNESS_NAME
        for run, witness in zip(self.runs, self.witness):
            (run / AUTO_WITNESS_NAME).write_bytes(witness.read_bytes())
        with patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=dict(PAIR, both_owner_logs_report_auto_core_witness_before_first_png=True),
        ):
            report = review_owner_capture(self.movie, self.plan, self.workspace)
        self.assertEqual(report["auto_psx_octoshock_core_witnesses_process_matched"], 2)
        self.assertEqual(report["manual_psx_octoshock_core_witnesses_process_matched"], 0)
        self.assertFalse(report["authentic_map02_scene_identified"])

    def test_partial_manual_witness_pair_is_rejected(self):
        with patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=dict(PAIR, both_owner_logs_report_auto_core_witness_before_first_png=True),
        ):
            with self.assertRaisesRegex(ValueError, "must be consistent"):
                review_owner_capture(
                    self.movie, self.plan, self.workspace, self.witness[0], None
                )

    def test_automatic_core_witness_missing_from_second_run_rejected(self):
        from tools.map02_private_bizhawk_poweron_launch import AUTO_WITNESS_NAME
        (self.runs[0] / AUTO_WITNESS_NAME).write_bytes(self.witness[0].read_bytes())
        with patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=dict(PAIR, both_owner_logs_report_auto_core_witness_before_first_png=True),
        ):
            with self.assertRaises((OSError, ValueError)):
                review_owner_capture(self.movie, self.plan, self.workspace)


    def test_auto_core_witness_requires_audited_pre_png_marker(self):
        from tools.map02_private_bizhawk_poweron_launch import AUTO_WITNESS_NAME
        for run, witness in zip(self.runs, self.witness):
            (run / AUTO_WITNESS_NAME).write_bytes(witness.read_bytes())
        with patch(
            "tools.map02_private_paired_capture_core_png_gate.audit_pair",
            return_value=dict(PAIR, both_owner_logs_report_auto_core_witness_before_first_png=False),
        ):
            with self.assertRaisesRegex(ValueError, "before first PNG"):
                review_owner_capture(self.movie, self.plan, self.workspace)


if __name__ == "__main__":
    unittest.main()
