from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.map02_private_disc_parts import (
    SCHEMA,
    join_parts,
    split_image,
)


class PrivateDiscPartsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "fictional-disc.bin"
        self.source.write_bytes(bytes(range(256)) * 41 + b"end-marker")
        self.parts_dir = self.root / "parts"
        self.manifest_path = None

    def tearDown(self):
        self.temp.cleanup()

    def split(self, chunk_size=1024, expected_sha256=None):
        self.manifest_path, manifest = split_image(
            self.source, self.parts_dir, chunk_size, expected_sha256=expected_sha256)
        return manifest

    def test_split_and_join_round_trip(self):
        manifest = self.split()
        self.assertEqual(manifest["schema"], SCHEMA)
        self.assertEqual(manifest["part_count"], 11)
        output_dir = self.root / "joined"
        output_dir.mkdir()
        output = output_dir / self.source.name
        result = join_parts(self.manifest_path, self.parts_dir, output)
        self.assertEqual(result["total_bytes"], self.source.stat().st_size)
        self.assertEqual(output.read_bytes(), self.source.read_bytes())

    def test_split_accepts_expected_sha256(self):
        expected = hashlib.sha256(self.source.read_bytes()).hexdigest()
        manifest = self.split(expected_sha256=expected)
        self.assertEqual(manifest["total_sha256"], expected)

    def test_split_rejects_wrong_expected_sha256_and_cleans_outputs(self):
        with self.assertRaisesRegex(ValueError, "does not match expected private reference"):
            split_image(self.source, self.parts_dir, 1024, expected_sha256="0" * 64)
        self.assertTrue(self.parts_dir.is_dir())
        self.assertEqual(list(self.parts_dir.iterdir()), [])

    def test_split_refuses_overwrite(self):
        self.split()
        with self.assertRaises(FileExistsError):
            split_image(self.source, self.parts_dir, 1024)

    def test_join_rejects_modified_part_and_removes_partial_output(self):
        self.split()
        first_part = self.parts_dir / "fictional-disc.bin.part00"
        first_part.write_bytes(first_part.read_bytes() + b"tamper")
        output_dir = self.root / "joined"
        output_dir.mkdir()
        output = output_dir / self.source.name
        with self.assertRaisesRegex(ValueError, "size or SHA-256 mismatch"):
            join_parts(self.manifest_path, self.parts_dir, output)
        self.assertFalse(output.exists())

    def test_join_rejects_manifest_path_traversal(self):
        self.split()
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        data["parts"][0]["filename"] = "../fictional-disc.bin.part00"
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        output_dir = self.root / "joined"
        output_dir.mkdir()
        with self.assertRaisesRegex(ValueError, "filename is invalid"):
            join_parts(self.manifest_path, self.parts_dir, output_dir / self.source.name)

    def test_split_rejects_chunk_over_connector_limit(self):
        with self.assertRaisesRegex(ValueError, "between 1 byte and 240 MiB"):
            split_image(self.source, self.parts_dir, 241 * 1024 * 1024)

    def test_join_refuses_existing_output(self):
        self.split()
        output_dir = self.root / "joined"
        output_dir.mkdir()
        output = output_dir / self.source.name
        output.write_text("do not overwrite", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            join_parts(self.manifest_path, self.parts_dir, output)
        self.assertEqual(output.read_text(encoding="utf-8"), "do not overwrite")


if __name__ == "__main__":
    unittest.main()
