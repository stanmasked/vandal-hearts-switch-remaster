"""Synthetic directory fixtures for published NeXium evidence inventory."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from verify_native_av_evidence_inventory import (
    FILES, PREFIX, SCENARIOS, SUFFIX, validate_inventory,
)


class NeXiumPublishedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "published"
        self.root.mkdir()
        for scenario in SCENARIOS:
            folder = self.root / (PREFIX + scenario + SUFFIX)
            folder.mkdir()
            for name in FILES:
                payload = b"" if name == "nexium.log" else b"synthetic-not-real-proof"
                (folder / name).write_bytes(payload)

    def folder(self, scenario="empty"):
        return self.root / (PREFIX + scenario + SUFFIX)

    def cli(self, root=None):
        return subprocess.run(
            [sys.executable, "tests/verify_native_av_evidence_inventory.py",
             str(root or self.root)], capture_output=True, text=True)

    def test_all_seven_synthetic_bundles_pass_without_hardware_claim(self):
        result = validate_inventory(self.root)
        self.assertEqual(result["scenario_count"], 7)
        self.assertEqual(result["files_per_scenario"], 5)
        self.assertFalse(result["audible_audio_verified"])
        output = self.cli()
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(json.loads(output.stdout)["verification"],
                         "exact_published_evidence_inventory")

    def test_missing_scenario_is_rejected(self):
        import shutil
        shutil.rmtree(self.folder("zl"))
        with self.assertRaisesRegex(ValueError, "case directory inventory mismatch"):
            validate_inventory(self.root)

    def test_unexpected_scenario_is_rejected(self):
        (self.root / "native-ps1-music-av-nexium-rogue-evidence").mkdir()
        with self.assertRaisesRegex(ValueError, "case directory inventory mismatch"):
            validate_inventory(self.root)

    def test_unexpected_root_metadata_rejected(self):
        (self.root / ".DS_Store").write_bytes(b"x")
        self.assertNotEqual(self.cli().returncode, 0)

    def test_missing_required_file_rejected(self):
        (self.folder("resume") / "av-after.png").unlink()
        with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
            validate_inventory(self.root)

    def test_extra_file_or_subdirectory_rejected(self):
        (self.folder("zr") / "untrusted.png").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
            validate_inventory(self.root)
        (self.folder("zr") / "untrusted.png").unlink()
        (self.folder("zr") / "nested").mkdir()
        self.assertNotEqual(self.cli().returncode, 0)

    def test_symlinked_evidence_file_rejected(self):
        path = self.folder("full") / "av-before.png"
        path.unlink()
        path.symlink_to(self.folder("full") / "av-after.png")
        with self.assertRaisesRegex(ValueError, "symlinked evidence file"):
            validate_inventory(self.root)

    def test_symlinked_scenario_directory_rejected(self):
        import shutil
        old = self.folder("partial")
        target = self.folder("empty")
        shutil.rmtree(old)
        old.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "invalid published scenario"):
            validate_inventory(self.root)

    def test_zero_length_png_and_witness_rejected_but_log_optional(self):
        (self.folder("empty") / "av-before.png").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty required evidence"):
            validate_inventory(self.root)
        (self.folder("empty") / "av-before.png").write_bytes(b"x")
        (self.folder("empty") / "native-av-guest-witness.json").write_bytes(b"")
        self.assertNotEqual(self.cli().returncode, 0)

    def test_reject_missing_or_symlinked_root(self):
        with self.assertRaisesRegex(ValueError, "non-symlink directory"):
            validate_inventory(self.root / "absent")
        link = Path(self.temp.name) / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symlink directory"):
            validate_inventory(link)


if __name__ == "__main__":
    unittest.main()
