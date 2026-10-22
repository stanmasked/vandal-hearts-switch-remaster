"""Synthetic fixtures for owner-private Windows DACL preflight; no assets."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.map02_windows_private_output_acl import (
    SCRIPT, SUCCESS, require_windows_private_output,
)


class WindowsPrivateOutputAclTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.folder = Path(t.name)

    def test_posix_requires_no_powershell(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run") as proc:
            self.assertIsNone(require_windows_private_output(self.folder, platform="posix"))
            proc.assert_not_called()

    def test_matching_windows_acl_signal_is_accepted(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run",
                   return_value=Mock(returncode=0, stdout=(SUCCESS + "\n").encode())) as proc:
            self.assertIsNone(require_windows_private_output(self.folder, platform="nt"))
        params = proc.call_args
        self.assertEqual(params.args[0][:3],
                         ["powershell.exe", "-NoProfile", "-NonInteractive"])
        self.assertEqual(params.args[0][-2:], ["-Directory", str(self.folder)])
        self.assertIs(params.kwargs["shell"], False)
        self.assertIs(params.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(params.kwargs["timeout"], 30)

    def test_acl_failure_rejected(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run",
                   return_value=Mock(returncode=1, stdout=b"")):
            with self.assertRaisesRegex(ValueError, "not owner-only"):
                require_windows_private_output(self.folder, platform="nt")

    def test_unexpected_success_output_rejected(self):
        for output in (b"", b"OK\n", SUCCESS.encode() + b"\nextra\n"):
            with self.subTest(output=output[:12]):
                with patch("tools.map02_windows_private_output_acl.subprocess.run",
                           return_value=Mock(returncode=0, stdout=output)):
                    with self.assertRaisesRegex(ValueError, "not owner-only"):
                        require_windows_private_output(self.folder, platform="nt")

    def test_spawn_failure_is_generic_and_no_paths(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run",
                   side_effect=OSError("invented secret private path")):
            with self.assertRaises(ValueError) as raised:
                require_windows_private_output(self.folder, platform="nt")
            self.assertNotIn(str(self.folder), str(raised.exception))
            self.assertNotIn("secret", str(raised.exception))

    def test_timeout_failure_redacted(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("secret", 30)):
            with self.assertRaisesRegex(ValueError, "could not be verified"):
                require_windows_private_output(self.folder, platform="nt")

    def test_relative_folder_rejected_without_process(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run") as proc:
            with self.assertRaisesRegex(ValueError, "absolute ordinary directory"):
                require_windows_private_output(Path("relative-folder"), platform="nt")
            proc.assert_not_called()

    def test_symlink_folder_rejected(self):
        link = self.folder / "alias"
        link.symlink_to(self.folder, target_is_directory=True)
        with patch("tools.map02_windows_private_output_acl.subprocess.run") as proc:
            with self.assertRaisesRegex(ValueError, "absolute ordinary directory"):
                require_windows_private_output(link, platform="nt")
            proc.assert_not_called()

    def test_missing_directory_rejected(self):
        with patch("tools.map02_windows_private_output_acl.subprocess.run") as proc:
            with self.assertRaisesRegex(ValueError, "absolute ordinary directory"):
                require_windows_private_output(self.folder / "not-here", platform="nt")
            proc.assert_not_called()

    def test_windows_script_is_public_source_not_a_game_asset(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(SCRIPT.name.endswith(".ps1"))


if __name__ == "__main__":
    unittest.main()
