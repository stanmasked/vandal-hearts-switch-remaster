"""Stage517: entirely fictional DLL hash pins, never PS1/game files."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_witness_plugin_digest import (
    MAX_CORE_DLL_BYTES, require_pinned_core_witness_dll,
)


class PrivateWitnessPluginDigestTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plugin = self.root / "VhMap02CoreWitness.dll"
        self.plugin.write_bytes(b"FICTIONAL-COMPILED-DLL-V1-NO-MEDIA")
        self.sha = hashlib.sha256(self.plugin.read_bytes()).hexdigest()

    def test_exact_independent_hash_accepts_fictional_dll(self):
        self.assertIsNone(require_pinned_core_witness_dll(self.plugin, self.sha))

    def test_uppercase_sha256_accepted(self):
        self.assertIsNone(require_pinned_core_witness_dll(self.plugin, self.sha.upper()))

    def test_wrong_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs from pinned build"):
            require_pinned_core_witness_dll(self.plugin, "0" * 64)

    def test_digest_needs_exact_64_hex_chars(self):
        for wrong in (None, True, 1, "", "0" * 63, "0" * 65,
                      "g" * 64, " " + self.sha, self.sha + "\n"):
            with self.subTest(value=str(wrong)[:12]), self.assertRaisesRegex(
                    ValueError, "64 hex digits"):
                require_pinned_core_witness_dll(self.plugin, wrong)

    def test_missing_dll_refused(self):
        self.plugin.unlink()
        with self.assertRaises(ValueError):
            require_pinned_core_witness_dll(self.plugin, self.sha)

    def test_empty_and_oversize_dll_refused(self):
        self.plugin.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "size or type"):
            require_pinned_core_witness_dll(self.plugin, self.sha)
        with self.plugin.open("wb") as handle:
            handle.truncate(MAX_CORE_DLL_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size or type"):
            require_pinned_core_witness_dll(self.plugin, self.sha)

    def test_relative_dll_refused(self):
        with self.assertRaisesRegex(ValueError, "direct absolute"):
            require_pinned_core_witness_dll(Path("VhMap02CoreWitness.dll"), self.sha)

    def test_directory_as_dll_refused(self):
        self.plugin.unlink()
        self.plugin.mkdir()
        with self.assertRaisesRegex(ValueError, "size or type"):
            require_pinned_core_witness_dll(self.plugin, self.sha)

    def test_symlink_to_real_dll_refused(self):
        link = self.root / "link.dll"
        try:
            link.symlink_to(self.plugin)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")
        with self.assertRaisesRegex(ValueError, "direct absolute"):
            require_pinned_core_witness_dll(link, self.sha)

    def test_changes_during_hashing_detected_before_acceptance(self):
        original_hash_factory = hashlib.sha256
        filename = self.plugin
        class ChangingHash:
            def __init__(self):
                self.real = original_hash_factory()
                self.changed = False
            def update(self, data):
                self.real.update(data)
                if not self.changed:
                    self.changed = True
                    filename.write_bytes(b"FICTIONAL-COMPILED-DLL-V2-NO-MEDIA-CHANGED")
            def hexdigest(self):
                return self.real.hexdigest()
        with patch("tools.map02_private_witness_plugin_digest.hashlib.sha256",
                   side_effect=lambda: ChangingHash()):
            with self.assertRaisesRegex(ValueError, "changed"):
                require_pinned_core_witness_dll(self.plugin, self.sha)


if __name__ == "__main__":
    unittest.main()
