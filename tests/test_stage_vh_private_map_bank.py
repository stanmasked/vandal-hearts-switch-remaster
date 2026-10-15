"""No-asset end-to-end tests for private SD staging of map 11 slot 241."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from inspect_vh_map_texture_bank import MAP_RECORD_BYTES  # noqa: E402
from stage_vh_private_map_bank import (  # noqa: E402
    RELATIVE_DESTINATION, stage_private_assets,
)
from test_inspect_vh_map_texture_bank import fixtures  # noqa: E402


def private_fixtures():
    texture, data = fixtures()
    land = bytearray(data)
    start = 11 * MAP_RECORD_BYTES + 241 * 4
    land[start:start + 4] = bytes([240, 192, 15, 15])
    return texture, bytes(land)


class PrivateStagingTests(unittest.TestCase):
    def test_stages_only_local_validated_assets(self):
        texture, land = private_fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = stage_private_assets(texture, land, root)
            location = root / RELATIVE_DESTINATION
            self.assertEqual((location / "F_TEX01.DAT").read_bytes(), texture)
            self.assertEqual((location / "LAND_DT.DAT").read_bytes(), land)
            self.assertEqual(result["uvwh"], [240, 192, 15, 15])
            self.assertEqual(result["local_clut_id"], 35)
            self.assertFalse(result["audited_ru_v1_6_match"])
            self.assertEqual(
                json.loads((location / "source-manifest.json").read_text()),
                result,
            )

    def test_does_not_overwrite_existing_assets(self):
        texture, land = private_fixtures()
        with tempfile.TemporaryDirectory() as directory:
            stage_private_assets(texture, land, directory)
            with self.assertRaises(FileExistsError):
                stage_private_assets(texture, land, directory)

    def test_rejects_wrong_sizes_without_writing(self):
        texture, land = private_fixtures()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "texture bytes"):
                stage_private_assets(texture[:-1], land, directory)
            self.assertFalse((Path(directory) / RELATIVE_DESTINATION).exists())

    def test_sha_strict_mode_rejects_synthetic_assets(self):
        texture, land = private_fixtures()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                stage_private_assets(texture, land, directory, strict_hashes=True)
            self.assertFalse((Path(directory) / RELATIVE_DESTINATION).exists())

    def test_rejects_palette_or_uv_mismatch(self):
        texture, land = private_fixtures()
        base = 11 * MAP_RECORD_BYTES
        with tempfile.TemporaryDirectory() as directory:
            altered = bytearray(land)
            altered[base + 4 * 257 + 241] = 17
            with self.assertRaisesRegex(ValueError, "local LAND_DT"):
                stage_private_assets(texture, bytes(altered), directory)
            altered = bytearray(land)
            altered[base + 241 * 4] = 255
            with self.assertRaisesRegex(ValueError, "UVWH"):
                stage_private_assets(texture, bytes(altered), directory)
            self.assertFalse((Path(directory) / RELATIVE_DESTINATION).exists())


if __name__ == "__main__":
    unittest.main()
