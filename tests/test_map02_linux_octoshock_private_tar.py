"""Stage535 fictional-only owner-private pack/restore and malicious tar tests."""
from __future__ import annotations

import io
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest

from test_map02_linux_octoshock_archive_readback import private_mock_runtime, sha
from tools.map02_linux_octoshock.private_runtime_tar import (
    PrivateTarError, pack_runtime, restore_runtime,
)


class PrivateTarTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "source"
        private_mock_runtime(self.source)
        self.pin = self.root / "trusted-manifest.sha256"
        self.pin.write_text(
            sha((self.source / "map02-owner-runtime-manifest.json").read_bytes()) + "\n",
            encoding="ascii",
        )
        self.pin.chmod(0o600)
        self.archivedir = self.root / "archive"
        self.archivedir.mkdir(mode=0o700)
        self.archivedir.chmod(0o700)
        self.readback = self.root / "readback"
        self.readback.mkdir(mode=0o700)
        self.readback.chmod(0o700)
        self.archive = self.archivedir / "runtime.tar"
        self.digest = self.archivedir / "archive.sha256"
        self.destination = self.readback / "runtime"

    def pack(self):
        return pack_runtime(self.source, self.pin, self.archive, self.digest)

    def restore(self):
        return restore_runtime(
            self.source, self.pin, self.archive, self.digest, self.destination
        )

    def replace_digest_as_if_untrusted(self):
        self.digest.write_text(sha(self.archive.read_bytes()) + "\n", encoding="ascii")
        self.digest.chmod(0o600)

    def test_exact_private_pack_and_restore(self):
        packed = self.pack()
        self.assertEqual(packed["files"], 7)
        self.assertFalse(packed["drive_upload_authenticated"])
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.digest.stat().st_mode), 0o600)
        restored = self.restore()
        self.assertEqual(restored["files"], 7)
        self.assertFalse(restored["capture_ready"])
        self.assertFalse(restored["drive_upload_authenticated"])
        self.assertEqual(
            (self.destination / "EmuHawk.exe").read_bytes(),
            (self.source / "EmuHawk.exe").read_bytes(),
        )

    def test_refuses_untrusted_manifest_before_pack(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(PrivateTarError):
            self.pack()
        self.assertFalse(self.archive.exists())

    def test_refuses_symlink_in_source(self):
        (self.source / "external-link").symlink_to(self.source / "EmuHawk.exe")
        with self.assertRaises(PrivateTarError):
            self.pack()

    def test_refuses_existing_archive_file(self):
        self.archive.write_bytes(b"keep original bytes")
        with self.assertRaises(PrivateTarError):
            self.pack()
        self.assertEqual(self.archive.read_bytes(), b"keep original bytes")

    def test_refuses_mutated_archive_with_original_sha(self):
        self.pack()
        with self.archive.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaises(PrivateTarError):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_refuses_replaced_local_archive_sha(self):
        self.pack()
        self.digest.write_text("f" * 64 + "\n", encoding="ascii")
        with self.assertRaises(PrivateTarError):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_refuses_added_tar_entry_even_when_hash_replaced(self):
        self.pack()
        with tarfile.open(self.archive, "a") as stream:
            m = tarfile.TarInfo("runtime/unlisted.bin")
            m.mode, m.size = 0o600, 4
            stream.addfile(m, io.BytesIO(b"evil"))
        self.replace_digest_as_if_untrusted()
        with self.assertRaises(PrivateTarError):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_refuses_tar_path_traversal_even_when_hash_replaced(self):
        self.pack()
        with tarfile.open(self.archive, "a") as stream:
            m = tarfile.TarInfo("../../unsafe-owner-output")
            m.mode, m.size = 0o600, 4
            stream.addfile(m, io.BytesIO(b"evil"))
        self.replace_digest_as_if_untrusted()
        with self.assertRaises(PrivateTarError):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_refuses_tar_symlink_even_when_hash_replaced(self):
        self.pack()
        with tarfile.open(self.archive, "a") as stream:
            m = tarfile.TarInfo("runtime/stray-link")
            m.type, m.mode = tarfile.SYMTYPE, 0o777
            m.linkname = "../../secret"
            stream.addfile(m)
        self.replace_digest_as_if_untrusted()
        with self.assertRaises(PrivateTarError):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_refuses_source_mutation_after_pack(self):
        self.pack()
        (self.source / "EmuHawk.exe").write_bytes(b"tamper")
        with self.assertRaises(PrivateTarError):
            self.restore()

    def test_refuses_existing_restore_destination(self):
        self.pack()
        self.destination.mkdir(mode=0o700)
        with self.assertRaises(PrivateTarError):
            self.restore()

    def test_refuses_archive_directory_with_weak_permissions(self):
        self.archivedir.chmod(0o755)
        with self.assertRaises(PrivateTarError):
            self.pack()
        self.assertFalse(self.archive.exists())

    def test_refuses_added_empty_directory(self):
        self.pack()
        with tarfile.open(self.archive, "a") as stream:
            m = tarfile.TarInfo("runtime/unlisted-dir")
            m.type, m.mode = tarfile.DIRTYPE, 0o700
            stream.addfile(m)
        self.replace_digest_as_if_untrusted()
        with self.assertRaises(PrivateTarError):
            self.restore()


if __name__ == "__main__":
    unittest.main()
