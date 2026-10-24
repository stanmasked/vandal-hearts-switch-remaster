"""Safety-contract tests for the owner-local Octoshock runtime stager."""
from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.map02_linux_octoshock.build_and_stage_owner import (
    MANIFEST_SCHEMA,
    find_bizhawk_root,
    resolve_output_root,
    safe_extract_archive,
    sha256_file,
    validate_tar_members,
)


class OwnerRuntimeStageSafetyTests(unittest.TestCase):
    def test_output_root_requires_absolute_nonexistent_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkout = root / "repo"
            checkout.mkdir()
            (checkout / ".git").mkdir()
            with self.assertRaises(ValueError):
                resolve_output_root(Path("relative-runtime"), checkout)
            existing = root / "already-exists"
            existing.mkdir()
            with self.assertRaises(ValueError):
                resolve_output_root(existing, checkout)

    def test_output_root_must_be_outside_git_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkout = root / "repo"
            checkout.mkdir()
            (checkout / ".git").mkdir()
            with self.assertRaises(ValueError):
                resolve_output_root(checkout / "runtime", checkout)
            accepted = resolve_output_root(root / "private-runtime", checkout)
            self.assertEqual(accepted, root / "private-runtime")
            self.assertFalse(accepted.exists())

    def test_archive_member_validator_rejects_traversal_and_links(self):
        traversal = tarfile.TarInfo("../outside.txt")
        absolute = tarfile.TarInfo("/tmp/outside.txt")
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside.txt"
        for member in (traversal, absolute, link):
            with self.subTest(member=member.name):
                with self.assertRaises(ValueError):
                    validate_tar_members([member])

    def test_safe_extractor_rejects_path_traversal_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "unsafe.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b"must not escape"
                member = tarfile.TarInfo("../outside.txt")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            destination = root / "extracted"
            with self.assertRaises(ValueError):
                safe_extract_archive(archive_path, destination)
            self.assertFalse((root / "outside.txt").exists())
            self.assertFalse(destination.exists())

    def test_find_runtime_root_requires_official_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "EmuHawk.exe").write_bytes(b"synthetic")
            (root / "EmuHawkMono.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            dll = root / "dll"
            dll.mkdir()
            for name in (
                "BizHawk.Client.Common.dll",
                "BizHawk.Emulation.Common.dll",
                "BizHawk.Emulation.Cores.dll",
            ):
                (dll / name).write_bytes(b"synthetic")
            self.assertEqual(find_bizhawk_root(root), root)
            (root / "nested").mkdir()
            (root / "nested" / "EmuHawk.exe").write_bytes(b"duplicate")
            with self.assertRaises(ValueError):
                find_bizhawk_root(root)

    def test_sha256_helper_matches_known_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "fixture.txt"
            fixture.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(fixture),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_manifest_schema_is_explicit(self):
        self.assertEqual(MANIFEST_SCHEMA, "vh.map02.owner-local-runtime.v2")


if __name__ == "__main__":
    unittest.main()
