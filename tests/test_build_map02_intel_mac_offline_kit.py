"""Public-only Intel Mac kit packaging, stable bytes and safe closure."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.build_map02_intel_mac_offline_kit import (
    PUBLIC_NAME, SCHEMA, bundle, checked_member, source_closure,
)

REPO = Path(__file__).resolve().parent.parent
RASTER = os.environ.get("MAP02_PINNED_RASTER")


class Map02OfflineKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RASTER:
            raise RuntimeError("MAP02_PINNED_RASTER must name the pinned PUBLIC PC raster")

    def test_reject_unsafe_member_and_unreviewed_file_type(self):
        for bad in (
            "", "/tmp/private.bin", "tests/../source/main.c",
            "source/main.c", "assets/secret.png", "tests/image.bin",
            "tools/private.dat", r"tests\escape.py", "tests/subdir/../../bad.py",
        ):
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    checked_member(bad)

    def test_dependency_closure_has_only_code_not_original_game_files(self):
        closure = source_closure(REPO)
        for necessary in (
            "tools/map02_intel_mac_offline_selfcheck.py",
            "tools/map02_catalina_helper_macho_audit.py",
            "tools/verify_map02_private_pc_native_ft4.py",
            "tests/test_map02_private_ft4_cli_mutations.py",
            "tests/test_verify_map02_timeline_native_ft4_join.py",
            "tests/test_map02_vram4_frame.c",
            "source/map02_vram4_frame.h",
            "source/map02_vram4_page.h",
        ):
            self.assertIn(necessary, closure)
        self.assertNotIn("source/main.c", closure)
        for name, data in closure.items():
            self.assertEqual(checked_member(name), name)
            self.assertNotIn(b"\0", data)
            self.assertFalse(any(x in name.lower() for x in (
                ".bin", ".cue", ".iso", ".png", ".jpg", "rom", "shader.bin",
            )))

    def test_reproducible_public_only_package_and_every_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "kit-1.zip"
            second = Path(directory) / "kit-2.zip"
            a = bundle(REPO, Path(RASTER), first)
            b = bundle(REPO, Path(RASTER), second)
            self.assertEqual(a["schema"], SCHEMA)
            self.assertEqual(a["zip_sha256"], b["zip_sha256"])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertFalse(a["private_data_included"])
            self.assertFalse(a["original_ps1_assets_included"])
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertEqual(len(names), len(set(names)))
                manifest = json.loads(archive.read("files.json"))
                self.assertEqual(manifest["schema"], SCHEMA)
                self.assertFalse(manifest["retail_assets_included"])
                self.assertEqual(
                    manifest["public_pc_raster_git_blob_sha1"],
                    "ba8a05d161ad778c0b75e452ff0a11ed163c65cd",
                )
                self.assertIn(PUBLIC_NAME, names)
                self.assertIn("run-selfcheck.sh", names)
                for name, expected in manifest["files"].items():
                    self.assertIn(name, names)
                    self.assertEqual(
                        hashlib.sha256(archive.read(name)).hexdigest(), expected
                    )
                self.assertNotIn("source/main.c", names)
                runner = archive.read("run-selfcheck.sh").decode()
                self.assertIn("--deployment-target 10.15", runner)
                self.assertNotIn("curl ", runner)
                self.assertNotIn("wget ", runner)
                self.assertNotIn("git clone", runner)

    def test_refuses_modified_public_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "pc_raster.c"
            bad.write_bytes(Path(RASTER).read_bytes() + b"\n/* modified */\n")
            with self.assertRaises(ValueError):
                bundle(REPO, bad, Path(directory) / "not-created.zip")

    def test_refuses_output_under_repo_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "already.zip"
            target.write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                bundle(REPO, Path(RASTER), target)
            with self.assertRaisesRegex(ValueError, "inside source"):
                bundle(REPO, Path(RASTER), REPO / "offline-kit-not-created.zip")


if __name__ == "__main__":
    unittest.main()
