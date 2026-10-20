"""Asset-free regressions for staging user-owned Drive files on macOS."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import stage_map02_private_disc as staging
from tools.stage_map02_private_disc import (
    BIN_NAME, CUE_NAME, STAGE_NAME, SECTOR_BYTES, stage_disc,
)


class PrivateLocalCopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mount = self.root / "mounted-drive"
        self.mount.mkdir()
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.bin = self.mount / BIN_NAME
        self.cue = self.mount / CUE_NAME
        self.data = b"synthetic-only-not-a-game-sector".ljust(SECTOR_BYTES, b"X") * 4
        self.bin.write_bytes(self.data)
        self.bin.chmod(0o644)  # Simulate a Drive-managed source we must not chmod.
        self.cue.write_bytes(
            (f'FILE "{BIN_NAME}" BINARY\r\n'
             '  TRACK 01 MODE2/2352\r\n'
             '    INDEX 01 00:00:00\r\n').encode("ascii")
        )
        self.cue.chmod(0o644)

    def run_stage(self, **kwargs):
        return stage_disc(self.bin, self.cue, self.private,
                          expected_bytes=len(self.data), **kwargs)

    def test_successful_private_copy_keeps_mounted_original_unchanged(self):
        original_modes = (self.bin.stat().st_mode & 0o777,
                          self.cue.stat().st_mode & 0o777)
        original_bytes = (self.bin.read_bytes(), self.cue.read_bytes())
        result, digest = self.run_stage()
        self.assertEqual(result, self.private / STAGE_NAME)
        self.assertEqual(digest, hashlib.sha256(self.data).hexdigest())
        self.assertEqual((self.bin.read_bytes(), self.cue.read_bytes()),
                         original_bytes)
        self.assertEqual((self.bin.stat().st_mode & 0o777,
                          self.cue.stat().st_mode & 0o777), original_modes)
        self.assertEqual((result / BIN_NAME).read_bytes(), self.data)
        self.assertEqual((result / CUE_NAME).read_bytes(), original_bytes[1])
        self.assertEqual((result / BIN_NAME).stat().st_mode & 0o777, 0o600)
        self.assertEqual((result / CUE_NAME).stat().st_mode & 0o777, 0o600)
        self.assertEqual((result / "receipt").stat().st_mode & 0o777, 0o700)
        self.assertEqual(sorted(p.name for p in result.iterdir()),
                         sorted((BIN_NAME, CUE_NAME, "receipt")))
        self.assertEqual(list(self.private.iterdir()), [result])

    def test_wrong_size_does_not_publish_any_copy(self):
        with self.assertRaisesRegex(ValueError, "size or sector"):
            stage_disc(self.bin, self.cue, self.private)
        self.assertEqual(list(self.private.iterdir()), [])

    def test_invalid_cue_rejected_before_copy(self):
        self.cue.write_bytes(b'FILE "wrong.bin" BINARY\n')
        with self.assertRaisesRegex(ValueError, "mounted CUE"):
            self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])

    def test_existing_final_path_is_never_overwritten(self):
        existing = self.private / STAGE_NAME
        existing.mkdir()
        marker = existing / "owner-data.txt"
        marker.write_text("do not touch")
        with self.assertRaises(FileExistsError):
            self.run_stage()
        self.assertEqual(marker.read_text(), "do not touch")
        self.assertEqual(sorted(self.private.iterdir()), [existing])

    def test_rejects_symlinked_mounted_source(self):
        real_file = self.mount / "original-not-exposed.bin"
        self.bin.rename(real_file)
        self.bin.symlink_to(real_file)
        with self.assertRaises((OSError, ValueError)):
            self.run_stage()
        self.assertTrue(real_file.exists())
        self.assertEqual(list(self.private.iterdir()), [])

    def test_requires_owner_only_private_destination_parent(self):
        self.private.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.private.chmod(0o700)

    def test_failed_private_copy_removes_pending_name(self):
        with patch("tools.stage_map02_private_disc._copy_image",
                   side_effect=OSError("injected disk-full")):
            with self.assertRaisesRegex(OSError, "disk-full"):
                self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_rename_failure_removes_pending_and_preserves_source(self):
        with patch("tools.stage_map02_private_disc._rename_no_replace",
                   side_effect=OSError("injected exclusive rename failure")):
            with self.assertRaisesRegex(OSError, "exclusive rename failure"):
                self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_race_existing_empty_directory_is_not_overwritten(self):
        real_rename = staging._rename_no_replace
        final = self.private / STAGE_NAME

        def create_competing_directory(parentfd, pending, name):
            self.assertEqual(name, STAGE_NAME)
            self.assertFalse(final.exists())
            # Simulate another owner process creating an empty directory after
            # the first preflight and directly before exclusive rename.
            os.mkdir(name, 0o700, dir_fd=parentfd)
            return real_rename(parentfd, pending, name)

        with patch("tools.stage_map02_private_disc._rename_no_replace",
                   side_effect=create_competing_directory):
            with self.assertRaises(FileExistsError):
                self.run_stage()
        self.assertTrue(final.is_dir())
        self.assertEqual(list(self.private.iterdir()), [final])
        self.assertEqual(list(final.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_race_symlink_destination_is_not_replaced(self):
        real_rename = staging._rename_no_replace
        target = self.root / "unrelated-real-directory"
        target.mkdir()
        sentinel = target / "untouched.txt"
        sentinel.write_text("untouched")
        final = self.private / STAGE_NAME

        def create_competing_symlink(parentfd, pending, name):
            os.symlink(target, name, dir_fd=parentfd)
            return real_rename(parentfd, pending, name)

        with patch("tools.stage_map02_private_disc._rename_no_replace",
                   side_effect=create_competing_symlink):
            with self.assertRaises(FileExistsError):
                self.run_stage()
        self.assertTrue(final.is_symlink())
        # Darwin canonically maps /var to /private/var in resolved paths.
        self.assertEqual(final.resolve(), target.resolve())
        self.assertEqual(sentinel.read_text(), "untouched")
        self.assertEqual(list(self.private.iterdir()), [final])

    def test_atomic_no_replace_does_not_fall_back_to_plain_rename(self):
        with patch("tools.stage_map02_private_disc._rename_no_replace",
                   side_effect=OSError("exclusive operation unavailable")):
            with self.assertRaisesRegex(OSError, "exclusive operation unavailable"):
                self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_rejects_corrupted_staged_bin_before_atomic_rename(self):
        real_copy = staging._copy_image

        def damage_after_copy(source, stagedfd, **kwargs):
            original_sha = real_copy(source, stagedfd, **kwargs)
            fd = os.open(BIN_NAME, os.O_RDWR, dir_fd=stagedfd)
            try:
                os.lseek(fd, 30, os.SEEK_SET)
                os.write(fd, b"!")
                os.fsync(fd)
            finally:
                os.close(fd)
            return original_sha

        with patch("tools.stage_map02_private_disc._copy_image",
                   side_effect=damage_after_copy):
            with self.assertRaisesRegex(ValueError, "staged BIN sha256 mismatch"):
                self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_rejects_truncated_staged_bin_before_atomic_rename(self):
        real_copy = staging._copy_image

        def truncate_after_copy(source, stagedfd, **kwargs):
            original_sha = real_copy(source, stagedfd, **kwargs)
            fd = os.open(BIN_NAME, os.O_RDWR, dir_fd=stagedfd)
            try:
                os.ftruncate(fd, len(self.data) - 1)
            finally:
                os.close(fd)
            return original_sha

        with patch("tools.stage_map02_private_disc._copy_image",
                   side_effect=truncate_after_copy):
            with self.assertRaisesRegex(ValueError, "staged file metadata mismatch"):
                self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_rejects_modified_staged_cue_before_atomic_rename(self):
        real_verify = staging._verify_staged_copy

        def tamper_cue(stagedfd, expected_sha, expected_bytes, cue_bytes):
            fd = os.open(CUE_NAME, os.O_RDWR, dir_fd=stagedfd)
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"X")
            finally:
                os.close(fd)
            return real_verify(stagedfd, expected_sha, expected_bytes, cue_bytes)

        with patch("tools.stage_map02_private_disc._verify_staged_copy",
                   side_effect=tamper_cue):
            with self.assertRaisesRegex(ValueError, "staged CUE byte mismatch"):
                self.run_stage()
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.cue.read_bytes().startswith(b"FILE "), True)

    def test_rejects_staging_inside_original_mounted_folder(self):
        unsafe = self.mount / "private-not-actually-local"
        unsafe.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "outside mounted source folder"):
            stage_disc(self.bin, self.cue, unsafe, expected_bytes=len(self.data))
        self.assertEqual(list(unsafe.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_rejects_macos_cloudstorage_destination(self):
        cloud = self.root / "Library" / "CloudStorage" / "GoogleDrive-example"
        cloud.mkdir(mode=0o700, parents=True)
        with patch.object(staging.Path, "home", return_value=self.root):
            with self.assertRaisesRegex(ValueError, "macOS CloudStorage"):
                stage_disc(self.bin, self.cue, cloud, expected_bytes=len(self.data))
        self.assertEqual(list(cloud.iterdir()), [])
        self.assertEqual(self.bin.read_bytes(), self.data)

    def test_outside_source_and_cloudstorage_still_allowed(self):
        folder, digest = self.run_stage()
        self.assertEqual(folder, self.private / STAGE_NAME)
        self.assertEqual(digest, hashlib.sha256(self.data).hexdigest())

    def test_rejects_unsafe_destination_name(self):
        for label in ("..", "../external", ".hidden", "f" * 90):
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.run_stage(stage_name=label)
        self.assertEqual(list(self.private.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
