"""Synthetic owner-runtime integrity verification and tamper regressions."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tools.map02_linux_octoshock.verify_owner_runtime import (
    BIZHAWK_ARCHIVE_SHA256, NATIVE_NAME, RuntimeVerificationError,
    SCHEMA, UPSTREAM_COMMIT, UPSTREAM_TREE, verify_runtime,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(root: Path) -> dict:
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    (root / "dll").mkdir(mode=0o700)
    (root / "ExternalTools").mkdir(mode=0o700)
    for relative, data in (
        ("EmuHawk.exe", b"fictional emuhawk"),
        ("EmuHawkMono.sh", b"#!/bin/sh\nexit 0\n"),
        ("dll/BizHawk.Emulation.Cores.dll", b"fictional core"),
        ("dll/" + NATIVE_NAME, b"fictional native"),
        ("ExternalTools/VhMap02CoreWitness.dll", b"fictional plugin"),
    ):
        (root / relative).write_bytes(data)
    core_hash = digest(b"fictional core")
    native_hash = digest(b"fictional native")
    plugin_hash = digest(b"fictional plugin")
    manifest = {
        "schema": SCHEMA,
        "source": {
            "commit": UPSTREAM_COMMIT, "octoshock_tree": UPSTREAM_TREE,
            "source_file_count": 41,
        },
        "official_bizhawk": {
            "version": "2.11", "archive_sha256": BIZHAWK_ARCHIVE_SHA256,
            "core_assembly_sha256": core_hash,
        },
        "native_octoshock": {
            "filename": NATIVE_NAME, "sha256": native_hash,
            "managed_exports_verified": 32,
            "installed_relative_paths": ["dll/" + NATIVE_NAME],
        },
        "experimental_witness_plugin": {
            "filename": "ExternalTools/VhMap02CoreWitness.dll",
            "sha256": plugin_hash,
        },
        "smoke_tests": {
            "native_abi": "pass",
            "official_managed_binding_synthetic_firmware": "pass",
            "emuhawk_no_media_startup": "pass",
        },
        "game_media_used": False, "bios_used": False, "bk2_used": False,
        "game_loaded": False, "psx_capture_ready": False,
    }
    manifest_path = root / "map02-owner-runtime-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    pins = (
        "export VH_MAP02_CORE_EXPECTED_CORE_ASSEMBLY_SHA256=" + core_hash + "\n"
        "export VH_MAP02_CORE_EXPECTED_NATIVE_MODULE_SHA256=" + native_hash + "\n"
        "export VH_MAP02_PRIVATE_WITNESS_DLL_SHA256=" + plugin_hash + "\n"
        "export VH_MAP02_CORE_EXPECTED_DLL_SHA256=" + plugin_hash + "\n"
    )
    pins_path = root / "map02-owner-runtime-pins.env"
    pins_path.write_text(pins, encoding="ascii")
    os.chmod(pins_path, 0o600)
    return manifest


class OwnerRuntimeVerifierTests(unittest.TestCase):
    def with_fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "owner-runtime"
        manifest = fixture(root)
        return temp, root, manifest

    def test_synthetic_staged_runtime_passes_without_media(self):
        temp, root, _ = self.with_fixture()
        with temp:
            result = verify_runtime(root)
            self.assertIs(result["verified"], True)
            self.assertIs(result["capture_ready"], False)

    def test_rejects_modified_native_and_managed_components(self):
        for relative in (
            "dll/" + NATIVE_NAME,
            "dll/BizHawk.Emulation.Cores.dll",
            "ExternalTools/VhMap02CoreWitness.dll",
        ):
            with self.subTest(relative=relative):
                temp, root, _ = self.with_fixture()
                with temp:
                    (root / relative).write_bytes(b"tampered")
                    with self.assertRaises(RuntimeVerificationError):
                        verify_runtime(root)

    def test_rejects_world_readable_staged_root(self):
        temp, root, _ = self.with_fixture()
        with temp:
            os.chmod(root, 0o755)
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(root)

    def test_rejects_private_manifest_or_pins_with_relaxed_permissions(self):
        for name in ("map02-owner-runtime-manifest.json", "map02-owner-runtime-pins.env"):
            with self.subTest(name=name):
                temp, root, _ = self.with_fixture()
                with temp:
                    os.chmod(root / name, 0o644)
                    with self.assertRaises(RuntimeVerificationError):
                        verify_runtime(root)

    def test_rejects_tampered_environment_pins(self):
        temp, root, _ = self.with_fixture()
        with temp:
            path = root / "map02-owner-runtime-pins.env"
            path.write_text(path.read_text(encoding="ascii").replace(
                "VH_MAP02_CORE_EXPECTED_DLL_SHA256=",
                "VH_MAP02_WRONG_DLL_SHA256=",
            ), encoding="ascii")
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(root)

    def test_rejects_fake_gameplay_readiness_or_media_claim(self):
        for key in ("game_media_used", "bios_used", "bk2_used", "game_loaded",
                    "psx_capture_ready"):
            with self.subTest(key=key):
                temp, root, manifest = self.with_fixture()
                with temp:
                    manifest[key] = True
                    (root / "map02-owner-runtime-manifest.json").write_text(
                        json.dumps(manifest), encoding="utf-8"
                    )
                    with self.assertRaises(RuntimeVerificationError):
                        verify_runtime(root)

    def test_rejects_forged_upstream_source_identity(self):
        temp, root, manifest = self.with_fixture()
        with temp:
            manifest["source"]["commit"] = "0" * 40
            (root / "map02-owner-runtime-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(root)

    def test_rejects_unlisted_or_extra_native_modules(self):
        temp, root, manifest = self.with_fixture()
        with temp:
            manifest["native_octoshock"]["installed_relative_paths"] = []
            (root / "map02-owner-runtime-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(root)

        temp, root, _ = self.with_fixture()
        with temp:
            (root / NATIVE_NAME).write_bytes(b"fictional native")
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(root)

    def test_rejects_symlink_replacement_of_native_module(self):
        temp, root, _ = self.with_fixture()
        with temp:
            native = root / "dll" / NATIVE_NAME
            native.unlink()
            target = root / "somewhere-else"
            target.write_bytes(b"fictional native")
            native.symlink_to(target)
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(root)

    def test_rejects_nonabsolute_or_symlink_root(self):
        temp, root, _ = self.with_fixture()
        with temp:
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(Path("relative-owner-runtime"))
            link = Path(temp.name) / "alias"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(RuntimeVerificationError):
                verify_runtime(link)


if __name__ == "__main__":
    unittest.main()
