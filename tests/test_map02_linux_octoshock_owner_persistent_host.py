"""Stage551 simulated mount tests, no actual owner machine or media."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest

from tools.map02_linux_octoshock.owner_persistent_host import (
    MINIMUM_PREPARE_BYTES, PersistentHostError, verify_persistent_private_host,
)


def mock_mount(fs="ext4"):
    return f"1 0 0:1 / / rw,relatime - {fs} /dev/fake rw\n"


class PersistentHostTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.root.chmod(0o700)

    def audit(self, *, path=None, fs="ext4", env=None, free=None,
              mountinfo=None, prefixes=()):
        candidate = self.root if path is None else path
        # Fake rows use recognizable device tokens, but the identity
        # gate requires the test mount to match the kernel's real st_dev.
        observed = candidate.stat().st_dev
        major_minor = f"{os.major(observed)}:{os.minor(observed)}"
        fake_mounts = mock_mount(fs) if mountinfo is None else mountinfo
        fake_mounts = (fake_mounts.replace("0:1", major_minor)
                       .replace("0:2", major_minor))
        return verify_persistent_private_host(
            [candidate],
            minimum_free_bytes=MINIMUM_PREPARE_BYTES,
            mountinfo=fake_mounts,
            environ={} if env is None else env,
            host_platform="linux", machine="x86_64",
            disk_usage=lambda _: SimpleNamespace(
                free=MINIMUM_PREPARE_BYTES * 2 if free is None else free),
            temporary_prefixes=prefixes,
        )

    def test_permitted_mock_ext4_and_large_owner_private_directory(self):
        result = self.audit()
        self.assertTrue(result["platform_accepted"])
        self.assertEqual(result["private_owner_directories_verified"], 1)
        self.assertFalse(result["drive_upload_performed"])
        self.assertFalse(result["capture_ready"])

    def test_ephemeral_overlay_and_tmpfs_denied(self):
        for fs in ("overlay", "tmpfs", "ramfs", "squashfs", "aufs"):
            with self.subTest(fs=fs), self.assertRaises(PersistentHostError):
                self.audit(fs=fs)

    def test_unknown_fuse_or_nfs_storage_rejected(self):
        for fs in ("fuse.rclone", "fuseblk", "nfs", "nfs4", "cifs",
                   "9p", "virtiofs", "mysteryfs"):
            with self.subTest(fs=fs), self.assertRaises(PersistentHostError):
                self.audit(fs=fs)

    def test_read_only_mount_rejected(self):
        for options in ("ro,relatime", "rw,relatime"):
            # In the second case the superblock is independently read-only.
            supermode = "rw" if options.startswith("ro") else "ro"
            line = ("1 0 0:1 / / " + options +
                    " - ext4 /dev/fake " + supermode + "\n")
            with self.subTest(options=options), self.assertRaises(PersistentHostError):
                self.audit(mountinfo=line)

    def test_mountpoint_with_escaped_spaces_is_handled(self):
        target = self.root / "owner files"
        target.mkdir(mode=0o700)
        escaped = str(self.root).replace(" ", "\\040") + "/owner\\040files"
        line = ("1 0 0:1 / / rw,relatime - overlay none rw\n"
                + f"2 1 0:2 / {escaped} rw,relatime - ext4 /dev/fake rw\n")
        self.assertTrue(self.audit(path=target, mountinfo=line)["platform_accepted"])

    def test_ci_environment_denied_before_write(self):
        for marker in ("CI", "GITHUB_ACTIONS", "RUNNER_TEMP",
                       "GITHUB_WORKSPACE"):
            with self.subTest(marker=marker), self.assertRaises(PersistentHostError):
                self.audit(env={marker: "1"})

    def test_insufficient_free_space_denied(self):
        with self.assertRaises(PersistentHostError):
            self.audit(free=MINIMUM_PREPARE_BYTES - 1)

    def test_owner_directory_must_be_mode_0700(self):
        self.root.chmod(0o755)
        with self.assertRaises(PersistentHostError):
            self.audit()

    def test_symlinked_work_parent_denied(self):
        link = self.root / "alias"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(PersistentHostError):
            self.audit(path=link)

    def test_repository_checkout_denied(self):
        (self.root / ".git").mkdir(mode=0o700)
        with self.assertRaises(PersistentHostError):
            self.audit()

    def test_tmp_location_rejected_with_production_prefix_policy(self):
        with self.assertRaises(PersistentHostError):
            self.audit(prefixes=(self.root,))

    def test_nested_persistent_mount_selection_is_most_specific(self):
        nested = self.root / "private-build"
        nested.mkdir(mode=0o700)
        line = ("1 0 0:1 / / rw - overlay none rw\n"
                + f"2 1 0:2 / {self.root} rw - ext4 /dev/fake rw\n")
        report = self.audit(path=nested, mountinfo=line)
        self.assertTrue(report["platform_accepted"])

    def test_mountinfo_device_must_match_kernel_st_dev(self):
        current = self.root.stat().st_dev
        other = f"{os.major(current) + 1}:{os.minor(current)}"
        mount = f"1 0 {other} / / rw,relatime - ext4 /dev/fake rw\n"
        with self.assertRaises(PersistentHostError):
            self.audit(mountinfo=mount)

    def test_buried_mount_with_same_path_but_different_device_is_rejected(self):
        different = f"{os.major(self.root.stat().st_dev) + 1}:3"
        mount = (mock_mount("ext4") +
                 f"2 1 {different} / / rw,relatime - overlay none rw\n")
        with self.assertRaises(PersistentHostError):
            self.audit(mountinfo=mount)

    def test_duplicate_mountpoint_with_conflicting_writability_rejected(self):
        mount = (mock_mount("ext4") +
                 "2 1 0:2 / / ro,relatime - ext4 /dev/fake ro\n")
        with self.assertRaises(PersistentHostError):
            self.audit(mountinfo=mount)

    def test_invalid_mount_device_identifier_refused(self):
        mount = "1 0 unknown-device / / rw,relatime - ext4 /dev/fake rw\n"
        with self.assertRaises(PersistentHostError):
            self.audit(mountinfo=mount)

    def test_malformed_mount_table_rejected(self):
        with self.assertRaises(PersistentHostError):
            self.audit(mountinfo="not a valid mountinfo row\n")

    def test_public_mountpoint_without_owner_acl_denied(self):
        self.root.chmod(0o777)
        with self.assertRaises(PersistentHostError):
            self.audit()

    def test_non_linux_architecture_denied(self):
        with self.assertRaises(PersistentHostError):
            verify_persistent_private_host(
                [self.root], minimum_free_bytes=MINIMUM_PREPARE_BYTES,
                mountinfo=mock_mount(), environ={},
                host_platform="darwin", machine="x86_64",
                temporary_prefixes=(),
            )


if __name__ == "__main__":
    unittest.main()
