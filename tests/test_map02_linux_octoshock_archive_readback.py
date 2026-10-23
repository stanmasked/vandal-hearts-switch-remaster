"""Fictional-only Stage534 archive/Drive readback comparison tests."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.map02_linux_octoshock.archive_owner_runtime import (
    ArchiveReadbackError, verify_archive_readback,
)
from tools.map02_linux_octoshock.verify_owner_runtime import (
    BIZHAWK_ARCHIVE_SHA256, NATIVE_NAME, SCHEMA, UPSTREAM_COMMIT, UPSTREAM_TREE,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def private_mock_runtime(root: Path) -> None:
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    (root / "dll").mkdir(mode=0o700)
    (root / "ExternalTools").mkdir(mode=0o700)
    payloads = {
        "EmuHawk.exe": b"fictional emuhawk",
        "EmuHawkMono.sh": b"#!/bin/sh\nexit 0\n",
        "dll/BizHawk.Emulation.Cores.dll": b"fictional managed",
        "dll/" + NATIVE_NAME: b"fictional native",
        "ExternalTools/VhMap02CoreWitness.dll": b"fictional plugin",
    }
    for name, value in payloads.items():
        (root / name).write_bytes(value)
    managed = sha(payloads["dll/BizHawk.Emulation.Cores.dll"])
    native = sha(payloads["dll/" + NATIVE_NAME])
    plugin = sha(payloads["ExternalTools/VhMap02CoreWitness.dll"])
    manifest = {
        "schema": SCHEMA,
        "source": {"commit": UPSTREAM_COMMIT, "octoshock_tree": UPSTREAM_TREE,
                   "source_file_count": 41},
        "official_bizhawk": {
            "version": "2.11", "archive_sha256": BIZHAWK_ARCHIVE_SHA256,
            "core_assembly_sha256": managed,
            "emuhawk_exe_sha256": sha(payloads["EmuHawk.exe"]),
            "emuhawk_mono_launcher_sha256": sha(payloads["EmuHawkMono.sh"]),
        },
        "native_octoshock": {
            "filename": NATIVE_NAME, "sha256": native,
            "managed_exports_verified": 32,
            "installed_relative_paths": ["dll/" + NATIVE_NAME],
        },
        "experimental_witness_plugin": {
            "filename": "ExternalTools/VhMap02CoreWitness.dll", "sha256": plugin,
        },
        "smoke_tests": {
            "native_abi": "pass",
            "official_managed_binding_synthetic_firmware": "pass",
            "emuhawk_no_media_startup": "pass",
        },
        "game_media_used": False, "bios_used": False, "bk2_used": False,
        "game_loaded": False, "psx_capture_ready": False,
    }
    mp = root / "map02-owner-runtime-manifest.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    mp.chmod(0o600)
    pins = (
        "export VH_MAP02_CORE_EXPECTED_CORE_ASSEMBLY_SHA256=" + managed + "\n"
        "export VH_MAP02_CORE_EXPECTED_NATIVE_MODULE_SHA256=" + native + "\n"
        "export VH_MAP02_PRIVATE_WITNESS_DLL_SHA256=" + plugin + "\n"
        "export VH_MAP02_CORE_EXPECTED_DLL_SHA256=" + plugin + "\n"
    )
    pp = root / "map02-owner-runtime-pins.env"
    pp.write_text(pins, encoding="ascii")
    pp.chmod(0o600)


class ArchiveReadbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source = self.base / "original"
        self.restored = self.base / "restored"
        private_mock_runtime(self.source)
        shutil.copytree(self.source, self.restored, copy_function=shutil.copy2)
        self.restored.chmod(0o700)
        self.pin = self.base / "owner-external.sha256"
        self.pin.write_text(
            sha((self.source / "map02-owner-runtime-manifest.json").read_bytes())
            + "\n", encoding="ascii"
        )
        self.pin.chmod(0o600)

    def audit(self):
        return verify_archive_readback(self.source, self.restored, self.pin)

    def test_exact_binary_readback_passes(self):
        report = self.audit()
        self.assertTrue(report["source_and_restored_match"])
        self.assertTrue(report["trusted_manifest_pin_verified_twice"])
        self.assertFalse(report["capture_ready"])
        self.assertFalse(report["drive_upload_authenticated"])
        self.assertEqual(report["files"], 7)

    def test_rejects_corrupted_unpinned_auxiliary_file(self):
        (self.restored / "ExtraNotes.txt").write_bytes(b"not part of stage")
        with self.assertRaises(ArchiveReadbackError):
            self.audit()

    def test_rejects_corrupted_runtime_file(self):
        (self.restored / "EmuHawk.exe").write_bytes(b"corrupted")
        with self.assertRaises(ArchiveReadbackError):
            self.audit()

    def test_rejects_missing_or_added_empty_directory(self):
        folder = self.source / "backup-cache"
        folder.mkdir(mode=0o700)
        with self.assertRaises(ArchiveReadbackError):
            self.audit()

    def test_rejects_mode_drift(self):
        # Even an unchanged payload must not lose owner-only permissions.
        (self.restored / "map02-owner-runtime-manifest.json").chmod(0o644)
        with self.assertRaises(ArchiveReadbackError):
            self.audit()

    def test_rejects_symlink_in_restored_tree(self):
        (self.restored / "extra-shortcut").symlink_to(self.restored / "dll")
        with self.assertRaises(ArchiveReadbackError):
            self.audit()

    def test_rejects_replaced_external_pin(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(ArchiveReadbackError):
            self.audit()

    def test_rejects_same_or_nested_runtime(self):
        for path in (self.source, self.source / "dll"):
            with self.subTest(path=path):
                with self.assertRaises(ArchiveReadbackError):
                    verify_archive_readback(self.source, path, self.pin)

    def test_rejects_nonprivate_archive_root(self):
        self.restored.chmod(0o755)
        with self.assertRaises(ArchiveReadbackError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
