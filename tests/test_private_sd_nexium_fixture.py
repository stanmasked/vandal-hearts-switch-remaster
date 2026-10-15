"""Regression tests for NeXium private SD proof-of-life fixture, no game data."""
import struct
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
from private_sd_nexium_check import (  # noqa: E402
    CLUT_ID, COLORS_BGR555, MAP_NUMBER, MAP_SLOT, SCREEN_SAMPLES,
    U0, V0, synthetic_source, stage,
)
from inspect_vh_map_texture_bank import (  # noqa: E402
    LAND_BYTES, MAP_RECORD_BYTES, TEXTURE_BYTES, inspect_bank,
)
from stage_vh_private_map_bank import RELATIVE_DESTINATION  # noqa: E402


def sample_at(texture, land, u, v):
    record = MAP_NUMBER * MAP_RECORD_BYTES
    selector = land[record + 257 * 4 + MAP_SLOT]
    palette = record + 257 * 5 + (selector - 32) * 32
    packed = texture[v * 128 + u // 2]
    index = (packed >> (4 * (u & 1))) & 0xf
    color = struct.unpack_from("<H", land, palette + index * 2)[0]
    return index, color


class PrivateSdQuadFixtureTests(unittest.TestCase):
    def setUp(self):
        self.texture, self.land = synthetic_source()

    def test_exact_formats_and_authored_slot(self):
        self.assertEqual(len(self.texture), TEXTURE_BYTES)
        self.assertEqual(len(self.land), LAND_BYTES)
        data = inspect_bank(self.texture, self.land, MAP_NUMBER)
        self.assertEqual(data["slot_uvwh"][MAP_SLOT], [240, 192, 15, 15])
        self.assertEqual(data["slot_clut_ids"][MAP_SLOT], 35)
        self.assertEqual(len(SCREEN_SAMPLES), 4)

    def test_independent_u_v_quadrants_and_clut(self):
        cases = (
            (U0, V0, 1, 0x001f),
            (U0 + 7, V0 + 7, 1, 0x001f),
            (U0 + 8, V0, 2, 0x03e0),
            (U0 + 15, V0 + 7, 2, 0x03e0),
            (U0, V0 + 8, 3, 0x7c00),
            (U0 + 7, V0 + 15, 3, 0x7c00),
            (U0 + 8, V0 + 8, 4, 0x03ff),
            (U0 + 15, V0 + 15, 4, 0x03ff),
        )
        for u, v, index, color in cases:
            with self.subTest(u=u, v=v):
                self.assertEqual(
                    sample_at(self.texture, self.land, u, v), (index, color)
                )
        self.assertEqual(COLORS_BGR555, (0, 31, 992, 31744, 1023))
        # The synthetic page uses no raster colors outside the authored UVs.
        self.assertEqual(sample_at(self.texture, self.land, 0, 0), (0, 0))

    def test_selected_fourth_clut_row_is_not_a_default_palette(self):
        record = MAP_NUMBER * MAP_RECORD_BYTES
        palette = record + 257 * 5
        self.assertEqual(self.land[record + 257 * 4 + MAP_SLOT], CLUT_ID)
        self.assertEqual(self.land[palette:palette + 32], bytes(32))
        self.assertEqual(
            struct.unpack_from("<HHHHH", self.land, palette + 3 * 32),
            COLORS_BGR555,
        )

    def test_production_stager_preserves_reference_colors(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = stage(Path(tmp))
            files = Path(tmp) / RELATIVE_DESTINATION
            texture = (files / "F_TEX01.DAT").read_bytes()
            land = (files / "LAND_DT.DAT").read_bytes()
            self.assertEqual(texture, self.texture)
            self.assertEqual(land, self.land)
            self.assertEqual(report["uvwh"], [240, 192, 15, 15])
            self.assertEqual(report["local_clut_id"], CLUT_ID)
            self.assertEqual(sample_at(texture, land, 242, 203),
                             (3, 0x7c00))


if __name__ == "__main__":
    unittest.main()
