"""Preflight exercises fail-closed native MAP02 session isolation."""
import json
import hashlib
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

    def test_optional_executable_identity_is_read_only_and_not_attestation(self):
        executable = Path(self.temp.name) / "pcport-game"
        contents = b"test-native-pcport-binary\\x00" * 17
        executable.write_bytes(contents)
        executable.chmod(0o700)
        first = preflight(self.env, executable=executable)
        self.assertTrue(first["executable_fingerprinted"])
        self.assertEqual(first["executable_sha256"], hashlib.sha256(contents).hexdigest())
        self.assertEqual(first["executable_bytes"], len(contents))
        self.assertFalse(first["binary_instrumentation_verified"])
        self.assertFalse(first["gameplay_capture_verified"])
        self.assertFalse(first["hd_replacement_authorized"])
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertNotIn(str(executable), json.dumps(first))
        executable.write_bytes(contents + b"changed")
        second = preflight(self.env, executable=executable)
        self.assertNotEqual(first["executable_sha256"], second["executable_sha256"])
        no_executable = preflight(self.env)
        self.assertFalse(no_executable["executable_fingerprinted"])
        self.assertIsNone(no_executable["executable_sha256"])
        self.assertIsNone(no_executable["executable_bytes"])

    def test_executable_requires_regular_executable_not_a_symlink(self):
        executable = Path(self.temp.name) / "pcport-game"
        executable.write_bytes(b"native")
        executable.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "regular executable"):
            preflight(self.env, executable=executable)
        executable.chmod(0o700)
        link = Path(self.temp.name) / "linked-pcport"
        link.symlink_to(executable)
        with self.assertRaisesRegex(ValueError, "symlink"):
            preflight(self.env, executable=link)
        with self.assertRaises(ValueError):
            preflight(self.env, executable=Path(self.temp.name) / "missing")
        with self.assertRaises(ValueError):
            preflight(self.env, executable=self.root)
        executable.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "nonempty"):
            preflight(self.env, executable=executable)

    def test_fifo_executable_rejected_without_blocking(self):
        executable = Path(self.temp.name) / "synthetic-named-pipe-executable"
        os.mkfifo(executable, 0o700)
        with self.assertRaisesRegex(ValueError, "regular executable"):
            preflight(self.env, executable=executable)

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

    def test_two_word_capture_requires_distinct_complete_bounded_coordinates(self):
        # The two-word C recorder silently disables logging unless X2/Y2
        # are both valid and differ from the first point. Fail *before*
        # launching the private PC executable, without leaking positions.
        selected = dict(self.env,
                        VH_MAP02_PUTPIXEL_X2="35",
                        VH_MAP02_PUTPIXEL_Y2="35")
        ready = preflight(selected)
        self.assertTrue(ready["sample_coordinate_in_vram"])
        self.assertEqual(ready["schema"], "map02_private_native_dda_preflight_v1")
        self.assertFalse(ready["gameplay_capture_verified"])
        self.assertNotIn('"35"', json.dumps(ready))
        self.assertEqual(list(self.root.iterdir()), [])

        for missing in ("VH_MAP02_PUTPIXEL_X2", "VH_MAP02_PUTPIXEL_Y2"):
            altered = dict(selected)
            del altered[missing]
            with self.subTest(missing=missing):
                with self.assertRaisesRegex(ValueError, "ASCII decimal"):
                    preflight(altered)
        for key, value in (
            ("VH_MAP02_PUTPIXEL_X2", "1024"),
            ("VH_MAP02_PUTPIXEL_Y2", "512"),
            ("VH_MAP02_PUTPIXEL_X2", "-1"),
            ("VH_MAP02_PUTPIXEL_Y2", "3.0"),
            ("VH_MAP02_PUTPIXEL_X2", ""),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    preflight(dict(selected, **{key: value}))
        same = dict(selected,
                    VH_MAP02_PUTPIXEL_X2="30",
                    VH_MAP02_PUTPIXEL_Y2="30")
        with self.assertRaisesRegex(ValueError, "must differ"):
            preflight(same)
        # Same X with different Y, or same Y with different X, is fine.
        self.assertTrue(preflight(dict(
            selected, VH_MAP02_PUTPIXEL_X2="30"))["sample_coordinate_in_vram"])
        self.assertTrue(preflight(dict(
            selected, VH_MAP02_PUTPIXEL_Y2="30"))["sample_coordinate_in_vram"])

    def test_git_worktree_markers_block_private_native_capture_preflight(self):
        # Unlike the public synthetic CI files, private GPU/VRAM logs must
        # never be captured under a Git checkout, even with owner-only 0700
        # output permissions. Linked worktrees use a .git FILE.
        parent = self.root.parent
        marker = parent / ".git"
        for kind in ("directory", "linked-worktree-file"):
            with self.subTest(kind=kind):
                if kind == "directory":
                    marker.mkdir(mode=0o700)
                else:
                    marker.write_text(
                        "gitdir: /private/linked-worktree\\n", encoding="utf-8")
                try:
                    with self.assertRaisesRegex(
                            ValueError, "Git worktree") as caught:
                        preflight(self.env)
                    self.assertNotIn(str(parent), str(caught.exception))
                    self.assertEqual(list(self.root.iterdir()), [])
                finally:
                    if marker.is_dir():
                        marker.rmdir()
                    else:
                        marker.unlink()
        # Also refuse hidden worktree metadata *inside* a literal or
        # resolved parent without publishing a private capture.
        hidden = parent / ".git"
        hidden.mkdir(mode=0o700)
        try:
            nested = parent / "secondary" / "capture"
            nested.mkdir(parents=True, mode=0o700)
            nested.chmod(0o700)
            env = dict(self.env,
                       VH_MAP02_GPU_CAPTURE_DIR=str(nested),
                       VH_MAP02_PUTPIXEL_DIR=str(nested))
            with self.assertRaisesRegex(ValueError, "Git worktree"):
                preflight(env)
            self.assertEqual(list(nested.iterdir()), [])
        finally:
            hidden.rmdir()

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

    def test_raw_env_directory_path_must_fit_fixed_c_buffer(self):
        # Path.resolve() hides many "/." components; snprintf() does not.
        long_alias = str(self.root) + "/." * 600
        self.assertEqual(Path(long_alias).resolve(), self.root)
        for key in ("VH_MAP02_GPU_CAPTURE_DIR", "VH_MAP02_PUTPIXEL_DIR"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "recorder buffer"):
                    preflight(dict(self.env, **{key: long_alias}))

    def test_absence_of_environment_vars(self):
        for key in tuple(self.env):
            with self.subTest(key=key):
                altered = dict(self.env)
                del altered[key]
                with self.assertRaises(ValueError):
                    preflight(altered)


if __name__ == "__main__":
    unittest.main()
