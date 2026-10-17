"""Preflight exercises fail-closed native MAP02 session isolation."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.preflight_map02_private_dda_capture import preflight

class NativeDdaCapturePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "capture"
        self.root.mkdir(mode=0o700)
        os.chmod(self.root, 0o700)
        self.env = {
            "VH_MAP02_GPU_CAPTURE_DIR": str(self.root),
            "VH_MAP02_PUTPIXEL_DIR": str(self.root),
            "VH_MAP02_GPU_CAPTURE_FRAME": "411",
            "VH_MAP02_PUTPIXEL_FRAME": "411",
            "VH_MAP02_PUTPIXEL_X": "30",
            "VH_MAP02_PUTPIXEL_Y": "30",
        }

    def test_empty_owner_private_synchronized_capture(self):
        output = preflight(self.env)
        self.assertEqual(output["capture_frame"], 411)
        self.assertTrue(output["private_empty_directory"])
        self.assertTrue(output["gpu_and_dda_directory_match"])
        self.assertFalse(output["binary_instrumentation_verified"])
        self.assertFalse(output["gameplay_capture_verified"])
        self.assertFalse(output["hd_replacement_authorized"])
        serial = json.dumps(output)
        self.assertNotIn(str(self.root), serial)
        self.assertNotIn('"30"', serial)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_conflicting_frame_and_capture_dirs(self):
        self.env["VH_MAP02_PUTPIXEL_FRAME"] = "412"
        with self.assertRaisesRegex(ValueError, "frames must match"):
            preflight(self.env)
        self.env["VH_MAP02_PUTPIXEL_FRAME"] = "411"
        second = Path(self.temp.name) / "other"
        second.mkdir(mode=0o700)
        self.env["VH_MAP02_PUTPIXEL_DIR"] = str(second)
        with self.assertRaisesRegex(ValueError, "directories must match"):
            preflight(self.env)

    def test_invalid_coordinates_and_frame(self):
        for key, invalid in (
            ("VH_MAP02_PUTPIXEL_X", "1024"),
            ("VH_MAP02_PUTPIXEL_Y", "512"),
            ("VH_MAP02_PUTPIXEL_X", "-1"),
            ("VH_MAP02_PUTPIXEL_X", "True"),
            ("VH_MAP02_GPU_CAPTURE_FRAME", "0"),
            ("VH_MAP02_GPU_CAPTURE_FRAME", "4294967296"),
            ("VH_MAP02_GPU_CAPTURE_FRAME", "3.0"),
        ):
            with self.subTest(key=key, invalid=invalid):
                other = dict(self.env, **{key: invalid})
                with self.assertRaises(ValueError):
                    preflight(other)

    def test_must_not_use_existing_or_public_directory(self):
        file = self.root / "old-journal.jsonl"
        file.write_text("private\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty"):
            preflight(self.env)
        file.unlink()
        os.chmod(self.root, 0o755)
        with self.assertRaisesRegex(ValueError, "private"):
            preflight(self.env)

    def test_reject_relative_symlink_missing_and_file_paths(self):
        for bad in ("relative/path", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    preflight(dict(self.env, VH_MAP02_GPU_CAPTURE_DIR=bad))
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.root, target_is_directory=True)
        for key in ("VH_MAP02_GPU_CAPTURE_DIR", "VH_MAP02_PUTPIXEL_DIR"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    preflight(dict(self.env, **{key: str(link)}))
        with self.assertRaises(ValueError):
            preflight(dict(self.env, VH_MAP02_GPU_CAPTURE_DIR=str(self.root / "missing")))
        item = Path(self.temp.name) / "file"
        item.write_text("not a directory")
        with self.assertRaises(ValueError):
            preflight(dict(self.env, VH_MAP02_GPU_CAPTURE_DIR=str(item),
                           VH_MAP02_PUTPIXEL_DIR=str(item)))

    def test_absence_of_environment_vars(self):
        for key in tuple(self.env):
            with self.subTest(key=key):
                altered = dict(self.env)
                del altered[key]
                with self.assertRaises(ValueError):
                    preflight(altered)


if __name__ == "__main__":
    unittest.main()
