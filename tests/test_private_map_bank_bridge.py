"""Proves Python staging and Switch-native C loader agree byte-for-byte.

All inputs are generated in memory; never copies PlayStation game assets into CI.
Compile host verifier first, then pass its path as the sole argument.
"""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_vh_map_texture_bank import (  # noqa: E402
    LAND_BYTES, MAP_RECORD_BYTES, TEXTURE_BYTES,
)
from stage_vh_private_map_bank import (  # noqa: E402
    RELATIVE_DESTINATION, stage_private_assets,
)


def make_fixture():
    tex = bytearray(TEXTURE_BYTES)
    land = bytearray(LAND_BYTES)
    map_base = 11 * MAP_RECORD_BYTES
    slot = 241
    uv = map_base + 4 * slot
    clut = map_base + 4 * 257 + slot
    row3 = map_base + 5 * 257 + 3 * 16 * 2
    land[uv:uv + 4] = bytes((240, 192, 15, 15))
    land[clut] = 35
    struct.pack_into("<HHH", land, row3, 0, 0x001f, 0x03e0)
    # x240=palette index 1 (red), x241=palette index 2 (green).
    tex[192 * 128 + 240 // 2] = 0x21
    return bytes(tex), bytes(land)


def invoke(loader, texture, land):
    output = subprocess.check_output(
        [str(loader), str(texture), str(land)], text=True,
        timeout=10,
    )
    return dict(line.strip().split("=", 1) for line in output.splitlines())


class CPrivateMapBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if len(sys.argv) < 2:
            raise ValueError("pass prebuilt C bridge binary after test script")
        cls.loader = Path(sys.argv[1]).resolve()

    def test_private_local_staging_c_loader_and_pixel_sample(self):
        texture, land = make_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = stage_private_assets(texture, land, root)
            files = root / RELATIVE_DESTINATION
            values = invoke(
                self.loader,
                files / "F_TEX01.DAT",
                files / "LAND_DT.DAT",
            )
            self.assertEqual(values["status"], "1")
            self.assertEqual(values["uvwh"], "240,192,15,15")
            self.assertEqual(values["clut"], "35")
            self.assertEqual(values["indexes"], "1,2")
            self.assertEqual(values["colors"], "001f,03e0")
            self.assertEqual(manifest["local_clut_id"], 35)
            self.assertEqual(manifest["uvwh"], [240, 192, 15, 15])
            self.assertEqual(
                json.loads((files / "source-manifest.json").read_text()),
                manifest,
            )

    def test_neither_file_then_partial_pair(self):
        texture, land = make_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            t = root / "F_TEX01.DAT"
            l = root / "LAND_DT.DAT"
            self.assertEqual(invoke(self.loader, t, l)["status"], "0")
            t.write_bytes(texture)
            self.assertEqual(invoke(self.loader, t, l)["status"], "-1")
            l.write_bytes(land)
            self.assertEqual(invoke(self.loader, t, l)["status"], "1")
            t.unlink()
            self.assertEqual(invoke(self.loader, t, l)["status"], "-1")

    def test_bad_size_and_selector_are_rejected_by_native_code(self):
        texture, land = make_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            t = root / "F_TEX01.DAT"
            l = root / "LAND_DT.DAT"
            t.write_bytes(texture[:-1])
            l.write_bytes(land)
            self.assertEqual(invoke(self.loader, t, l)["status"], "-1")
            t.write_bytes(texture)
            wrong = bytearray(land)
            wrong[11 * MAP_RECORD_BYTES + 4 * 257 + 241] = 31
            l.write_bytes(wrong)
            self.assertEqual(invoke(self.loader, t, l)["status"], "-1")


if __name__ == "__main__":
    # unittest uses sys.argv as test labels unless the verifier is removed.
    bridge = sys.argv[1] if len(sys.argv) > 1 else None
    sys.argv = [sys.argv[0]]
    if bridge is not None:
        CPrivateMapBridgeTests.loader = Path(bridge).resolve()
    unittest.main()
