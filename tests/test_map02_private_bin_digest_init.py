"""Synthetic-only checks for local BIN digest reference creation.

No retail disc, screenshots, BK2, EmuHawk or BIOS are read in CI.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_bin_digest_init import (
    create_private_reference, main,
)
from tools.map02_private_disc_movie_preflight import read_private_full_bin_sha256

PREFIX = "tools.map02_private_bin_digest_init."


class PrivateDigestBootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "owner-only"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.bin = self.private / "fictional.bin"
        self.bin.write_bytes(b"CI_FICTIONAL_SECTORLESS_IMAGE" * 333)
        self.cue = self.private / "fictional.cue"
        self.cue.write_text(
            'FILE "fictional.bin" BINARY\n'
            '  TRACK 01 MODE2/2352\n'
            '    INDEX 01 00:00:00\n', encoding="ascii",
        )
        self.reference = self.private / "owner-disc.sha256"

    def run_bootstrap(self, *, expected_profile=(True, True, True, None),
                      rechecks=None):
        identity = ("fictional-cue", "fictional-image")
        with patch(PREFIX + "_disc_source_snapshot", return_value=identity), \
             patch(PREFIX + "_require_disc_unchanged",
                   side_effect=rechecks) as stable, \
             patch(PREFIX + "_disc_profile",
                   return_value=expected_profile), \
             patch(PREFIX + "EXPECTED_BIN_BYTES", self.bin.stat().st_size):
            return create_private_reference(self.cue, self.reference), stable

    def test_creates_new_private_digest_and_hides_value_from_report(self):
        report, stable = self.run_bootstrap()
        self.assertEqual(stable.call_count, 2)
        expected = hashlib.sha256(self.bin.read_bytes()).hexdigest()
        self.assertEqual(read_private_full_bin_sha256(self.reference), expected)
        self.assertEqual(self.reference.read_text(encoding="ascii"), expected + "\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.reference.stat().st_mode), 0o600)
        self.assertTrue(report["full_bin_sha256_streamed"])
        self.assertTrue(report["private_reference_readback_checked"])
        self.assertFalse(report["independently_trusted_disc_provenance_authenticated"])
        self.assertFalse(report["movie_replay_or_map02_scene_authenticated"])
        self.assertNotIn(expected, json.dumps(report))
        self.assertNotIn(str(self.private), json.dumps(report))
        self.assertNotIn(self.bin.name, json.dumps(report))
        self.assertNotIn(self.cue.name, json.dumps(report))

    def test_existing_reference_is_never_overwritten(self):
        self.reference.write_text("existing-private-reference", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "new absolute path"):
            self.run_bootstrap()
        self.assertEqual(self.reference.read_text(), "existing-private-reference")

    def test_output_symlink_is_rejected_without_changing_target(self):
        target = self.private / "target.txt"
        target.write_text("unchanged", encoding="utf-8")
        self.reference.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "new absolute path"):
            self.run_bootstrap()
        self.assertEqual(target.read_text(), "unchanged")

    def test_destination_must_be_absolute(self):
        with self.assertRaisesRegex(ValueError, "new absolute path"):
            create_private_reference(self.cue, Path("owner-disc.sha256"))

    def test_rejects_public_or_wrong_owner_directory(self):
        if os.name == "nt":
            self.skipTest("POSIX owner/private mode checks")
        self.private.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.run_bootstrap()
        self.assertFalse(self.reference.exists())

    def test_rejects_output_inside_git_worktree(self):
        (self.private / ".git").write_text("gitdir: /private/example", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "outside Git"):
            self.run_bootstrap()
        self.assertFalse(self.reference.exists())

    def test_rejects_symlinked_output_parent(self):
        alias = self.root / "alias"
        alias.symlink_to(self.private, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "real directory"):
            create_private_reference(self.cue, alias / "target.sha256")

    def test_rejects_wrong_volume_resource_or_image_size(self):
        for profile in (
            (False, True, True, None),
            (True, False, True, None),
            (True, True, False, None),
        ):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, "audited MAP02"):
                    self.run_bootstrap(expected_profile=profile)
                self.assertFalse(self.reference.exists())

    def test_changed_source_before_reference_write_leaves_no_file(self):
        with self.assertRaisesRegex(ValueError, "fictional changed"):
            self.run_bootstrap(rechecks=[
                ValueError("fictional changed before reference creation"),
            ])
        self.assertFalse(self.reference.exists())

    def test_changed_source_after_reference_write_removes_new_file(self):
        with self.assertRaisesRegex(ValueError, "fictional changed"):
            self.run_bootstrap(rechecks=[
                None, ValueError("fictional changed after creation"),
            ])
        self.assertFalse(self.reference.exists())

    def test_reference_readback_failure_removes_new_file(self):
        with patch(PREFIX + "read_private_full_bin_sha256",
                   side_effect=ValueError("readback failure")):
            with self.assertRaisesRegex(ValueError, "readback failure"):
                self.run_bootstrap()
        self.assertFalse(self.reference.exists())

    def test_no_collision_overwrite_on_exclusive_open(self):
        real_open = os.open
        def collision(path, flags, mode=0o777):
            if str(path) == str(self.reference):
                raise FileExistsError("fictional exclusive-create collision")
            return real_open(path, flags, mode)
        with patch(PREFIX + "os.open", side_effect=collision):
            with self.assertRaisesRegex(FileExistsError, "exclusive-create"):
                self.run_bootstrap()
        self.assertFalse(self.reference.exists())

    def test_changed_source_during_streaming_leaves_no_file(self):
        with patch(PREFIX + "_assert_stable",
                   side_effect=ValueError("fictional BIN changed")):
            with self.assertRaisesRegex(ValueError, "fictional BIN changed"):
                self.run_bootstrap()
        self.assertFalse(self.reference.exists())

    def test_cli_report_is_redacted(self):
        report, _ = self.run_bootstrap()
        self.reference.unlink()
        with patch(PREFIX + "create_private_reference", return_value=report), \
             patch.object(sys, "argv", [
                 "digest-init", str(self.cue), str(self.reference),
             ]):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertNotIn(str(self.cue), stdout.getvalue())
        self.assertNotIn(str(self.reference), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
