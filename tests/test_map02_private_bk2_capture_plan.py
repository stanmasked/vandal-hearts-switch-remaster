"""Fake planner output only; no original game or private BK2 in tests."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_bk2_capture_plan import (
    plan_lines, write_private_plan,
)


def window(before=3000, middle=3250, after=3500):
    return {
        "suggested_local_review_input_indices_zero_based":
            [before, middle, after],
    }


class PrivatePlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bk2 = self.root / "fake.bk2"
        self.bk2.write_bytes(b"fictional BK2 placeholder; never a real movie")
        self.plan = self.root / "capture-plan.txt"

    def mock(self, windows):
        return patch("tools.map02_private_bk2_capture_plan.inspect_movie",
                     return_value={"review_windows": windows})

    def test_valid_private_plan_has_three_ordered_rows_and_expected_button_states(self):
        with self.mock([window()]):
            lines = plan_lines(self.bk2, limit=1)
        self.assertEqual(lines, [
            "VH_MAP02_CAPTURE_PLAN_V1",
            "movie_frames=933949",
            "capture_count=3",
            "1,before,3000,held",
            "1,middle,3250,neutral",
            "1,after,3500,held",
        ])

    def test_multiple_ranked_groups_are_sorted_by_frame_for_one_pass_replay(self):
        with self.mock([window(6000, 6200, 6300), window(3000, 3200, 3300)]):
            lines = plan_lines(self.bk2, limit=2)
        self.assertEqual(lines[3:], [
            "2,before,3000,held", "2,middle,3200,neutral",
            "2,after,3300,held",
            "1,before,6000,held", "1,middle,6200,neutral",
            "1,after,6300,held",
        ])

    def test_creation_is_private_mode_0600_and_no_input_names_leak(self):
        with self.mock([window()]):
            count = write_private_plan(self.bk2, self.plan, limit=1)
        self.assertEqual(count, 3)
        self.assertEqual(self.plan.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.bk2), self.plan.read_text())

    def test_no_qualified_windows_refuses_output(self):
        with self.mock([]), self.assertRaises(ValueError):
            write_private_plan(self.bk2, self.plan)
        self.assertFalse(self.plan.exists())

    def test_output_collision_refuses_overwrite(self):
        self.plan.write_text("DO NOT OVERWRITE")
        with self.mock([window()]), self.assertRaises(ValueError):
            write_private_plan(self.bk2, self.plan)
        self.assertEqual(self.plan.read_text(), "DO NOT OVERWRITE")

    def test_existing_symlink_output_refused(self):
        victim = self.root / "secret"
        victim.write_text("unchanged")
        self.plan.symlink_to(victim)
        with self.mock([window()]), self.assertRaises(ValueError):
            write_private_plan(self.bk2, self.plan)
        self.assertEqual(victim.read_text(), "unchanged")

    def test_output_inside_checkout_refused_before_source_read(self):
        (self.root / ".git").mkdir()
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / "fake.bk2"
            source.write_bytes(b"fictional source")
            with self.mock([window()]) as inspect, self.assertRaises(ValueError):
                write_private_plan(source, self.plan)
            inspect.assert_not_called()
        self.assertFalse(self.plan.exists())

    def test_source_inside_checkout_refused_before_inspection(self):
        (self.root / ".git").mkdir()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "private-plan.txt"
            with self.mock([window()]) as inspect, self.assertRaises(ValueError):
                write_private_plan(self.bk2, target)
            inspect.assert_not_called()
        self.assertFalse(target.exists())

    def test_output_through_symlink_into_checkout_refused(self):
        checkout = self.root / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        alias = self.root / "checkout-alias"
        alias.symlink_to(checkout, target_is_directory=True)
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / "fake.bk2"
            source.write_bytes(b"fictional source")
            target = alias / "capture-plan.txt"
            with self.mock([window()]) as inspect, self.assertRaises(ValueError):
                write_private_plan(source, target)
            inspect.assert_not_called()
        self.assertFalse((checkout / "capture-plan.txt").exists())

    def test_relative_output_refused(self):
        with self.mock([window()]), self.assertRaises(ValueError):
            write_private_plan(self.bk2, Path("relative-plan.txt"))

    def test_duplicate_frame_positions_refused(self):
        with self.mock([window(), window(3000, 3450, 3600)]), self.assertRaises(ValueError):
            plan_lines(self.bk2, limit=2)

    def test_unsorted_triplet_refused(self):
        with self.mock([window(3000, 3500, 3200)]), self.assertRaises(ValueError):
            plan_lines(self.bk2)

    def test_earliest_allowed_private_capture_at_input_1663(self):
        with self.mock([window(1663, 1765, 1865)]):
            rows = plan_lines(self.bk2, limit=1)
        self.assertEqual(rows[3], "1,before,1663,held")

    def test_capture_before_1663_refused(self):
        with self.mock([window(1662, 1765, 1865)]), self.assertRaises(ValueError):
            plan_lines(self.bk2, limit=1)

    def test_invalid_capture_limit_refused(self):
        for limit in (0, 11, True, 1.1):
            with self.subTest(limit=limit), self.mock([window()]), self.assertRaises(ValueError):
                plan_lines(self.bk2, limit=limit)

    def test_movie_end_boundary_refused(self):
        with self.mock([window(933900, 933920, 933949)]), self.assertRaises(ValueError):
            plan_lines(self.bk2)

    def test_all_frame_roles_are_selected_from_source_not_guessed(self):
        with self.mock([window(3100, 3300, 3500)]) as mocked:
            plan_lines(self.bk2, limit=1, minimum=240, maximum=1200, after=2000, before=5000)
        self.assertEqual(mocked.call_args.kwargs, {
            "minimum": 240, "maximum": 1200, "limit": 1,
            "after": 2000, "before": 5000,
        })


if __name__ == "__main__":
    unittest.main()
