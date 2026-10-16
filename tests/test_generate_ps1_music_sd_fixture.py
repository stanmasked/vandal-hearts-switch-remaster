"""Generated SEQ/VH/VB files only; no original game material."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.generate_ps1_music_sd_fixture import (
    AUDIO_RELATIVE, SEQ, make_synthetic_files, populate
)


class SyntheticSDMusicFixtures(unittest.TestCase):
    def test_three_modes_have_distinct_provenance_and_never_imply_audible_music(self):
        files = make_synthetic_files()
        self.assertEqual(len(SEQ), 36)
        self.assertEqual(files["music.seq"][:4], b"pQES")
        self.assertEqual(files["music.vh"][:4], b"pBAV")
        self.assertEqual(len(files["music.vh"]), 3104)
        self.assertEqual(len(files["music.vb"]), 48)
        self.assertEqual(files["music.vb"][16:18], b"\x02\x04")
        for mode, expected in (("empty", "synthetic"),
                               ("full", "user_files"),
                               ("partial", "invalid_or_partial")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                manifest = populate(root, mode)
                self.assertEqual(manifest["expected_audio_source"], expected)
                self.assertFalse(manifest["original_audio_verified"])
                self.assertFalse(manifest["audible_audio_verified"])
                actual = sorted(p.name for p in (root / AUDIO_RELATIVE).iterdir())
                self.assertEqual(actual, sorted(manifest["files_created"]))
                for name in actual:
                    self.assertEqual((root / AUDIO_RELATIVE / name).read_bytes(), files[name])

    def test_existing_music_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / AUDIO_RELATIVE
            path.mkdir(parents=True)
            (path / "music.vh").write_bytes(b"personal data")
            with self.assertRaisesRegex(FileExistsError, "already contains"):
                populate(root, "full")
            self.assertEqual((path / "music.vh").read_bytes(), b"personal data")
            self.assertFalse((path / "music.seq").exists())

    def test_symlinked_sd_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            external = root / "destination"
            external.mkdir()
            (root / "sdmc").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "contains a symlink"):
                populate(root, "full")
            self.assertFalse((external / "switch").exists())

    def test_cli_requires_existing_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            command = [sys.executable, "-m", "tools.generate_ps1_music_sd_fixture",
                       str(root), "--mode", "partial"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["files_created"], ["music.seq"])
            self.assertEqual(report["expected_audout_status"], "unavailable_or_error")


if __name__ == "__main__":
    unittest.main()
