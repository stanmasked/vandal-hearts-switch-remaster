"""Stage537 fictional Drive transport simulator; never accesses a real account."""
from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from test_map02_linux_octoshock_archive_readback import private_mock_runtime, sha
from tools.map02_linux_octoshock.private_runtime_tar import pack_runtime
from tools.map02_linux_octoshock.private_runtime_drive import (
    PrivateDriveError,
    archive_to_private_drive, _folder_map, _seal_payload,
)


BUILDS_FOLDER_ID = "fictionalBuildsFolderRoot1"
MANIFESTS_FOLDER_ID = "fictionalManifestFolderR2"


class FakeDriveTransport:
    """Only an in-memory rclone stand-in, never evidence of Google Drive."""
    def __init__(self):
        self.remote = {"vh_builds": {}, "vh_manifests": {}}
        self.folder_ids = {
            "vh_builds": BUILDS_FOLDER_ID, "vh_manifests": MANIFESTS_FOLDER_ID
        }
        self.uploads = 0
        self.corrupt_download = False
        self.bad_object_metadata = False
        self.mutate_owner_archive = None
        self.upload_sources = []
        self.version = "rclone v1.69.3"

    def __call__(self, argv):
        name = argv[0]
        if name == "version":
            return self.version + "\n- os/version: synthetic-test-only\n"
        if name == "config" and argv[1] == "redacted":
            remote = argv[2]
            return (
                f"[{remote}]\ntype = drive\n"
                f"root_folder_id = {self.folder_ids[remote]}\n"
                "token = XXX\n"
            )
        if name == "lsf":
            assert argv[1] == "--files-only"
            remote = argv[2].removesuffix(":")
            return "".join(filename + "\n" for filename in self.remote[remote])
        if name == "lsjson":
            assert argv[1] == "--stat"
            remote, filename = argv[2].split(":", 1)
            data = self.remote[remote][filename]
            return json.dumps({
                "ID": ("not-valid-!" if self.bad_object_metadata else
                       "fictionalDrive" + str(len(data)) + filename.replace(".", "_")),
                "Name": filename, "IsDir": False, "Size": len(data),
            })
        if name == "copyto":
            source, dest = argv[-2:]
            if ":" in dest:
                remote, filename = dest.split(":", 1)
                assert "--immutable" in argv
                assert filename not in self.remote[remote], "immutable object overwritten"
                if self.uploads == 0 and self.mutate_owner_archive is not None:
                    self.mutate_owner_archive.write_bytes(b"PRIVATE TAMPERED OUTPUT")
                self.upload_sources.append(source)
                self.remote[remote][filename] = Path(source).read_bytes()
                self.uploads += 1
            else:
                remote, filename = source.split(":", 1)
                data = self.remote[remote][filename]
                if self.corrupt_download and filename.endswith(".tar"):
                    data += b"forged"
                path = Path(dest)
                assert not path.exists()
                path.write_bytes(data)
            return ""
        raise AssertionError("unexpected fictional rclone command: " + name)


