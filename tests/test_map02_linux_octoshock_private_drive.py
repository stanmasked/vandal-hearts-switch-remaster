"""Stage537 fictional Drive transport simulator; never accesses a real account."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from test_map02_linux_octoshock_archive_readback import private_mock_runtime, sha
from tools.map02_linux_octoshock.private_runtime_tar import pack_runtime
from tools.map02_linux_octoshock.private_runtime_drive import (
    BUILDS_FOLDER_ID, MANIFESTS_FOLDER_ID, PrivateDriveError,
    archive_to_private_drive,
)


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

    def __call__(self, argv):
        name = argv[0]
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
        self.readback = self.base / "downloaded"
        self.transport = FakeDriveTransport()

    def run_archive(self):
        return archive_to_private_drive(
            self.source, self.pin, self.tar, self.tar_sha, self.readback,
            "vh_builds", "vh_manifests", "testowner001",
            invoke=self.transport,
        )

    def test_entire_mock_transfer_and_readback_receipt(self):
        result = self.run_archive()
        self.assertEqual(result["objects_read_back"], 5)
        self.assertEqual(result["files"], 7)
        self.assertFalse(result["capture_ready"])
        self.assertTrue(result["drive_download_bytes_verified"])
        self.assertEqual(self.transport.uploads, 5)
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
                invoke=self.transport
            )
        self.assertEqual(self.transport.uploads, 0)


if __name__ == "__main__":
    unittest.main()
