"""Synthetic multi-cell placement checks; not original-map evidence."""
import struct
import unittest

from tools.map02_face_geometry import (
    RECORD_COUNT, RECORD_SIZE, STRIDE, FACE_TABLE_OFFSET,
    FACE_COUNT_OFFSET, GFX_OFFSET,
)
from tools.map02_multicell_probe import place_faces, shared_vertices


def fixture():
    data = bytearray(RECORD_COUNT * RECORD_SIZE)
    for z, x in ((2, 3), (2, 4), (3, 3)):
        off = (z * STRIDE + x) * RECORD_SIZE
        for i, p in enumerate(((0, 0, 0), (64, 0, 0),
                               (64, 0, 64), (0, 0, 64))):
            struct.pack_into("<hhh", data, off + i * 8, *p)
        data[off + FACE_TABLE_OFFSET:off + FACE_TABLE_OFFSET + 4] = bytes(range(4))
        data[off + FACE_COUNT_OFFSET] = 1
        struct.pack_into("<h", data, off + GFX_OFFSET, 241)
    return data


class MultiCellTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.cells = [(2, 3), (2, 4), (3, 3)]
        self.uv = {key: (0, 0, 15, 15) for key in self.cells}

    def test_neighbor_edges_and_diagonal_corner(self):
        faces = place_faces(self.data, self.cells, self.uv,
                            step_x=64, step_z=64)
        self.assertEqual([f["record_index"] for f in faces],
                         [2 * 28 + 3, 2 * 28 + 4, 3 * 28 + 3])
        self.assertEqual(shared_vertices(faces[0], faces[1]),
                         [[256, 0, 128], [256, 0, 192]])
        self.assertEqual(shared_vertices(faces[0], faces[2]),
                         [[192, 0, 192], [256, 0, 192]])
        self.assertEqual(shared_vertices(faces[1], faces[2]),
                         [[256, 0, 192]])
        self.assertEqual(self.data, fixture())

    def test_incorrect_step_exposes_seam_mismatch(self):
        faces = place_faces(self.data, self.cells[:2], self.uv,
                            step_x=65, step_z=64)
        self.assertEqual(shared_vertices(*faces), [])

    def test_signed_axis_and_local_height_remain_explicit(self):
        faces = place_faces(self.data, self.cells[:2], self.uv,
                            step_x=-64, step_z=64)
        self.assertEqual(faces[0]["grid_offset_xyz"], [-192, 0, 128])
        self.assertEqual(shared_vertices(*faces), [])

    def test_duplicate_invalid_steps_and_missing_uv(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            place_faces(self.data, [self.cells[0]] * 2, self.uv,
                        step_x=64, step_z=64)
        for step in (0, True, 64.0):
            with self.subTest(step=step):
                with self.assertRaisesRegex(ValueError, "grid steps"):
                    place_faces(self.data, self.cells, self.uv,
                                step_x=step, step_z=64)
        with self.assertRaises(KeyError):
            place_faces(self.data, self.cells, {}, step_x=64, step_z=64)

    def test_degenerate_source_face_does_not_turn_into_seam_proof(self):
        data = fixture()
        off = (2 * STRIDE + 3) * RECORD_SIZE
        data[off + FACE_TABLE_OFFSET:off + FACE_TABLE_OFFSET + 4] = bytes((0, 1, 1, 1))
        with self.assertRaisesRegex(ValueError, "degenerate"):
            place_faces(data, self.cells, self.uv, step_x=64, step_z=64)


if __name__ == "__main__":
    unittest.main()
