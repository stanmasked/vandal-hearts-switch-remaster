"""Stage539 independently pinned fictional Drive readback, no original runtime."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    IndependentAuditError, _safe_restore, audit_independent_readback,
)


class IndependentReadbackTests(unittest.TestCase):
    def setUp(self):
        # Reuse the 13-test fixture setup, not its actual unittest subclasses.
        Stage537TransportTests.setUp(self)
        Stage537TransportTests.run_archive(self)
        self.receipt_name = "map02-runtime-testowner001.receipt.json"
        self.receipt_pin = self.base / "trusted-receipt.sha256"
        content = self.transport.remote["vh_manifests"][self.receipt_name]
        self.receipt_pin.write_text(
            hashlib.sha256(content).hexdigest() + "\n", encoding="ascii"
        )
        self.receipt_pin.chmod(0o600)
        self.reaudit = self.base / "new-readback-audit"

    def run_audit(self):
        return audit_independent_readback(
            self.private_map, self.pin, self.tar_sha, self.receipt_pin,
            self.reaudit, "vh_builds", "vh_manifests",
            "testowner001", invoke=self.transport
        )

    def test_complete_independent_readback_without_source_runtime(self):
        shutil.rmtree(self.source)
        report = self.run_audit()
        self.assertEqual(report["files"], 7)
        self.assertEqual(report["objects_read_back"], 5)
        self.assertTrue(report["independent_receipt_pin_verified"])
        self.assertFalse(report["original_runtime_required"])
        self.assertFalse(report["capture_ready"])
        self.assertTrue((self.reaudit / "restored/runtime/EmuHawk.exe").is_file())

    def test_refuse_corrupted_remote_archive(self):
        key = "map02-runtime-testowner001.tar"
        self.transport.remote["vh_builds"][key] += b"FORGED"
        with self.assertRaises(IndependentAuditError):
            self.run_audit()

    def test_refuse_corrupted_remote_receipt(self):
        self.transport.remote["vh_manifests"][self.receipt_name] += b"x"
        with self.assertRaises(IndependentAuditError):
            self.run_audit()

    def test_refuse_changed_local_receipt_pin(self):
        self.receipt_pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(IndependentAuditError):
            self.run_audit()

    def test_refuse_changed_owner_manifest_pin(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(IndependentAuditError):
            self.run_audit()

    def test_refuse_wrong_folder_root(self):
        self.transport.folder_ids["vh_manifests"] = "anotherFolderWhichIsFake1"
        with self.assertRaises(IndependentAuditError):
            self.run_audit()

    def test_refuse_already_existing_readback(self):
        self.reaudit.mkdir(mode=0o700)
        with self.assertRaises(IndependentAuditError):
            self.run_audit()

    def test_refuse_archive_tar_symlink_entry(self):
        tar = self.base / "malicious.tar"
        target = self.base / "new-malicious-runtime"
        with tarfile.open(tar, "w") as stream:
            top = tarfile.TarInfo("runtime")
            top.type, top.mode = tarfile.DIRTYPE, 0o700
            stream.addfile(top)
            bad = tarfile.TarInfo("runtime/link")
            bad.type, bad.mode = tarfile.SYMTYPE, 0o777
            bad.linkname = "../../private-owner"
            stream.addfile(bad)
        with self.assertRaises(IndependentAuditError):
            # This inner helper throws same generic no-path rejection.
            _safe_restore(tar, target)
        self.assertFalse(target.exists())

    def test_refuse_archive_with_ps1_bios_even_with_valid_tar_structure(self):
        tar = self.base / "disc-leak.tar"
        target = self.base / "new-disc-leak-runtime"
        with tarfile.open(tar, "w") as stream:
            top = tarfile.TarInfo("runtime")
            top.type, top.mode = tarfile.DIRTYPE, 0o700
            stream.addfile(top)
            bios = tarfile.TarInfo("runtime/firmware/scph1001.BIN")
            bios.size, bios.mode = 6, 0o600
            stream.addfile(bios, io.BytesIO(b"PS1ROM"))
        with self.assertRaises(IndependentAuditError):
            _safe_restore(tar, target)
        self.assertFalse(target.exists())

    def test_refuse_archive_with_game_movie_inside_subdirectory(self):
        tar = self.base / "movie-leak.tar"
        target = self.base / "new-movie-leak-runtime"
        with tarfile.open(tar, "w") as stream:
            top = tarfile.TarInfo("runtime")
            top.type, top.mode = tarfile.DIRTYPE, 0o700
            stream.addfile(top)
            movie = tarfile.TarInfo("runtime/captures/inputs.BK2")
            movie.size, movie.mode = 3, 0o600
            stream.addfile(movie, io.BytesIO(b"BK2"))
        with self.assertRaises(IndependentAuditError):
            _safe_restore(tar, target)
        self.assertFalse(target.exists())

    def test_refuse_tar_path_traversal(self):
        tar = self.base / "traversal.tar"
        target = self.base / "new-traversal-runtime"
        with tarfile.open(tar, "w") as stream:
            top = tarfile.TarInfo("runtime")
            top.type, top.mode = tarfile.DIRTYPE, 0o700
            stream.addfile(top)
            bad = tarfile.TarInfo("runtime/../../escape.txt")
            bad.size, bad.mode = 4, 0o600
            stream.addfile(bad, io.BytesIO(b"EVIL"))
        with self.assertRaises(IndependentAuditError):
            _safe_restore(tar, target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
