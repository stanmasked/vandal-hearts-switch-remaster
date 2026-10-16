"""Synthetic multi-cell placement checks; not original-map evidence."""
import struct
import unittest

from tools.map02_face_geometry import (
    RECORD_COUNT, RECORD_SIZE, STRIDE, FACE_TABLE_OFFSET,
    FACE_COUNT_OFFSET, GFX_OFFSET,
)
from tools.map02_multicell_probe import (
    place_faces, shared_vertices, shared_edges, boundary_report,
    face_cross_xyz, placement_invariants, order_faces_by_external_otz,
    bind_gte_face_samples,
)


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
        self.assertEqual(shared_vertices(*faces),
                         [[-192, 0, 128], [-192, 0, 192]])

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


    def test_exact_shared_edge_and_boundary_incidence(self):
        faces = place_faces(self.data, self.cells, self.uv,
                            step_x=64, step_z=64)
        self.assertEqual(shared_edges(faces[0], faces[1]),
                         [[[256, 0, 128], [256, 0, 192]]])
        self.assertEqual(shared_edges(faces[0], faces[2]),
                         [[[192, 0, 192], [256, 0, 192]]])
        self.assertEqual(shared_edges(faces[1], faces[2]), [])
        self.assertEqual(boundary_report(faces), {
            "outer_edges": 8, "paired_edges": 2,
            "nonmanifold_edges": 0, "edge_count": 10,
        })

    def test_height_mismatch_is_not_a_shared_3d_edge(self):
        data = fixture()
        off = (2 * STRIDE + 4) * RECORD_SIZE
        for i in range(4):
            struct.pack_into("<h", data, off + i * 8 + 2, 16)
        faces = place_faces(data, self.cells[:2], self.uv,
                            step_x=64, step_z=64)
        self.assertEqual(shared_edges(*faces), [])
        self.assertEqual(shared_vertices(*faces), [])
        self.assertEqual(boundary_report(faces)["outer_edges"], 8)

    def test_reverse_winding_preserves_shared_edge(self):
        data = fixture()
        off = (2 * STRIDE + 4) * RECORD_SIZE
        data[off + FACE_TABLE_OFFSET:off + FACE_TABLE_OFFSET + 4] = bytes((3, 2, 1, 0))
        faces = place_faces(data, self.cells[:2], self.uv,
                            step_x=64, step_z=64)
        self.assertEqual(shared_edges(*faces),
                         [[[256, 0, 128], [256, 0, 192]]])

    def test_three_overlapping_copies_are_nonmanifold(self):
        one = place_faces(self.data, self.cells[:1], self.uv,
                          step_x=64, step_z=64)[0]
        self.assertEqual(boundary_report([one, one, one])["nonmanifold_edges"], 4)


    def test_translation_preserves_face_cross_uv_and_vertex_order(self):
        faces = place_faces(self.data, self.cells, self.uv,
                            step_x=64, step_z=64)
        for face in faces:
            with self.subTest(cell=(face["z"], face["x"])):
                audit = placement_invariants(face)
                self.assertTrue(audit["translation_exact"])
                self.assertTrue(audit["cross_preserved"])
                self.assertEqual(audit["local_cross_xyz"], [0, -4096, 0])
                self.assertEqual(audit["placed_cross_xyz"], [0, -4096, 0])
                self.assertEqual(audit["vertex_indices"], [0, 1, 2, 3])
                self.assertEqual(audit["gpu_corners"],
                                 ["uv0_poly0", "uv1_poly1",
                                  "uv3_poly3", "uv2_poly2"])
                self.assertEqual(audit["uv_corners"],
                                 [[0, 0], [15, 0], [15, 15], [0, 15]])

    def test_negative_steps_preserve_cross_and_uv(self):
        face = place_faces(self.data, self.cells[:1], self.uv,
                           step_x=-64, step_z=-128)[0]
        audit = placement_invariants(face)
        self.assertTrue(audit["translation_exact"])
        self.assertTrue(audit["cross_preserved"])

    def test_mutated_world_coordinate_is_detected(self):
        face = place_faces(self.data, self.cells[:1], self.uv,
                           step_x=64, step_z=64)[0]
        face["world_xyz_hypothesis"][2][1] += 1
        audit = placement_invariants(face)
        self.assertFalse(audit["translation_exact"])
        self.assertFalse(audit["cross_preserved"])

    def test_cross_product_rejects_invalid_shape(self):
        with self.assertRaisesRegex(ValueError, "four XYZ"):
            face_cross_xyz([[0, 0, 0]])


    def test_external_otz_is_attached_without_projection_guess(self):
        faces = place_faces(self.data, self.cells, self.uv,
                            step_x=64, step_z=64)
        measurements = {(2, 3): 900, (2, 4): 100, (3, 3): 900}
        ordered = order_faces_by_external_otz(faces, measurements)
        self.assertEqual([(f["z"], f["x"], f["otz"]) for f in ordered],
                         [(2, 4, 100), (2, 3, 900), (3, 3, 900)])
        self.assertEqual([f["input_order"] for f in ordered], [1, 0, 2])
        self.assertEqual([f["record_index"] for f in ordered], [60, 59, 87])

    def test_external_otz_requires_complete_valid_measurements(self):
        faces = place_faces(self.data, self.cells[:2], self.uv,
                            step_x=64, step_z=64)
        for bad in ({}, {(2, 3): 1, (2, 4): 2, (9, 9): 3}):
            with self.subTest(measurements=bad):
                with self.assertRaisesRegex(ValueError, "match placed"):
                    order_faces_by_external_otz(faces, bad)
        for value in (-1, 65536, True, 1.25):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "unsigned 16-bit"):
                    order_faces_by_external_otz(
                        faces, {(2, 3): value, (2, 4): 0})
        with self.assertRaisesRegex(ValueError, "duplicate cell"):
            order_faces_by_external_otz(
                [faces[0], faces[0]], {(2, 3): 10})


    def test_sample_binding_preserves_source_face_provenance(self):
        faces = place_faces(self.data, self.cells[:2], self.uv,
                            step_x=64, step_z=64)
        keys = [(2, 3, 59, 0), (2, 4, 60, 0)]
        bound = bind_gte_face_samples(faces, {
            keys[0]: {"otz": 65535}, keys[1]: {"otz": 0}
        })
        self.assertEqual([b["source_key"] for b in bound],
                         [[2, 3, 59, 0], [2, 4, 60, 0]])
        self.assertEqual([b["otz"] for b in bound], [65535, 0])
        self.assertEqual([b["local_gfx"] for b in bound], [241, 241])

    def test_sample_binding_rejects_wrong_record_or_face(self):
        faces = place_faces(self.data, self.cells[:1], self.uv,
                            step_x=64, step_z=64)
        valid = (2, 3, 59, 0)
        for key in ((2, 3, 60, 0), (2, 3, 59, 1)):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "match source"):
                    bind_gte_face_samples(faces, {key: {"otz": 12}})
        for sample in ({"otz": True}, {"otz": -1},
                       {"otz": 65536}, {"otz": 2.5}):
            with self.subTest(sample=sample):
                with self.assertRaisesRegex(ValueError, "unsigned 16-bit"):
                    bind_gte_face_samples(faces, {valid: sample})
        with self.assertRaisesRegex(ValueError, "only captured"):
            bind_gte_face_samples(faces, {valid: {"otz": 12, "xy": []}})
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            bind_gte_face_samples([faces[0], faces[0]], {valid: {"otz": 12}})
        faces[0]["record_index"] += 1
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            bind_gte_face_samples(faces, {valid: {"otz": 12}})


if __name__ == "__main__":
    unittest.main()