class Stage537TransportTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.base = Path(d.name)
        self.source = self.base / "owner"
        private_mock_runtime(self.source)
        self.pin = self.base / "owner-manifest.sha256"
        self.pin.write_text(
            sha((self.source / "map02-owner-runtime-manifest.json").read_bytes()) + "\n",
            encoding="ascii"
        )
        self.pin.chmod(0o600)
        self.archive_dir = self.base / "archive"
        self.archive_dir.mkdir(mode=0o700)
        self.archive_dir.chmod(0o700)
        self.tar = self.archive_dir / "runtime.tar"
        self.tar_sha = self.archive_dir / "runtime.tar.sha256"
        pack_runtime(self.source, self.pin, self.tar, self.tar_sha)
        self.private_map = self.base / "private-folders.json"
        self.private_map.write_text(json.dumps({
            "builds_folder_id": BUILDS_FOLDER_ID,
            "manifests_folder_id": MANIFESTS_FOLDER_ID,
        }), encoding="utf-8")
        self.private_map.chmod(0o600)
        self.readback = self.base / "downloaded"
        self.transport = FakeDriveTransport()

    def run_archive(self):
        return archive_to_private_drive(
            self.source, self.pin, self.tar, self.tar_sha, self.readback,
            "vh_builds", "vh_manifests", "testowner001",
            self.private_map, invoke=self.transport,
        )

    def test_seal_payload_snapshot_hash_and_mode(self):
        parent = self.base / "sealed-unit"
        parent.mkdir(mode=0o700)
        target = parent / "runtime-copy.tar"
        expected = sha(self.tar.read_bytes())
        self.assertEqual(_seal_payload(self.tar, target), expected)
        self.assertEqual(target.read_bytes(), self.tar.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(target.stat().st_ino, self.tar.stat().st_ino)

    def test_seal_payload_rejects_preexisting_target(self):
        parent = self.base / "sealed-existing"
        parent.mkdir(mode=0o700)
        target = parent / "runtime-copy.tar"
        target.write_bytes(b"preserve")
        target.chmod(0o600)
        with self.assertRaises(PrivateDriveError):
            _seal_payload(self.tar, target)
        self.assertEqual(target.read_bytes(), b"preserve")

    def test_folder_map_anchored_descriptor_reads_owner_only_config(self):
        self.assertEqual(
            _folder_map(self.private_map, self.source),
            (BUILDS_FOLDER_ID, MANIFESTS_FOLDER_ID),
        )

    def test_folder_map_same_contents_inode_swap_before_open_denied(self):
        original_open = os.open
        payload = self.private_map.read_bytes()
        exchanged = self.base / "old-folder-map.json"
        swapped = False

        def replace_file(file, flags, *args, **kwargs):
            nonlocal swapped
            if file == self.private_map.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                self.private_map.rename(exchanged)
                self.private_map.write_bytes(payload)
                self.private_map.chmod(0o600)
            return original_open(file, flags, *args, **kwargs)

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=replace_file):
            with self.assertRaises(PrivateDriveError):
                _folder_map(self.private_map, self.source)
        self.assertTrue(swapped)

    def test_folder_map_swap_after_open_but_before_read_denied(self):
        original_open = os.open
        payload = self.private_map.read_bytes()
        exchanged = self.base / "old-folder-map.json"
        swapped = False

        def replace_after_open(file, flags, *args, **kwargs):
            nonlocal swapped
            fd = original_open(file, flags, *args, **kwargs)
            if file == self.private_map.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                self.private_map.rename(exchanged)
                self.private_map.write_bytes(payload)
                self.private_map.chmod(0o600)
            return fd

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=replace_after_open):
            with self.assertRaises(PrivateDriveError):
                _folder_map(self.private_map, self.source)
        self.assertTrue(swapped)

    def test_folder_map_symlink_swap_before_open_denied(self):
        original_open = os.open
        exchanged = self.base / "old-folder-map.json"
        swapped = False

        def replace_with_symlink(file, flags, *args, **kwargs):
            nonlocal swapped
            if file == self.private_map.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                self.private_map.rename(exchanged)
                self.private_map.symlink_to(exchanged)
            return original_open(file, flags, *args, **kwargs)

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=replace_with_symlink):
            with self.assertRaises(PrivateDriveError):
                _folder_map(self.private_map, self.source)
        self.assertTrue(swapped)

    def test_folder_map_oversized_owner_config_denied(self):
        self.private_map.write_bytes(b" " * 2049)
        with self.assertRaises(PrivateDriveError):
            _folder_map(self.private_map, self.source)

    def test_folder_map_nested_no_symlink_ancestor_chain_accepted(self):
        outer = self.base / "owner-parent"
        inner = outer / "private-mapping"
        outer.mkdir(mode=0o700)
        inner.mkdir(mode=0o700)
        candidate = inner / "scope.json"
        candidate.write_bytes(self.private_map.read_bytes())
        candidate.chmod(0o600)
        self.assertEqual(
            _folder_map(candidate, self.source),
            (BUILDS_FOLDER_ID, MANIFESTS_FOLDER_ID),
        )

    def test_folder_map_same_content_parent_swap_before_open_rejected(self):
        vault = self.base / "parent-to-swap"
        vault.mkdir(mode=0o700)
        candidate = vault / "scope.json"
        payload = self.private_map.read_bytes()
        candidate.write_bytes(payload)
        candidate.chmod(0o600)
        old_vault = self.base / "old-parent-before"
        original_open = os.open
        swapped = False

        def swap_parent_before_open(file, flags, *args, **kwargs):
            nonlocal swapped
            if file == vault.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                vault.rename(old_vault)
                vault.mkdir(mode=0o700)
                replacement = vault / "scope.json"
                replacement.write_bytes(payload)
                replacement.chmod(0o600)
            return original_open(file, flags, *args, **kwargs)

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=swap_parent_before_open):
            with self.assertRaises(PrivateDriveError):
                _folder_map(candidate, self.source)
        self.assertTrue(swapped)

    def test_folder_map_same_content_parent_swap_after_open_rejected(self):
        vault = self.base / "parent-after-open"
        vault.mkdir(mode=0o700)
        candidate = vault / "scope.json"
        payload = self.private_map.read_bytes()
        candidate.write_bytes(payload)
        candidate.chmod(0o600)
        old_vault = self.base / "old-parent-after"
        original_open = os.open
        swapped = False

        def swap_parent_after_open(file, flags, *args, **kwargs):
            nonlocal swapped
            fd = original_open(file, flags, *args, **kwargs)
            if file == vault.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                vault.rename(old_vault)
                vault.mkdir(mode=0o700)
                replacement = vault / "scope.json"
                replacement.write_bytes(payload)
                replacement.chmod(0o600)
            return fd

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=swap_parent_after_open):
            with self.assertRaises(PrivateDriveError):
                _folder_map(candidate, self.source)
        self.assertTrue(swapped)

    def test_folder_map_grandparent_swap_after_open_rejected(self):
        outer = self.base / "outer-ancestor"
        vault = outer / "private-vault"
        vault.mkdir(mode=0o700, parents=True)
        candidate = vault / "scope.json"
        payload = self.private_map.read_bytes()
        candidate.write_bytes(payload)
        candidate.chmod(0o600)
        old_outer = self.base / "old-outer-ancestor"
        original_open = os.open
        swapped = False

        def swap_grandparent(file, flags, *args, **kwargs):
            nonlocal swapped
            fd = original_open(file, flags, *args, **kwargs)
            if file == outer.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                outer.rename(old_outer)
                vault.mkdir(mode=0o700, parents=True)
                replacement = vault / "scope.json"
                replacement.write_bytes(payload)
                replacement.chmod(0o600)
            return fd

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=swap_grandparent):
            with self.assertRaises(PrivateDriveError):
                _folder_map(candidate, self.source)
        self.assertTrue(swapped)

    def test_folder_map_ancestor_symlink_swap_before_open_rejected(self):
        vault = self.base / "symlink-parent"
        vault.mkdir(mode=0o700)
        candidate = vault / "scope.json"
        candidate.write_bytes(self.private_map.read_bytes())
        candidate.chmod(0o600)
        old_vault = self.base / "old-symlink-parent"
        original_open = os.open
        swapped = False

        def symlink_parent(file, flags, *args, **kwargs):
            nonlocal swapped
            if file == vault.name and "dir_fd" in kwargs and not swapped:
                swapped = True
                vault.rename(old_vault)
                vault.symlink_to(old_vault, target_is_directory=True)
            return original_open(file, flags, *args, **kwargs)

        with patch("tools.map02_linux_octoshock.private_runtime_drive.os.open",
                   side_effect=symlink_parent):
            with self.assertRaises(PrivateDriveError):
                _folder_map(candidate, self.source)
        self.assertTrue(swapped)

    def test_entire_mock_transfer_and_readback_receipt(self):
        result = self.run_archive()
        self.assertEqual(result["objects_read_back"], 5)
        self.assertEqual(result["files"], 7)
        self.assertFalse(result["capture_ready"])
        self.assertTrue(result["drive_download_bytes_verified"])
        self.assertEqual(self.transport.uploads, 5)
        self.assertTrue(all("sealed-for-upload" in name or "receipt.json" in name
                            for name in self.transport.upload_sources))
        self.assertNotIn(str(self.tar), self.transport.upload_sources)
        manifest = self.transport.remote["vh_manifests"][
            "map02-runtime-testowner001.receipt.json"
        ]
        receipt = json.loads(manifest)
        self.assertEqual(receipt["runtime_file_count"], 7)
        self.assertEqual(len(receipt["objects"]), 4)
        self.assertFalse(receipt["capture_ready"])
        self.assertTrue(
            (self.readback / "restored/runtime/EmuHawk.exe").is_file()
        )

    def test_mutation_of_owner_tar_during_transfer_cannot_upload_mutated_bytes(self):
        original = self.tar.read_bytes()
        self.transport.mutate_owner_archive = self.tar
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        # The first upload is the sealed tar, unaffected by concurrent
        # tampering of the original owner build output.
        uploaded = self.transport.remote["vh_builds"].get(
            "map02-runtime-testowner001.tar"
        )
        self.assertEqual(uploaded, original)
        self.assertNotIn(b"PRIVATE TAMPERED OUTPUT", uploaded)
        self.assertFalse(any(n.endswith(".receipt.json")
                             for n in self.transport.remote["vh_manifests"]))

    def test_sealed_tar_snapshot_blocks_direct_source_path_upload(self):
        self.run_archive()
        self.assertNotIn(str(self.tar), self.transport.upload_sources)
        self.assertTrue(
            "sealed-for-upload" in self.transport.upload_sources[0]
        )

    def test_create_independent_owner_receipt_pin_after_readback(self):
        anchor = self.base / "offline-owner-receipt.sha256"
        result = archive_to_private_drive(
            self.source, self.pin, self.tar, self.tar_sha, self.readback,
            "vh_builds", "vh_manifests", "testowner001", self.private_map,
            owner_receipt_pin_output=anchor, invoke=self.transport,
        )
        expected = sha(self.transport.remote["vh_manifests"][
            "map02-runtime-testowner001.receipt.json"])
        self.assertEqual(anchor.read_text(encoding="ascii"), expected + "\n")
        self.assertEqual(anchor.stat().st_mode & 0o777, 0o600)
        self.assertTrue(result["owner_receipt_pin_written"])

    def test_existing_owner_receipt_pin_rejected_before_upload(self):
        anchor = self.base / "offline-owner-receipt.sha256"
        anchor.write_text("0" * 64 + "\n", encoding="ascii")
        anchor.chmod(0o600)
        with self.assertRaises(PrivateDriveError):
            archive_to_private_drive(
                self.source, self.pin, self.tar, self.tar_sha, self.readback,
                "vh_builds", "vh_manifests", "testowner001", self.private_map,
                owner_receipt_pin_output=anchor, invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(anchor.read_text(encoding="ascii"), "0" * 64 + "\n")

    def test_wrong_drive_folder_scope_fails_before_upload(self):
        self.transport.folder_ids["vh_builds"] = "wrong-folder"
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_corrupted_download_refused_and_no_receipt(self):
        self.transport.corrupt_download = True
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertFalse(
            any(n.endswith("receipt.json")
                for n in self.transport.remote["vh_manifests"])
        )

    def test_outdated_rclone_refused_before_upload(self):
        self.transport.version = "rclone v1.63.4"
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_invalid_rclone_version_refused_before_upload(self):
        self.transport.version = "not-a-real-rclone"
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_duplicate_remote_name_blocked(self):
        self.transport.remote["vh_builds"]["map02-runtime-testowner001.tar"] = b"old"
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_bad_remote_object_identity_refused(self):
        self.transport.bad_object_metadata = True
        with self.assertRaises(PrivateDriveError):
            self.run_archive()

    def test_missing_owner_trust_anchor_refused(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_owner_game_bin_file_prohibited_before_upload(self):
        (self.source / "SCPH1001.bin").write_bytes(b"private-bios-placeholder")
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_forged_tar_even_with_rehashed_digest_blocked_before_upload(self):
        # The owner's locally trusted tar digest can be forged together with
        # archive bytes; inspecting archive membership BEFORE upload is required.
        with tarfile.open(self.tar, "a") as stream:
            extra = tarfile.TarInfo("runtime/private-disc.cue")
            extra.mode = 0o600
            extra.size = 7
            stream.addfile(extra, io.BytesIO(b"PRIVATE"))
        self.tar_sha.write_text(
            sha(self.tar.read_bytes()) + "\n", encoding="ascii"
        )
        self.tar_sha.chmod(0o600)
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_owner_original_game_file_prohibited(self):
        (self.source / "disc.cue").write_bytes(b"original-game-path")
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_insecure_readback_parent_refused(self):
        self.base.chmod(0o755)
        with self.assertRaises(PrivateDriveError):
            self.run_archive()
        self.assertEqual(self.transport.uploads, 0)

    def test_invalid_session_id_refused(self):
        with self.assertRaises(PrivateDriveError):
            archive_to_private_drive(
                self.source, self.pin, self.tar, self.tar_sha, self.readback,
                "vh_builds", "vh_manifests", "../not-safe",
                self.private_map, invoke=self.transport
            )
        self.assertEqual(self.transport.uploads, 0)


if __name__ == "__main__":
    unittest.main()
