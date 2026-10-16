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
    bind_gte_face_samples, place_selected_faces, audit_multicell_gte_batch, bind_external_screen_corners,
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


    def test_two_faces_same_cell_keep_distinct_gfx_shade_and_gte(self):
        data = fixture()
        off = (2 * STRIDE + 3) * RECORD_SIZE
        data[off + FACE_COUNT_OFFSET] = 2
        data[off + FACE_TABLE_OFFSET + 4:off + FACE_TABLE_OFFSET + 8] = bytes((3, 2, 1, 0))
        struct.pack_into("<h", data, off + GFX_OFFSET + 2, 497)
        data[off + 284] = 7
        data[off + 285] = 19
        keys = [(2, 3, 0), (2, 3, 1)]
        faces = place_selected_faces(data, keys, {
            keys[0]: (0, 0, 15, 15), keys[1]: (16, 32, 15, 15)
        }, step_x=64, step_z=64)
        self.assertEqual([f["source_face"]["face"] for f in faces], [0, 1])
        self.assertEqual([f["source_face"]["local_gfx"] for f in faces], [241, 497])
        self.assertEqual([f["source_face"]["face_shade"] for f in faces], [7, 19])
        self.assertEqual(faces[1]["source_face"]["face_vertex_indices"], [3, 2, 1, 0])
        self.assertEqual(faces[1]["source_face"]["face_corners"][0]["uv"], [16, 32])
        bound = bind_gte_face_samples(faces, {
            (2, 3, 59, 0): {"otz": 12}, (2, 3, 59, 1): {"otz": 29}
        })
        self.assertEqual([b["otz"] for b in bound], [12, 29])
        self.assertEqual([b["source_key"][-1] for b in bound], [0, 1])
        for face in faces:
            self.assertTrue(placement_invariants(face)["cross_preserved"])

    def test_selected_faces_reject_duplicate_or_out_of_count(self):
        data = fixture()
        key = (2, 3, 0)
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            place_selected_faces(data, [key, key], {key: (0, 0, 15, 15)},
                                 step_x=64, step_z=64)
        bad = (2, 3, 1)
        with self.assertRaisesRegex(ValueError, "face index outside"):
            place_selected_faces(data, [bad], {bad: (0, 0, 15, 15)},
                                 step_x=64, step_z=64)
        with self.assertRaisesRegex(ValueError, "grid steps"):
            place_selected_faces(data, [key], {key: (0, 0, 15, 15)},
                                 step_x=0, step_z=64)


    def test_all_18_face_slots_have_distinct_material_shade_and_depth(self):
        data = fixture()
        origin = (2 * STRIDE + 3) * RECORD_SIZE
        data[origin + FACE_COUNT_OFFSET] = 18
        selections = [(2, 3, i) for i in range(18)]
        uv = {}
        samples = {}
        for i in range(18):
            indices = (0, 1, 2, 3) if i % 2 == 0 else (3, 2, 1, 0)
            data[origin + FACE_TABLE_OFFSET + i * 4:
                 origin + FACE_TABLE_OFFSET + (i + 1) * 4] = bytes(indices)
            struct.pack_into("<h", data, origin + GFX_OFFSET + 2 * i, 300 + i)
            data[origin + 284 + i] = 20 + i
            uv[(2, 3, i)] = (i * 12, 0, 11, 15)
            samples[(2, 3, 59, i)] = {"otz": 1000 + i}
        faces = place_selected_faces(data, selections, uv, step_x=64, step_z=64)
        self.assertEqual(len(faces), 18)
        self.assertEqual([f["source_face"]["local_gfx"] for f in faces],
                         list(range(300, 318)))
        self.assertEqual([f["source_face"]["face_shade"] for f in faces],
                         list(range(20, 38)))
        self.assertEqual([f["source_face"]["face"] for f in faces],
                         list(range(18)))
        self.assertEqual(
            [f["source_face"]["face_corners"][0]["uv"][0] for f in faces],
            [i * 12 for i in range(18)])
        bound = bind_gte_face_samples(faces, samples)
        self.assertEqual([b["otz"] for b in bound], list(range(1000, 1018)))
        self.assertTrue(all(placement_invariants(f)["translation_exact"]
                            and placement_invariants(f)["cross_preserved"]
                            for f in faces))
        with self.assertRaisesRegex(ValueError, "face index outside"):
            place_selected_faces(data, [(2, 3, 18)],
                                 {(2, 3, 18): (0, 0, 15, 15)},
                                 step_x=64, step_z=64)

    def test_mutation_of_single_face_slot_is_detected_without_aliasing(self):
        data = fixture()
        origin = (2 * STRIDE + 3) * RECORD_SIZE
        data[origin + FACE_COUNT_OFFSET] = 2
        data[origin + FACE_TABLE_OFFSET + 4:
             origin + FACE_TABLE_OFFSET + 8] = bytes((0, 1, 2, 3))
        data[origin + 284] = 10
        data[origin + 285] = 11
        keys = [(2, 3, 0), (2, 3, 1)]
        uv = {key: (0, 0, 15, 15) for key in keys}
        first = place_selected_faces(data, keys, uv, step_x=64, step_z=64)
        data[origin + 285] = 99
        second = place_selected_faces(data, keys, uv, step_x=64, step_z=64)
        self.assertEqual(first[0]["source_face"], second[0]["source_face"])
        self.assertEqual(second[1]["source_face"]["face_shade"], 99)
        self.assertNotEqual(first[1]["source_face"], second[1]["source_face"])


    def test_multicell_multiface_batch_preserves_provenance(self):
        data = fixture()
        for z, x in self.cells[:2]:
            origin = (z * STRIDE + x) * RECORD_SIZE
            data[origin + FACE_COUNT_OFFSET] = 2
            data[origin + FACE_TABLE_OFFSET + 4:
                 origin + FACE_TABLE_OFFSET + 8] = bytes((3, 2, 1, 0))
            struct.pack_into("<h", data, origin + GFX_OFFSET + 2, 410 + x)
            data[origin + 285] = 10 + x
        keys = [(2, 3, 0), (2, 4, 1), (2, 3, 1), (2, 4, 0)]
        faces = place_selected_faces(data, keys,
                                     {key: (0, 0, 15, 15) for key in keys},
                                     step_x=64, step_z=64)
        samples = {
            (2, 3, 59, 0): {"otz": 400},
            (2, 4, 60, 1): {"otz": 100},
            (2, 3, 59, 1): {"otz": 300},
            (2, 4, 60, 0): {"otz": 200},
        }
        report = audit_multicell_gte_batch(faces, samples)
        self.assertEqual(report["cell_count"], 2)
        self.assertEqual(report["face_count"], 4)
        self.assertEqual([f["source_key"] for f in report["faces"]],
                         [[2, 3, 59, 0], [2, 4, 60, 1],
                          [2, 3, 59, 1], [2, 4, 60, 0]])
        self.assertEqual([f["otz"] for f in report["faces"]],
                         [400, 100, 300, 200])
        self.assertEqual([f["input_order"] for f in report["faces"]],
                         [0, 1, 2, 3])
        self.assertEqual(report["faces"][1]["local_gfx"], 414)

    def test_multicell_batch_rejects_missing_samples_and_moved_vertex(self):
        keys = [(2, 3, 0), (2, 4, 0)]
        faces = place_selected_faces(
            self.data, keys, {key: (0, 0, 15, 15) for key in keys},
            step_x=64, step_z=64)
        samples = {(2, 3, 59, 0): {"otz": 100},
                   (2, 4, 60, 0): {"otz": 200}}
        with self.assertRaisesRegex(ValueError, "match source"):
            audit_multicell_gte_batch(faces, {(2, 3, 59, 0): {"otz": 100}})
        faces[1]["world_xyz_hypothesis"][0][0] += 1
        with self.assertRaisesRegex(ValueError, "translation invariant"):
            audit_multicell_gte_batch(faces, samples)


    def test_screen_corners_preserve_gpu_ft4_cross_order_and_face_keys(self):
        keys = [(2, 3, 0), (2, 4, 0)]
        faces = place_selected_faces(self.data, keys,
                                     {key: (0, 0, 15, 15) for key in keys},
                                     step_x=64, step_z=64)
        bound = bind_external_screen_corners(faces, {
            (2, 3, 59, 0): [(10, 20), (30, 20), (30, 40), (10, 40)],
            (2, 4, 60, 0): [(-32768, 32767), (50, 60), (70, 80), (90, 100)]
        })
        self.assertEqual(bound[0]["gpu_poly_xy"],
                         [[10, 20], [30, 20], [10, 40], [30, 40]])
        self.assertEqual(bound[1]["source_key"], [2, 4, 60, 0])
        self.assertEqual(bound[1]["perimeter_xy"][0], [-32768, 32767])

    def test_screen_samples_reject_mismatch_invalid_coordinates_and_duplicates(self):
        keys = [(2, 3, 0)]
        faces = place_selected_faces(self.data, keys,
                                     {keys[0]: (0, 0, 15, 15)},
                                     step_x=64, step_z=64)
        good = [(1, 2), (3, 4), (5, 6), (7, 8)]
        with self.assertRaisesRegex(ValueError, "match source"):
            bind_external_screen_corners(faces, {(2, 3, 60, 0): good})
        for bad in (good[:3], [(True, 0)] + good[1:],
                    [(32768, 0)] + good[1:], [(1.5, 0)] + good[1:]):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "signed-16"):
                    bind_external_screen_corners(faces, {(2, 3, 59, 0): bad})
        with self.assertRaisesRegex(ValueError, "duplicate screen"):
            bind_external_screen_corners([faces[0], faces[0]],
                                         {(2, 3, 59, 0): good})


if __name__ == "__main__":
    unittest.main()
