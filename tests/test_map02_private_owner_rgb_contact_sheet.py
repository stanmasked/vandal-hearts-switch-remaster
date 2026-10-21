"""Invented PNGs only: review image renderer never reads owner BK2 in CI."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import test_map02_private_dual_capture_rgb_repeatability as dual_fixtures
from tools.map02_private_owner_rgb_contact_sheet import (
    SCHEMA, MAX_SHEET_PIXELS, _checked_groups, _output_path_safely_uncreated, render,
)
from tools.map02_private_reviewed_scene_candidates import SCHEMA as CANDIDATE_SCHEMA


class PrivateContactSheetTests(unittest.TestCase):
    def setUp(self):
        fixture = dual_fixtures.PrivateDualRGBTests(
            "test_two_supplied_identical_pixel_sets_are_exact")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.image_out = fixture.root / "owner-only-contact-sheet.png"

    def call(self, output=None, *, count=3, reviewed_candidates=None):
        f = self.fixture
        with patch(
            "tools.map02_private_dual_capture_rgb_repeatability.verify_chain",
            return_value={"screenshot_count": count},
        ) as audit:
            result = render(
                f.movie, f.plan, f.logs[0], f.folders[0],
                f.logs[1], f.folders[1],
                output if output is not None else self.image_out,
                minimum=200, maximum=1000,
                reviewed_candidates=reviewed_candidates,
            )
        self.assertEqual(audit.call_count, 2)
        return result

    def test_outputs_owner_only_png_and_conservative_report(self):
        result = self.call()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["private_review_groups"], 1)
        self.assertEqual(result["paired_screenshot_positions"], 3)
        self.assertEqual(result["decoded_rgb_mismatches"], 0)
        self.assertTrue(result["both_owner_supplied_capture_chains_revalidated"])
        self.assertTrue(result["private_owner_only_png_created"])
        for field in (
            "actual_ps1_emulation_authenticated",
            "two_independent_emulator_processes_authenticated",
            "input_to_video_offset_verified",
            "map02_scene_identified",
            "ps1_gpu_vram_parity_verified", "private_media_uploaded",
        ):
            self.assertFalse(result[field])
        self.assertNotIn(str(self.fixture.root), json.dumps(result))
        self.assertNotIn("3000", json.dumps(result))
        data = self.image_out.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(self.image_out) as screenshot:
            self.assertEqual(screenshot.mode, "RGB")
            self.assertGreaterEqual(screenshot.width, 900)
            self.assertGreaterEqual(screenshot.height, 400)
            screenshot.verify()
        self.assertEqual(self.image_out.stat().st_mode & 0o777, 0o600)

    def write_candidate_report(self, *, state="requires_game_state_witness",
                               plan_sha256=None):
        plan_sha = plan_sha256 or hashlib.sha256(
            self.fixture.plan.read_bytes()).hexdigest()
        candidate = state == "requires_game_state_witness"
        report = {
            "schema": CANDIDATE_SCHEMA,
            "source_plan_sha256": plan_sha,
            "private_review_group_count": 1,
            "review_groups_requiring_game_state_witness": 1 if candidate else 0,
            "groups": [{
                "review_group": 1,
                "state": state,
                "all_three_positions_exact_rgb_equal_across_supplied_sets": candidate,
                "manual_transition_pattern": candidate,
                "intra_group_visual_change_confirmed": candidate,
                "actual_map02_scene_authenticated": False,
            }],
            "source_capture_chains_revalidated": True,
            "two_capture_sets_independently_authenticated": False,
            "independent_human_reviewers_authenticated": False,
            "input_to_video_alignment_verified": False,
            "actual_map02_start_authenticated": False,
            "original_ps1_game_authenticated": False,
            "game_state_or_gpu_vram_witness_available": False,
            "private_bk2_images_labels_or_frame_coordinates_uploaded": False,
        }
        path = self.fixture.root / "owner-private-reviewed-candidates.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_plan_bound_shortlist_filters_sheet_and_marks_limits(self):
        report = self.write_candidate_report()
        result = self.call(reviewed_candidates=report)
        self.assertTrue(result["reviewed_candidate_filter_applied"])
        self.assertTrue(result["candidate_report_plan_binding_verified"])
        self.assertEqual(result["candidate_filter_group_count"], 1)
        self.assertEqual(result["private_review_groups"], 1)
        self.assertEqual(result["paired_screenshot_positions"], 3)
        self.assertEqual(result["source_audited_screenshot_positions"], 3)
        self.assertFalse(result["map02_scene_identified"])
        self.assertEqual(self.image_out.stat().st_mode & 0o777, 0o600)

    def test_shortlist_for_different_plan_is_rejected_without_output(self):
        report = self.write_candidate_report(plan_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "does not match current private capture plan"):
            self.call(reviewed_candidates=report)
        self.assertFalse(self.image_out.exists())

    def test_empty_candidate_shortlist_is_rejected_without_output(self):
        report = self.write_candidate_report(state="not_candidate_in_selected_frames")
        with self.assertRaisesRegex(ValueError, "no eligible groups"):
            self.call(reviewed_candidates=report)
        self.assertFalse(self.image_out.exists())

    def test_candidate_report_overclaiming_emulator_provenance_is_rejected(self):
        report = self.write_candidate_report()
        payload = json.loads(report.read_text(encoding="utf-8"))
        payload["two_capture_sets_independently_authenticated"] = True
        report.write_text(json.dumps(payload), encoding="utf-8")
        report.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "overclaims provenance"):
            self.call(reviewed_candidates=report)
        self.assertFalse(self.image_out.exists())

    def test_candidate_report_rejects_non_string_state_without_output(self):
        report = self.write_candidate_report()
        payload = json.loads(report.read_text(encoding="utf-8"))
        payload["groups"][0]["state"] = []
        report.write_text(json.dumps(payload), encoding="utf-8")
        report.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "groups do not match capture plan"):
            self.call(reviewed_candidates=report)
        self.assertFalse(self.image_out.exists())

    def test_candidate_report_must_be_owner_private(self):
        report = self.write_candidate_report()
        report.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-only regular JSON"):
            self.call(reviewed_candidates=report)
        self.assertFalse(self.image_out.exists())

    def test_disagreement_remains_reviewable_not_scene_proof(self):
        f = self.fixture
        f.image(1, "middle").write_bytes(
            dual_fixtures.synthetic_png((250, 1, 10)))
        result = self.call()
        self.assertEqual(result["decoded_rgb_mismatches"], 1)
        self.assertFalse(result["map02_scene_identified"])

    def test_png_metadata_byte_difference_does_not_count_as_rgb_difference(self):
        f = self.fixture
        f.image(1, "middle").write_bytes(
            dual_fixtures.synthetic_png(
                dual_fixtures.COLORS[1], metadata=True))
        report = self.call()
        self.assertEqual(report["decoded_rgb_mismatches"], 0)

    def test_refuses_existing_output_without_overwriting(self):
        self.image_out.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            self.call()
        self.assertEqual(self.image_out.read_bytes(), b"do not overwrite")

    def test_refuses_symlink_output(self):
        target = self.fixture.root / "existing.png"
        target.write_bytes(b"private content")
        self.image_out.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            self.call()
        self.assertEqual(target.read_bytes(), b"private content")

    def test_refuses_output_inside_git_checkout(self):
        git = self.fixture.root / "checkout"
        git.mkdir()
        (git / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "inside a Git checkout"):
            self.call(git / "private.png")
        self.assertFalse((git / "private.png").exists())

    def test_refuses_output_directory_symlink(self):
        alias = self.fixture.root / "linked"
        alias.symlink_to(self.fixture.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory must be real"):
            self.call(alias / "private.png")

    def test_allows_canonicalized_system_path_ancestor(self):
        # Emulates macOS's /var -> /private/var without trusting a direct
        # symlink destination directory.
        actual = self.fixture.root / "private-var"
        inner = actual / "tmp"
        inner.mkdir(parents=True)
        alias = self.fixture.root / "var"
        alias.symlink_to(actual, target_is_directory=True)
        destination = alias / "tmp" / "private-review.png"
        result = self.call(destination)
        self.assertEqual(result["private_review_groups"], 1)
        self.assertTrue(destination.exists())

    def test_canonicalized_ancestor_must_not_hide_git_checkout(self):
        actual = self.fixture.root / "hidden-repo"
        actual.mkdir()
        (actual / ".git").mkdir()
        nested = actual / "tmp"
        nested.mkdir()
        alias = self.fixture.root / "linked-repo"
        alias.symlink_to(actual, target_is_directory=True)
        destination = alias / "tmp" / "private-review.png"
        with self.assertRaisesRegex(ValueError, "inside a Git checkout"):
            self.call(destination)
        self.assertFalse(destination.exists())

    def test_refuses_relative_output(self):
        with self.assertRaisesRegex(ValueError, "absolute private"):
            self.call(Path("private-contact-sheet.png"))

    def test_refuses_wrong_file_extension(self):
        with self.assertRaisesRegex(ValueError, "absolute private PNG"):
            self.call(self.fixture.root / "preview.html")

    def test_capture_bundle_same_directory_rejected(self):
        f = self.fixture
        with patch(
            "tools.map02_private_dual_capture_rgb_repeatability.verify_chain",
            return_value={"screenshot_count": 3},
        ):
            with self.assertRaises(ValueError):
                render(
                    f.movie, f.plan, f.logs[0], f.folders[0],
                    f.logs[1], f.folders[0], self.image_out)
        self.assertFalse(self.image_out.exists())

    def test_source_capture_plan_and_audit_disagreement_rejected(self):
        with self.assertRaisesRegex(ValueError, "counts disagree"):
            self.call(count=2)
        self.assertFalse(self.image_out.exists())

    def test_corrupt_private_png_rejected_without_partial_output(self):
        self.fixture.image(1, "after").write_bytes(b"not a PNG")
        with self.assertRaises((ValueError, OSError)):
            self.call()
        self.assertFalse(self.image_out.exists())

    def test_cross_bundle_hardlinks_rejected_without_partial_output(self):
        a = self.fixture.image(0, "before")
        b = self.fixture.image(1, "before")
        b.unlink()
        os.link(a, b)
        with self.assertRaisesRegex(ValueError, "inode reused"):
            self.call()
        self.assertFalse(self.image_out.exists())

    def test_malformed_private_plan_missing_middle_fails_closed(self):
        lines = dual_fixtures.LINES.copy()
        lines[4] = "1,before,3250,neutral"
        self.fixture.plan.write_text("\n".join(lines) + "\n", encoding="ascii")
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.image_out.exists())

    def test_path_validation_does_not_create_an_output(self):
        result = _output_path_safely_uncreated(self.image_out)
        self.assertEqual(result, self.image_out)
        self.assertFalse(result.exists())


if __name__ == "__main__":
    unittest.main()
