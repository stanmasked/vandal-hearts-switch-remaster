"""Synthetic, asset-free tests for unpacked original MapTileModel slabs."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_vh_map_geometry import (  # noqa: E402
    TILE_BYTES, MAP_11_BYTES, MAP_11_STRIDE, MAP_11_ROWS,
    VERTICES_BYTES, GFX_BYTES, FACE_BYTES, parse_tile,
    attach_land_uv_faces,
)
from inspect_vh_map_texture_bank import (  # noqa: E402
    LAND_BYTES, MAP_RECORD_BYTES, SLOT_COUNT,
)

X, Z = 6, 3
UVWH = (240, 192, 15, 15)


def fixture(gfx=241, clut=35):
    models = bytearray(MAP_11_BYTES)
    base = (Z * MAP_11_STRIDE + X) * TILE_BYTES
    corners = (
        (-16, 0, -16, 0),
        (16, 0, -16, 0),
        (-16, 0, 16, 0),
        (16, 0, 16, 0),
    )
    for i, vertex in enumerate(corners):
        struct.pack_into("<hhhh", models, base + 8 * i, *vertex)
    struct.pack_into("<h", models, base + VERTICES_BYTES, gfx)
    face = base + VERTICES_BYTES + GFX_BYTES
    models[face:face + 4] = bytes((0, 1, 2, 3))
    shade = base + VERTICES_BYTES + GFX_BYTES + FACE_BYTES
    models[shade] = 6
    models[base + TILE_BYTES - 2] = 1
    models[base + TILE_BYTES - 1] = 7
    land = bytearray(LAND_BYTES)
    record = 11 * MAP_RECORD_BYTES
    land[record + 4 * 241:record + 4 * 241 + 4] = bytes(UVWH)
    land[record + 4 * SLOT_COUNT + 241] = clut
    return models, land


class UnpackedMapGeometryTests(unittest.TestCase):
    def test_original_map_model_layout_is_304_bytes(self):
        self.assertEqual(TILE_BYTES, 304)
        self.assertEqual(MAP_11_STRIDE, 28)
        self.assertEqual(MAP_11_ROWS, 12)
        self.assertEqual(MAP_11_BYTES, 102144)
        self.assertEqual(
            22 * 8 + 18 * 2 + 18 * 4 + 18 + 2,
            TILE_BYTES,
        )

    def test_face_vertex_order_graphics_and_shade(self):
        models, _ = fixture()
        tile = parse_tile(models, X, Z)
        self.assertEqual(tile["face_count"], 1)
        self.assertEqual(tile["tile_height"], 7)
        self.assertTrue(tile["within_active_width"])
        face = tile["faces"][0]
        self.assertEqual(face["local_gfx_slot"], 241)
        self.assertEqual(face["shade_index"], 6)
        self.assertTrue(face["textured"])
        self.assertEqual(face["vertex_indices"], [0, 1, 2, 3])
        self.assertEqual(face["vertex_xyz"], [
            [-16, 0, -16], [16, 0, -16],
            [-16, 0, 16], [16, 0, 16],
        ])

    def test_attach_authored_uv_and_selected_local_clut(self):
        models, land = fixture()
        tile = attach_land_uv_faces(parse_tile(models, X, Z), land)
        face = tile["faces"][0]
        self.assertEqual(face["uvwh"], list(UVWH))
        self.assertEqual(face["clut_selector"], 35)
        self.assertEqual(face["local_clut_row"], 3)
        self.assertTrue(face["fully_mapped_by_local_land_palette"])

    def test_external_clut_is_not_falsely_mapped_locally(self):
        models, land = fixture(clut=17)
        face = attach_land_uv_faces(parse_tile(models, X, Z), land)["faces"][0]
        self.assertEqual(face["clut_selector"], 17)
        self.assertIsNone(face["local_clut_row"])
        self.assertFalse(face["fully_mapped_by_local_land_palette"])

    def test_empty_tile_and_padding_column(self):
        models, _ = fixture()
        self.assertEqual(parse_tile(models, 0, 0)["face_count"], 0)
        self.assertFalse(parse_tile(models, 27, 0)["within_active_width"])

    def test_reject_truncated_or_compressed_prs_input(self):
        models, _ = fixture()
        for data in (models[:-1], models + bytes(1), bytes((0x18, 0, 0, 0))):
            with self.subTest(n=len(data)):
                with self.assertRaisesRegex(ValueError, "unpacked"):
                    parse_tile(data, X, Z)

    def test_reject_invalid_tile_coordinates(self):
        models, _ = fixture()
        for x, z in ((-1, Z), (MAP_11_STRIDE, Z), (X, -1),
                     (X, MAP_11_ROWS)):
            with self.subTest(x=x, z=z):
                with self.assertRaisesRegex(ValueError, "coordinates"):
                    parse_tile(models, x, z)

    def test_reject_overfull_face_count(self):
        models, _ = fixture()
        base = (Z * MAP_11_STRIDE + X) * TILE_BYTES
        models[base + TILE_BYTES - 2] = 19
        with self.assertRaisesRegex(ValueError, "faceCt"):
            parse_tile(models, X, Z)

    def test_reject_oob_face_vertex_index(self):
        models, _ = fixture()
        base = (Z * MAP_11_STRIDE + X) * TILE_BYTES
        models[base + VERTICES_BYTES + GFX_BYTES + 2] = 22
        with self.assertRaisesRegex(ValueError, "vertex"):
            parse_tile(models, X, Z)

    def test_reject_corrupt_land(self):
        models, land = fixture()
        for data in (land[:-1], land + bytes(1)):
            with self.subTest(n=len(data)):
                with self.assertRaisesRegex(ValueError, "LAND_DT"):
                    attach_land_uv_faces(parse_tile(models, X, Z), data)

    def test_unmapped_negative_local_gfx_is_not_misidentified_as_slot(self):
        models, land = fixture(gfx=-1)
        face = attach_land_uv_faces(parse_tile(models, X, Z), land)["faces"][0]
        self.assertIsNone(face["uv_slot_in_land_dt"])
        self.assertNotIn("uvwh", face)


if __name__ == "__main__":
    unittest.main()
