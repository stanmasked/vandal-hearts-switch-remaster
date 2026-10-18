"""Synthetic private-layout preflight: no retail image or ELF required."""
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import tools.check_map02_private_launch_layout as layout
from tools.map02_local_capture_handoff import PLAN


class Map02PrivateLaunchLayoutTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="map02-launch-layout-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dirs = {role: self.root / role for role in layout.ROLES}
        for directory in self.dirs.values():
            directory.mkdir(mode=0o700)
        plan = self.dirs["handoff"] / PLAN
        plan.write_bytes(b'{"synthetic":"unverified plan"}\n')
        plan.chmod(0o600)

    def inspect(self, **overrides):
        dirs = dict(self.dirs)
        dirs.update(overrides)
        return layout.inspect_private_launch_layout(
            *(dirs[role] for role in layout.ROLES))

    def test_owner_private_empty_capture_layout_accepted(self):
        # Source evidence may already exist, but no capture output may.
        (self.dirs["source"] / "synthetic-input").write_bytes(b"not game data")
        with patch.object(Path, "read_bytes",
                          side_effect=AssertionError("must not read game bytes")):
            result = self.inspect()
        self.assertEqual(result["private_directory_roles_checked"], 7)
        self.assertEqual(result["capture_output_directories_empty"], 5)
        self.assertTrue(result["prelaunch_layout_ready"])
        for name in ("original_pc_elf_verified", "original_game_image_verified",
                     "original_gameplay_executed", "map02_frame_authenticated",
                     "private_game_bytes_read"):
            self.assertFalse(result[name])

    def test_rejects_nonempty_capture_folders(self):
        for role in layout.CAPTURE_ROLES:
            with self.subTest(role=role):
                junk = self.dirs[role] / "test-only"
                junk.write_bytes(b"synthetic")
                with self.assertRaisesRegex(ValueError, "not empty"):
                    self.inspect()
                junk.unlink()

    def test_rejects_symlink_and_nonprivate_directories(self):
        for role in layout.ROLES:
            with self.subTest(role=role):
                directory = self.dirs[role]
                directory.chmod(0o755)
                with self.assertRaisesRegex(ValueError, "owner-only"):
                    self.inspect()
                directory.chmod(0o700)
        alias = self.root / "alias"
        alias.symlink_to(self.dirs["preview"], target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.inspect(preview=alias)

    def test_rejects_duplicate_or_nested_folders(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.inspect(preview=self.dirs["cycle"])
        child = self.dirs["cycle"] / "nested"
        child.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.inspect(preview=child)

    def test_plan_must_be_unique_private_regular_file(self):
        path = self.dirs["handoff"] / PLAN
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.inspect()
        path.chmod(0o600)
        second = self.root / "plan-hardlink"
        os.link(path, second)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.inspect()
        second.unlink()
        path.unlink()
        path.symlink_to(second)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.inspect()

    def test_handoff_rejects_extra_files(self):
        extra = self.dirs["handoff"] / "unverified-receipt"
        extra.write_bytes(b"synthetic")
        with self.assertRaisesRegex(ValueError, "only its plan"):
            self.inspect()

    def test_detects_files_created_during_prelaunch_audit(self):
        original = layout._check_plan
        calls = [0]

        def add_late_file(directory):
            original(directory)
            calls[0] += 1
            if calls[0] == 1:
                (self.dirs["native"] / "late-file").write_bytes(b"synthetic")
        with patch.object(layout, "_check_plan", side_effect=add_late_file):
            with self.assertRaisesRegex(ValueError, "changed during audit"):
                self.inspect()

    def test_cli_never_discloses_private_original_path(self):
        private_path = "/private/user-owned-game/SLUS_004.47"
        error = ValueError("failed original input at " + private_path)
        argv = ["prelaunch-layout"] + [
            str(self.dirs[role]) for role in layout.ROLES]
        stderr = io.StringIO()
        with (patch("sys.argv", argv),
              patch.object(layout, "inspect_private_launch_layout",
                           side_effect=error),
              redirect_stderr(stderr)):
            with self.assertRaises(SystemExit) as exit_result:
                layout.main()
        self.assertEqual(exit_result.exception.code, 2)
        self.assertIn("prelaunch layout unavailable", stderr.getvalue())
        self.assertNotIn(private_path, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
