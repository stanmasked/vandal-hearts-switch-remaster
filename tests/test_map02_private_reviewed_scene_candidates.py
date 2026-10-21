"""Fabricated 2x1 RGB captures + private fake CSV. No owner BK2 or PS1."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_map02_private_dual_capture_rgb_repeatability as fake
from tools.map02_private_reviewed_scene_candidates import SCHEMA, shortlist, verify
from tools.map02_private_human_review_ledger import HEADER, write_private_new

POSITIONS = [(1, "before"), (1, "middle"), (1, "after")]
PLAN_SHA = "a" * 64
TRANSITION = [
    ("menu", "menu"),
    ("tactical_board", "tactical_board"),
    ("tactical_board", "tactical_board"),
]


class ReviewShortlistTests(unittest.TestCase):
    def setUp(self):
        self.sample = fake.PrivateDualRGBTests(
            "test_two_supplied_identical_pixel_sets_are_exact")
        self.sample.setUp()
        self.addCleanup(self.sample.doCleanups)
        self.labels = self.sample.root / "private-human-annotations.csv"
        self.output = self.sample.root / "owner-private-shortlist.json"
        self.write_labels(TRANSITION)

    def write_labels(self, sequence):
        with self.labels.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(HEADER)
            for (group, role), pair in zip(POSITIONS, sequence):
                writer.writerow((group, role, *pair))

    def call(self):
        x = self.sample
        with patch(
            "tools.map02_private_dual_capture_rgb_repeatability.verify_chain",
            return_value={"screenshot_count": 3},
        ) as checked:
            result = verify(
                x.movie, x.plan, x.logs[0], x.folders[0],
                x.logs[1], x.folders[1], self.labels,
            )
        self.assertEqual(checked.call_count, 2)
        return result

    def test_complete_agreed_visual_pattern_requires_game_state_witness(self):
        result = self.call()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["private_review_group_count"], 1)
        self.assertEqual(result["review_groups_requiring_game_state_witness"], 1)
        self.assertEqual(result["groups"][0]["state"], "requires_game_state_witness")
        self.assertTrue(result["groups"][0]["manual_transition_pattern"])
        for field in (
            "two_capture_sets_independently_authenticated",
            "independent_human_reviewers_authenticated",
            "input_to_video_alignment_verified",
            "original_ps1_game_authenticated",
            "actual_map02_start_authenticated",
            "game_state_or_gpu_vram_witness_available",
            "private_bk2_images_labels_or_frame_coordinates_uploaded",
        ):
            self.assertFalse(result[field])
        self.assertNotIn("3000", json.dumps(result))
        self.assertNotIn(str(self.sample.root), json.dumps(result))
        self.assertNotIn("png_file", json.dumps(result))

    def test_travel_before_tactical_middle_and_after_still_reviewable(self):
        self.write_labels([("travel", "travel"), *TRANSITION[1:]])
        self.assertEqual(self.call()["review_groups_requiring_game_state_witness"], 1)

    def test_tactical_before_middle_and_after_not_a_transition(self):
        self.write_labels([("tactical_board", "tactical_board"),
                           *TRANSITION[1:]])
        self.assertEqual(self.call()["groups"][0]["state"],
                         "not_candidate_in_selected_frames")

    def test_only_after_tactical_is_not_selected(self):
        self.write_labels([TRANSITION[0], ("dialogue", "dialogue"),
                           TRANSITION[2]])
        self.assertEqual(self.call()["review_groups_requiring_game_state_witness"], 0)

    def test_disagreeing_human_labels_never_auto_resolved(self):
        self.write_labels([
            ("menu", "menu"), ("tactical_board", "menu"),
            ("tactical_board", "tactical_board"),
        ])
        report = self.call()
        self.assertEqual(report["groups"][0]["state"], "human_labels_disagree")
        self.assertEqual(report["review_groups_with_label_conflicts"], 1)
        self.assertEqual(report["review_groups_requiring_game_state_witness"], 0)

    def test_unreviewed_label_suppresses_candidate(self):
        self.write_labels([TRANSITION[0], ("unreviewed", "tactical_board"),
                           TRANSITION[2]])
        self.assertEqual(self.call()["groups"][0]["state"],
                         "awaiting_manual_classification")

    def test_uncertain_label_suppresses_candidate(self):
        self.write_labels([("uncertain", "uncertain"), *TRANSITION[1:]])
        group = self.call()["groups"][0]
        self.assertEqual(group["state"], "awaiting_manual_classification")
        self.assertFalse(group["manual_transition_pattern"])

    def test_png_pixel_disagreement_overrides_matching_manual_labels(self):
        self.sample.image(1, "middle").write_bytes(
            fake.synthetic_png((250, 1, 10)))
        report = self.call()
        self.assertEqual(report["groups"][0]["state"], "requires_pixel_replay")
        self.assertEqual(report["review_groups_with_pixel_disagreements"], 1)
        self.assertEqual(report["review_groups_requiring_game_state_witness"], 0)

    def test_png_metadata_difference_does_not_count_as_pixel_disagreement(self):
        self.sample.image(1, "middle").write_bytes(fake.synthetic_png(
            fake.COLORS[1], metadata=True))
        self.assertEqual(self.call()["review_groups_requiring_game_state_witness"], 1)

    def test_manual_scene_pattern_with_same_before_middle_pixels_is_rejected(self):
        # Human category claims can disagree with actual decoded images:
        # before/menu and middle/board share EXACT pixels in both runs.
        for run in (0, 1):
            self.sample.image(run, "middle").write_bytes(
                fake.synthetic_png(fake.COLORS[0]))
        report = self.call()
        self.assertEqual(report["review_groups_requiring_game_state_witness"], 0)
        self.assertEqual(report["review_groups_without_intra_group_pixel_change"], 1)
        self.assertEqual(report["groups"][0]["state"],
                         "no_observed_intra_group_pixel_change")

    def test_manual_scene_pattern_with_same_before_after_pixels_is_rejected(self):
        for run in (0, 1):
            self.sample.image(run, "after").write_bytes(
                fake.synthetic_png(fake.COLORS[0]))
        self.assertEqual(self.call()["groups"][0]["state"],
                         "no_observed_intra_group_pixel_change")

    def test_cross_role_dimensions_must_match_for_visual_transition(self):
        for run in (0, 1):
            self.sample.image(run, "middle").write_bytes(
                fake.synthetic_png(fake.COLORS[1], width=3))
        with self.assertRaisesRegex(ValueError, "within-group frame dimensions"):
            self.call()

    def test_forged_or_missing_intra_group_rgb_evidence_rejected(self):
        proof = self.sample.call()
        with self.assertRaisesRegex(ValueError, "incomplete source-validated"):
            shortlist(POSITIONS, proof, self.labels, {1: "true"},
                      source_plan_sha256=PLAN_SHA,
                      source_capture_evidence_sha256=proof["source_capture_evidence_sha256"])
        with self.assertRaisesRegex(ValueError, "incomplete source-validated"):
            shortlist(POSITIONS, proof, self.labels, {},
                      source_plan_sha256=PLAN_SHA,
                      source_capture_evidence_sha256=proof["source_capture_evidence_sha256"])

    def test_corrupt_png_blocks_report_generation(self):
        self.sample.image(1, "after").write_bytes(b"not an image")
        with self.assertRaises((OSError, ValueError)):
            self.call()

    def test_reused_screenshot_inode_blocks_report_generation(self):
        import os
        a = self.sample.image(0, "before")
        b = self.sample.image(1, "before")
        b.unlink()
        os.link(a, b)
        with self.assertRaises(ValueError):
            self.call()

    def test_malformed_duplicate_or_missing_annotation_rejected(self):
        with self.labels.open("a", encoding="utf-8") as fp:
            fp.write("1,before,menu,menu\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.call()

    def test_spreadsheet_formula_cannot_become_category(self):
        self.write_labels([("=CMD()", "menu"), *TRANSITION[1:]])
        with self.assertRaisesRegex(ValueError, "invalid manually"):
            self.call()

    def test_missing_row_cannot_be_accepted(self):
        self.write_labels(TRANSITION[:2])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.call()

    def test_extra_or_duplicate_cross_capture_rgb_receipt_rejected(self):
        audit = self.sample.call()
        row = audit["matches_and_differences_by_review_position"][0]
        audit["matches_and_differences_by_review_position"].append(dict(row))
        with self.assertRaisesRegex(ValueError, "source RGB witness"):
            shortlist(POSITIONS, audit, self.labels, {1: True},
                      source_plan_sha256=PLAN_SHA,
                      source_capture_evidence_sha256=audit["source_capture_evidence_sha256"])

    def test_forged_source_game_proof_is_rejected(self):
        audit = self.sample.call()
        audit["map02_start_frame_identified"] = True
        with self.assertRaisesRegex(ValueError, "source RGB witness"):
            shortlist(POSITIONS, audit, self.labels, {1: True},
                      source_plan_sha256=PLAN_SHA,
                      source_capture_evidence_sha256=audit["source_capture_evidence_sha256"])

    def test_non_boolean_rgb_agreement_rejected(self):
        audit = self.sample.call()
        audit["matches_and_differences_by_review_position"][0][
            "same_decoded_rgb_pixels"] = "true"
        with self.assertRaisesRegex(ValueError, "cross-capture RGB"):
            shortlist(POSITIONS, audit, self.labels, {1: True}, source_plan_sha256=PLAN_SHA)

    def test_report_binds_exact_capture_plan_sha256(self):
        report = self.call()
        self.assertEqual(
            report["source_plan_sha256"],
            hashlib.sha256(self.sample.plan.read_bytes()).hexdigest(),
        )
        self.assertNotIn(self.sample.plan.read_text(encoding="ascii"),
                         json.dumps(report))

    def test_report_binds_exact_capture_evidence_digest(self):
        report = self.call()
        source = self.sample.call()
        self.assertEqual(
            report["source_capture_evidence_sha256"],
            source["source_capture_evidence_sha256"],
        )
        self.assertNotIn(str(self.sample.root), json.dumps(report))
        self.assertNotIn("3000", json.dumps(report))

    def test_capture_plan_mutation_during_audit_fails_closed(self):
        def mutate_plan(*_args, **_kwargs):
            self.sample.plan.write_text(
                self.sample.plan.read_text(encoding="ascii") + "# changed\n",
                encoding="ascii",
            )
            return {1: True}

        with patch(
            "tools.map02_private_reviewed_scene_candidates._intra_group_visual_changes",
            side_effect=mutate_plan,
        ):
            with self.assertRaisesRegex(ValueError, "changed during audit"):
                self.call()

    def test_private_json_output_is_owner_only_and_cannot_be_overwritten(self):
        report = self.call()
        write_private_new(
            self.output, json.dumps(report, sort_keys=True) + "\n", ".json")
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        saved = json.loads(self.output.read_text())
        self.assertEqual(saved["groups"][0]["state"], "requires_game_state_witness")
        with self.assertRaisesRegex(ValueError, "already exists"):
            write_private_new(self.output, "overwrite", ".json")


if __name__ == "__main__":
    unittest.main()
