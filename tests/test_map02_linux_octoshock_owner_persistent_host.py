"""Stage551 simulated mount tests, no actual owner machine or media."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.map02_linux_octoshock.owner_persistent_host import (
    MINIMUM_PREPARE_BYTES, PersistentHostError, verify_persistent_private_host,
    snapshot_private_path_identity, verify_and_snapshot_persistent_host,
    require_unchanged_persistent_host,
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

    def test_secure_private_ancestor_allows_nested_directory(self):
        parent = self.root / "private-parent"
        parent.mkdir(mode=0o700)
        child = parent / "private-child"
        child.mkdir(mode=0o700)
        self.assertTrue(self.audit(path=child)["platform_accepted"])

    def test_group_writable_ancestor_rejected(self):
        parent = self.root / "shared-parent"
        parent.mkdir(mode=0o700)
        child = parent / "private-child"
        child.mkdir(mode=0o700)
        parent.chmod(0o770)
        with self.assertRaises(PersistentHostError):
            self.audit(path=child)

    def test_world_writable_ancestor_rejected(self):
        parent = self.root / "world-parent"
        parent.mkdir(mode=0o700)
        child = parent / "private-child"
        child.mkdir(mode=0o700)
        parent.chmod(0o777)
        with self.assertRaises(PersistentHostError):
            self.audit(path=child)

    def test_second_level_group_writable_ancestor_rejected(self):
        parent = self.root / "shared-parent"
        parent.mkdir(mode=0o700)
        middle = parent / "middle"
        middle.mkdir(mode=0o700)
        child = middle / "private-child"
        child.mkdir(mode=0o700)
        parent.chmod(0o770)
        with self.assertRaises(PersistentHostError):
            self.audit(path=child)

    def recheck_identity(self, path, initial):
        device = path.stat().st_dev
        mountinfo = (
            f"1 0 {os.major(device)}:{os.minor(device)} / / "
            "rw,relatime - ext4 /dev/fake rw\\n"
        ).replace("\\\\n", "\\n")
        return require_unchanged_persistent_host(
            [path], initial, minimum_free_bytes=MINIMUM_PREPARE_BYTES,
            mountinfo=mountinfo, environ={},
            host_platform="linux", machine="x86_64",
            disk_usage=lambda _: SimpleNamespace(free=MINIMUM_PREPARE_BYTES * 2),
            temporary_prefixes=(),
        )

    def test_identity_checkpoint_accepts_same_directory(self):
        leaf = self.root / "stable"
        leaf.mkdir(mode=0o700)
        self.audit(path=leaf)
        saved = snapshot_private_path_identity([leaf])
        self.assertEqual(
            self.recheck_identity(leaf, saved)["private_owner_directories_verified"], 1,
        )

    def test_identity_checkpoint_rejects_leaf_inode_replacement(self):
        leaf = self.root / "replaceable"
        leaf.mkdir(mode=0o700)
        self.audit(path=leaf)
        saved = snapshot_private_path_identity([leaf])
        leaf.rename(self.root / "old-replaceable")
        leaf.mkdir(mode=0o700)
        self.audit(path=leaf)
        with self.assertRaises(PersistentHostError):
            self.recheck_identity(leaf, saved)

    def test_identity_checkpoint_rejects_ancestor_inode_replacement(self):
        parent = self.root / "private-parent"
        parent.mkdir(mode=0o700)
        leaf = parent / "leaf"
        leaf.mkdir(mode=0o700)
        self.audit(path=leaf)
        saved = snapshot_private_path_identity([leaf])
        parent.rename(self.root / "old-private-parent")
        parent.mkdir(mode=0o700)
        leaf.mkdir(mode=0o700)
        self.audit(path=leaf)
        with self.assertRaises(PersistentHostError):
            self.recheck_identity(leaf, saved)

    def test_identity_checkpoint_rejects_changed_owner_mode(self):
        leaf = self.root / "chmoded"
        leaf.mkdir(mode=0o700)
        self.audit(path=leaf)
        saved = snapshot_private_path_identity([leaf])
        leaf.chmod(0o755)
        with self.assertRaises(PersistentHostError):
            self.recheck_identity(leaf, saved)

    def test_identity_checkpoint_rejects_untrusted_empty_baseline(self):
        self.audit()
        with self.assertRaises(PersistentHostError):
            self.recheck_identity(self.root, ())

    def test_initial_baseline_requires_stable_identity_around_two_audits(self):
        leaf = self.root / "baseline-stable"
        leaf.mkdir(mode=0o700)
        with patch(
            "tools.map02_linux_octoshock.owner_persistent_host.verify_persistent_private_host",
            return_value={"platform_accepted": True},
        ) as audit:
            saved = verify_and_snapshot_persistent_host(
                [leaf], minimum_free_bytes=MINIMUM_PREPARE_BYTES,
            )
        self.assertEqual(audit.call_count, 2)
        self.assertEqual(saved, snapshot_private_path_identity([leaf]))

    def test_initial_baseline_rejects_replacement_during_first_audit(self):
        leaf = self.root / "baseline-race"
        parked = self.root / "baseline-race-old"
        leaf.mkdir(mode=0o700)
        calls = []

        def replace_during_audit(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                leaf.rename(parked)
                leaf.mkdir(mode=0o700)
            return {"platform_accepted": True}

        with patch(
            "tools.map02_linux_octoshock.owner_persistent_host.verify_persistent_private_host",
            side_effect=replace_during_audit,
        ) as audit:
            with self.assertRaises(PersistentHostError):
                verify_and_snapshot_persistent_host(
                    [leaf], minimum_free_bytes=MINIMUM_PREPARE_BYTES,
                )
        self.assertEqual(audit.call_count, 1)

    def test_recheck_rejects_replacement_during_audit(self):
        leaf = self.root / "recheck-race"
        parked = self.root / "recheck-race-old"
        leaf.mkdir(mode=0o700)
        saved = snapshot_private_path_identity([leaf])
        calls = []

        def replace_during_audit(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                leaf.rename(parked)
                leaf.mkdir(mode=0o700)
            return {"platform_accepted": True}

        with patch(
            "tools.map02_linux_octoshock.owner_persistent_host.verify_persistent_private_host",
            side_effect=replace_during_audit,
        ) as audit:
            with self.assertRaises(PersistentHostError):
                require_unchanged_persistent_host(
                    [leaf], saved, minimum_free_bytes=MINIMUM_PREPARE_BYTES,
                )
        self.assertEqual(audit.call_count, 1)

    def test_recheck_revalidates_policy_after_identity_sample(self):
        leaf = self.root / "policy-race"
        leaf.mkdir(mode=0o700)
        saved = snapshot_private_path_identity([leaf])
        with patch(
            "tools.map02_linux_octoshock.owner_persistent_host.verify_persistent_private_host",
            side_effect=[
                {"platform_accepted": True},
                PersistentHostError("synthetic mount policy change"),
            ],
        ) as audit:
            with self.assertRaisesRegex(PersistentHostError, "mount policy change"):
                require_unchanged_persistent_host(
                    [leaf], saved, minimum_free_bytes=MINIMUM_PREPARE_BYTES,
                )
        self.assertEqual(audit.call_count, 2)

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
