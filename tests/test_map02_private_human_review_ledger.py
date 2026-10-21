"""Invented capture metadata only; all original BK2/PS1/PNG evidence private."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_map02_private_dual_capture_rgb_repeatability as invented
from tools.map02_private_human_review_ledger import (
    SCHEMA, HEADER, _source_positions, checked_positions, evaluate, prepare,
    safe_private_new_path, write_private_new,
)


class HumanReviewLedgerTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.positions = [(1, "before"), (1, "middle"), (1, "after")]
        self.labels = self.root / "manual-observations.csv"
        self.result = self.root / "review-report.json"

    def _contents(self, records):
        with self.labels.open("w", newline="", encoding="utf-8") as target:
            writer = csv.writer(target)
            writer.writerow(HEADER)
            writer.writerows(records)

    def _filled(self, *values):
        assert len(values) == len(self.positions)
        self._contents([
            (group, role, labels[0], labels[1])
            for (group, role), labels in zip(self.positions, values)
        ])
        return evaluate(self.positions, self.labels)

    def test_owner_only_template_and_conservative_flags(self):
        report = prepare(self.positions, self.labels)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["review_positions_prepared"], 3)
        self.assertFalse(report["map02_scene_authenticated"])
        self.assertEqual(self.labels.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.labels.read_text().splitlines()), 4)
        reviewed = evaluate(self.positions, self.labels)
        self.assertEqual(reviewed["uncertain_or_unreviewed_position_pairs"], 3)
        self.assertEqual(reviewed["fully_categorized_position_pairs"], 0)
        self.assertFalse(reviewed["map02_scene_authenticated"])
        self.assertNotIn(str(self.root), json.dumps(reviewed))

    def test_matching_manual_board_observations_not_map02_proof(self):
        result = self._filled(("menu", "menu"),
                              ("tactical_board", "tactical_board"),
                              ("transition", "uncertain"))
        self.assertEqual(result["matching_human_label_pairs"], 2)
        self.assertEqual(result["manual_tactical_board_label_pairs"], 1)
        self.assertEqual(result["uncertain_or_unreviewed_position_pairs"], 1)
        for field in (
            "independent_human_reviewers_authenticated",
            "two_real_ps1_emulator_runs_authenticated",
            "actual_ps1_game_disc_authenticated",
            "input_to_video_frame_offset_authenticated",
            "map02_scene_authenticated",
            "gpu_vram_parity_authenticated",
            "private_observations_uploaded",
        ):
            self.assertFalse(result[field])

    def test_conflicting_human_labels_are_counted_not_silently_resolved(self):
        result = self._filled(("menu", "dialogue"),
                              ("tactical_board", "menu"),
                              ("travel", "travel"))
        self.assertEqual(result["conflicting_human_label_pairs"], 2)
        self.assertEqual(result["matching_human_label_pairs"], 1)
        self.assertEqual(result["manual_tactical_board_label_pairs"], 0)

    def test_uncertain_and_unreviewed_never_count_as_agreement(self):
        result = self._filled(("uncertain", "uncertain"),
                              ("unreviewed", "unreviewed"),
                              ("travel", "unreviewed"))
        self.assertEqual(result["uncertain_or_unreviewed_position_pairs"], 3)
        self.assertEqual(result["matching_human_label_pairs"], 0)

    def test_rejects_missing_position(self):
        self._contents([(1, "before", "menu", "menu")])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            evaluate(self.positions, self.labels)

    def test_rejects_extra_or_duplicate_position(self):
        self._contents([(1, "before", "menu", "menu"),
                        (1, "before", "menu", "menu"),
                        (1, "middle", "other", "other"),
                        (1, "after", "other", "other")])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate(self.positions, self.labels)

    def test_refuses_spreadsheet_formula_injection(self):
        self._contents([(1, "before", "=HYPERLINK('bad')", "menu"),
                        (1, "middle", "menu", "menu"),
                        (1, "after", "menu", "menu")])
        with self.assertRaisesRegex(ValueError, "invalid manually"):
            evaluate(self.positions, self.labels)

    def test_bad_csv_structure_and_extra_notes_rejected(self):
        self.labels.write_text(
            "review_group,frame_role,run_1_label,run_2_label,notes\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "header"):
            evaluate(self.positions, self.labels)

    def test_symlinked_private_annotations_rejected(self):
        original = self.root / "source.csv"
        original.write_text("some local private text", encoding="utf-8")
        self.labels.symlink_to(original)
        with self.assertRaises(ValueError):
            evaluate(self.positions, self.labels)

    def test_existing_report_file_not_overwritten(self):
        self.result.write_text("keep this secret", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            write_private_new(self.result, "overwrite", ".json")
        self.assertEqual(self.result.read_text(), "keep this secret")

    def test_output_symlink_rejected(self):
        original = self.root / "other.csv"
        original.write_text("keep this secret", encoding="utf-8")
        self.labels.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.positions, self.labels)
        self.assertEqual(original.read_text(), "keep this secret")

    def test_output_inside_git_tree_rejected(self):
        checkout = self.root / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "inside Git"):
            prepare(self.positions, checkout / "observation.csv")
        self.assertFalse((checkout / "observation.csv").exists())

    def test_symlinked_system_ancestor_permitted_but_resolved_git_guarded(self):
        actual = self.root / "private-var"
        sub = actual / "tmp"
        sub.mkdir(parents=True)
        alias = self.root / "var"
        alias.symlink_to(actual, target_is_directory=True)
        output = alias / "tmp" / "owner.csv"
        prepare(self.positions, output)
        self.assertTrue(output.exists())
        (actual / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "inside Git"):
            safe_private_new_path(alias / "tmp" / "blocked.csv", ".csv")

    def test_refuses_direct_symlink_output_directory(self):
        actual = self.root / "real"
        actual.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directly symlinked"):
            prepare(self.positions, alias / "owner.csv")

    def test_mock_verified_source_chain_and_canonical_role_order(self):
        sample = invented.PrivateDualRGBTests(
            "test_two_supplied_identical_pixel_sets_are_exact")
        sample.setUp()
        self.addCleanup(sample.doCleanups)
        with patch(
            "tools.map02_private_dual_capture_rgb_repeatability.verify_chain",
            return_value={"screenshot_count": 3},
        ) as checked:
            actual = _source_positions(
                sample.movie, sample.plan, sample.logs[0], sample.folders[0],
                sample.logs[1], sample.folders[1],
                minimum=200, maximum=1000, after=1663, before=933949,
            )
        self.assertEqual(checked.call_count, 2)
        self.assertEqual(actual, self.positions)

    def test_bad_provenance_fails_closed(self):
        proof = {
            "both_source_bk2_capture_chains_passed_integrity_audit": True,
            "no_local_capture_inode_reused": True,
            "map02_start_frame_identified": True,
            "independent_replay_executions_authenticated": False,
            "compared_screenshot_positions": 3,
        }
        with self.assertRaisesRegex(ValueError, "conservative provenance"):
            checked_positions(self.root / "fake-plan", proof)


if __name__ == "__main__":
    unittest.main()
