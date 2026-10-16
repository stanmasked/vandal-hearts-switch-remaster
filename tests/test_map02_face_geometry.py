"""Regression tests for source face-0 map model/GPU FT4 UV association."""
import struct
import unittest

from tools.compare_map02_variants import EXPECTED_LENGTH, FACE_GFX_OFFSET, RECORD_SIZE
from tools.map02_face_geometry import (
    ACTIVE_HEIGHT, ACTIVE_WIDTH, FACE_COUNT_OFFSET, FACE_TABLE_OFFSET,
    GFX_OFFSET, HEIGHT_OFFSET, SHADE_TABLE_OFFSET, STRIDE,
    compare_face_geometry, decode_face_0, tile_record,
)


def synthetic_maps():
    prs = bytearray(EXPECTED_LENGTH)
    dat = bytearray(EXPECTED_LENGTH)
    corners = [(0, 0, 0), (64, 0, 0), (64, 0, 64), (0, 0, 64)]
    for z, x, p_gfx, d_gfx in ((8, 19, 241, 98), (11, 11, 243, 150)):
        origin = (z * STRIDE + x) * RECORD_SIZE
        for data, gfx in ((prs, p_gfx), (dat, d_gfx)):
            for i, vertex in enumerate(corners):
                struct.pack_into("<hhh", data, origin + i * 8, *vertex)
            struct.pack_into("<h", data, origin + GFX_OFFSET, gfx)
            data[origin + FACE_TABLE_OFFSET:origin + FACE_TABLE_OFFSET + 4] = bytes((0, 1, 2, 3))
            data[origin + SHADE_TABLE_OFFSET] = 4
            data[origin + FACE_COUNT_OFFSET] = 1
            data[origin + HEIGHT_OFFSET] = 6
    return prs, dat


class Map02FaceGeometryTests(unittest.TestCase):
    def test_tile_record_uses_28_wide_storage_not_24_wide_active_grid(self):
        prs, _ = synthetic_maps()
        p = tile_record(prs, 8, 19)
        self.assertEqual(len(p), 304)
        self.assertEqual(struct.unpack_from("<h", p, FACE_GFX_OFFSET)[0], 241)
        self.assertEqual(struct.unpack_from("<h", tile_record(prs, 11, 11),
                                            FACE_GFX_OFFSET)[0], 243)
        self.assertEqual(prs[(8 * 28 + 19) * RECORD_SIZE + 176], 241)

    def test_original_face_vertex_order_maps_to_ft4_uv_correctly(self):
        prs, _ = synthetic_maps()
        result = decode_face_0(prs, 8, 19, (240, 192, 15, 15))
        self.assertEqual(result["local_gfx"], 241)
        self.assertEqual(result["record_index"], 243)
        self.assertEqual(result["face_vertex_indices"], [0, 1, 2, 3])
        self.assertEqual(result["face_shade"], 4)
        self.assertEqual(result["tile_height"], 6)
        self.assertEqual([corner["gpu_corner"] for corner in result["face_corners"]],
                         ["uv0_poly0", "uv1_poly1", "uv3_poly3", "uv2_poly2"])
        self.assertEqual([corner["uv"] for corner in result["face_corners"]],
                         [[240, 192], [255, 192], [255, 207], [240, 207]])
        self.assertEqual([corner["model_xyz"] for corner in result["face_corners"]],
                         [[0, 0, 0], [64, 0, 0], [64, 0, 64], [0, 0, 64]])
        self.assertEqual(result["first_triangle_cross_xyz"], [0, -4096, 0])
        self.assertTrue(result["first_triangle_nonzero_area"])

    def test_prs_dat_same_polygon_different_source_uv_and_material(self):
        prs, dat = synthetic_maps()
        first = compare_face_geometry(
            prs, dat, 8, 19, (240, 192, 15, 15), (64, 96, 15, 15))
        second = compare_face_geometry(
            prs, dat, 11, 11, (240, 208, 15, 15), (224, 128, 15, 15))
        for item, pair in ((first, (241, 98)), (second, (243, 150))):
            self.assertTrue(item["shape_and_other_tile_data_identical"])
            self.assertTrue(item["model_vertex_positions_identical"])
            self.assertFalse(item["uv_corner_positions_identical"])
            self.assertEqual((item["prs_face"]["local_gfx"], item["dat_face"]["local_gfx"]),
                             pair)
            self.assertEqual(item["prs_tile_except_face_gfx_sha256"],
                             item["dat_tile_except_face_gfx_sha256"])

    def test_any_other_geometry_or_shade_mutation_is_not_hidden(self):
        prs, dat = synthetic_maps()
        origin = (8 * STRIDE + 19) * RECORD_SIZE
        for offset in (0, FACE_TABLE_OFFSET + 1, SHADE_TABLE_OFFSET, HEIGHT_OFFSET):
            with self.subTest(offset=offset):
                modified = bytearray(dat)
                modified[origin + offset] ^= 1
                result = compare_face_geometry(
                    prs, modified, 8, 19, (240, 192, 15, 15), (64, 96, 15, 15))
                self.assertFalse(result["shape_and_other_tile_data_identical"])

    def test_16_bit_gfx_is_not_silently_reduced_to_low_byte(self):
        prs, _ = synthetic_maps()
        start = (8 * STRIDE + 19) * RECORD_SIZE + GFX_OFFSET
        prs[start + 1] = 1
        result = decode_face_0(prs, 8, 19, (240, 192, 15, 15))
        self.assertEqual(result["local_gfx"], 497)
        self.assertNotEqual(result["local_gfx"], 241)

    def test_invalid_vertex_index_and_degenerate_faces_are_rejected(self):
        prs, _ = synthetic_maps()
        start = (8 * STRIDE + 19) * RECORD_SIZE
        prs[start + FACE_TABLE_OFFSET] = 22
        with self.assertRaisesRegex(ValueError, "vertex index outside"):
            decode_face_0(prs, 8, 19, (240, 192, 15, 15))
        prs[start + FACE_TABLE_OFFSET:start + FACE_TABLE_OFFSET + 4] = bytes((0, 1, 1, 1))
        with self.assertRaisesRegex(ValueError, "degenerate"):
            decode_face_0(prs, 8, 19, (240, 192, 15, 15))

    def test_invalid_face_count_and_bounds_are_rejected(self):
        prs, _ = synthetic_maps()
        start = (8 * STRIDE + 19) * RECORD_SIZE
        for face_count in (0, 19, 255):
            with self.subTest(count=face_count):
                prs[start + FACE_COUNT_OFFSET] = face_count
                with self.assertRaisesRegex(ValueError, "faceCt"):
                    decode_face_0(prs, 8, 19, (240, 192, 15, 15))
        prs[start + FACE_COUNT_OFFSET] = 1
        for z, x in ((-1, 19), (12, 11), (8, 24), (True, 19)):
            with self.subTest(z=z, x=x):
                with self.assertRaisesRegex(ValueError, "outside active"):
                    tile_record(prs, z, x)
        with self.assertRaisesRegex(ValueError, "shorter than"):
            tile_record(prs[:1000], 8, 19)

    def test_out_of_bounds_uv_wh_are_rejected(self):
        prs, _ = synthetic_maps()
        for bad in ((250, 192, 15, 15), (240, 250, 15, 15),
                    (240, 192, 0, 15), (240, 192, 15, 0),
                    (240, 192, True, 15), (240, 192, 15)):
            with self.subTest(uv=bad):
                with self.assertRaisesRegex(ValueError, "UVWH"):
                    decode_face_0(prs, 8, 19, bad)


if __name__ == "__main__":
    unittest.main()
