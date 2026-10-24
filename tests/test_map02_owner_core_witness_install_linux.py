"""Synthetic-only tests for the fail-closed Linux witness installer."""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import tempfile
import unittest

from tools.map02_owner_core_witness_install_linux import install


class LinuxWitnessInstallerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bizhawk = self.root / "BizHawk"
        (self.bizhawk / "dll").mkdir(parents=True)
        (self.bizhawk / "EmuHawk.exe").write_bytes(b"fictional executable marker")
        (self.bizhawk / "EmuHawkMono.sh").write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
        (self.bizhawk / "dll" / "BizHawk.Emulation.Cores.dll").write_bytes(b"fictional managed core")
        (self.bizhawk / "liboctoshock.dll.so").write_bytes(b"fictional native core")
        self.source = self.root / "VhMap02CoreWitness.dll"
        self.source.write_bytes(b"fictional public witness plugin only")
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_install_accepts_exact_hash_and_creates_owner_only_file(self):
        report = install(self.bizhawk, self.source, self.sha)
        target = self.bizhawk / "ExternalTools" / "VhMap02CoreWitness.dll"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertTrue(report["verified_source_sha256"])
        self.assertTrue(report["installed_owner_only"])
        self.assertFalse(report["game_assets_read_or_changed"])

    def test_wrong_hash_fails_before_creating_destination(self):
        with self.assertRaisesRegex(ValueError, "differs from"):
            install(self.bizhawk, self.source, "a" * 64)
        self.assertFalse((self.bizhawk / "ExternalTools").exists())

    def test_existing_destination_is_never_overwritten(self):
        external = self.bizhawk / "ExternalTools"
        external.mkdir()
        target = external / "VhMap02CoreWitness.dll"
        target.write_bytes(b"keep existing bytes")
        with self.assertRaises(FileExistsError):
            install(self.bizhawk, self.source, self.sha)
        self.assertEqual(target.read_bytes(), b"keep existing bytes")

    def test_external_tools_symlink_is_rejected(self):
        external = self.bizhawk / "ExternalTools"
        external.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            install(self.bizhawk, self.source, self.sha)

    def test_source_inside_git_checkout_is_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            install(self.bizhawk, self.source, self.sha)


if __name__ == "__main__":
    unittest.main()
