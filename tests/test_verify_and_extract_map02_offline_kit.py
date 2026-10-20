"""A malicious or damaged ZIP must be rejected before any file extraction."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tools.build_map02_intel_mac_offline_kit import bundle
from tools.verify_and_extract_map02_offline_kit import (
    authenticate_zip, verify_and_extract,
)

REPO = Path(__file__).resolve().parent.parent
PUBLIC = os.environ.get("MAP02_PINNED_RASTER")


class SafeMap02PreExtractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLIC:
            raise RuntimeError("public pinned PC raster required")
        cls.session = tempfile.TemporaryDirectory()
        cls.root = Path(cls.session.name)
        cls.good = cls.root / "original.zip"
        cls.correct = bundle(REPO, Path(PUBLIC), cls.good)["zip_sha256"]

    @classmethod
    def tearDownClass(cls):
        cls.session.cleanup()

    def setUp(self):
        self.session_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.session_dir.cleanup)
        self.work = Path(self.session_dir.name)
        self.destination = self.work / "new"
        self.bad = self.work / "altered.zip"

    def rewrite(self, transform):
        with zipfile.ZipFile(self.good) as source:
            files = [(copy.copy(x), source.read(x)) for x in source.infolist()]
        files = transform(files)
        with zipfile.ZipFile(self.bad, "w") as target:
            for info, contents in files:
                target.writestr(info, contents)
        return hashlib.sha256(self.bad.read_bytes()).hexdigest()

    @staticmethod
    def extra_entry(name, data=b"x", mode=0o644):
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = mode << 16
        return info, data

    def test_verified_original_archive_extracts_and_preexec_verifies(self):
        report = verify_and_extract(self.good, self.correct, self.destination)
        self.assertEqual(report["inner_zip_sha256_verified"], self.correct)
        self.assertGreaterEqual(report["validated_files_extracted"], 20)
        self.assertFalse(report["raw_ps1_data_read"])
        self.assertTrue((self.destination / "verify-kit.py").is_file())
        run = subprocess.run(
            [sys.executable, "verify-kit.py", "--root", "."],
            cwd=str(self.destination), capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(run.returncode, 0, run.stderr[:180])
        self.assertIn("file_digests_verified", run.stdout)

    def test_wrong_expected_digest_refuses_without_extraction(self):
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify_and_extract(self.good, "0" * 64, self.destination)
        self.assertFalse(self.destination.exists())

    def test_forged_consistent_archive_refused_by_original_digest(self):
        import json
        def forge(items):
            mapping = {i.filename: (i, v) for i, v in items}
            info, source = mapping["README.md"]
            altered = source + b"\nsynthetic injected material\n"
            mapping["README.md"] = (info, altered)
            i, manifest_bytes = mapping["files.json"]
            manifest = json.loads(manifest_bytes)
            manifest["files"]["README.md"] = hashlib.sha256(altered).hexdigest()
            mapping["files.json"] = (
                i, (json.dumps(manifest, sort_keys=True) + "\n").encode()
            )
            return list(mapping.values())
        forged_digest = self.rewrite(forge)
        self.assertNotEqual(forged_digest, self.correct)
        # Even a ZIP with internally self-consistent digests is untrusted
        # if its independently supplied original checksum disagrees.
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify_and_extract(self.bad, self.correct, self.destination)
        self.assertFalse(self.destination.exists())

    def test_unlisted_executable_refused_even_with_updated_outer_hash(self):
        digest = self.rewrite(
            lambda items: items + [self.extra_entry("tools/evil.py")]
        )
        with self.assertRaisesRegex(ValueError, "manifest"):
            verify_and_extract(self.bad, digest, self.destination)
        self.assertFalse(self.destination.exists())

    def test_zip_slip_path_refused(self):
        digest = self.rewrite(
            lambda items: items + [self.extra_entry("../escaped.py")]
        )
        with self.assertRaisesRegex(ValueError, "unsafe ZIP member"):
            verify_and_extract(self.bad, digest, self.destination)
        self.assertFalse((self.work / "escaped.py").exists())

    def test_duplicate_archive_member_refused(self):
        def duplicate(items):
            info, content = items[0]
            return items + [(copy.copy(info), content)]
        digest = self.rewrite(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            verify_and_extract(self.bad, digest, self.destination)

    def test_symlink_member_refused(self):
        def symlink(items):
            info, content = items[0]
            info.external_attr = (0o120777 << 16)
            return items
        digest = self.rewrite(symlink)
        with self.assertRaisesRegex(ValueError, "mode"):
            verify_and_extract(self.bad, digest, self.destination)

    def test_case_colliding_file_name_refused(self):
        digest = self.rewrite(
            lambda items: items + [
                self.extra_entry("tools/SYNTHETIC.py"),
                self.extra_entry("tools/synthetic.py"),
            ]
        )
        with self.assertRaisesRegex(ValueError, "case-colliding"):
            verify_and_extract(self.bad, digest, self.destination)

    def test_symlinked_zip_input_refused(self):
        link = self.work / "linked.zip"
        link.symlink_to(self.good)
        with self.assertRaisesRegex(ValueError, "unlinked regular"):
            verify_and_extract(link, self.correct, self.destination)

    def test_existing_destination_never_overwritten(self):
        self.destination.mkdir()
        original = self.destination / "sentinel.txt"
        original.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            verify_and_extract(self.good, self.correct, self.destination)
        self.assertEqual(original.read_text(encoding="utf-8"), "keep")

    def test_bad_sha_format_refused(self):
        for value in ("abcd", "A" * 64, "invalid", "", "f" * 65):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "lowercase"):
                    authenticate_zip(self.good, value)


if __name__ == "__main__":
    unittest.main()
