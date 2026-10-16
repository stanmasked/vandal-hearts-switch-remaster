"""Source contract tests for the original 26 MAP02 terrain light normals."""
import unittest

from tools.audit_map02_direction_source import (
    ASSIGN, DIRECTIONS, FACE_ANCHORS, verify_directions,
    verify_pc_normal_math,
)


def synthetic_sources():
    statements = []
    for index, values in enumerate(DIRECTIONS):
        for component, value in zip(("vx", "vy", "vz"), values):
            statements.append(f"v[{index}].{component} = {value};")
    graphics = (
        "void SetupLightNormals(void) {\n"
        + "\n".join(statements)
        + "\nfor (i = 0; i < ARRAY_COUNT(v); i++)\n"
        + "VectorNormalS(&v[i], &gSideLightNormals[i]);\n"
        + "}\n"
        + "void UpdateLight(void) {}\n"
        + "void UpdateMapTileLighting(void) {\n"
        + "\n".join(FACE_ANCHORS)
        + "\n"
        + "gSideLightNormals[j].vx * svec_sp40.vx\n"
        + "gSideLightNormals[j].vy * svec_sp40.vy\n"
        + "gSideLightNormals[j].vz * svec_sp40.vz\n"
        + "}\n"
        + "void RenderMapTile(void) {}\n"
    )
    header = (
        "static const VhMap02Direction vh_map02_directions[26] = {\n"
        + ",\n".join("{" + ",".join(map(str, vector)) + "}" for vector in DIRECTIONS)
        + "\n};\n"
    )
    return graphics, header


def synthetic_pc_normal_source():
    return (
        "void PC_GTE_LoadOPV2(void *v) {\n"
        "g.ir1 = (short)src[0];\n"
        "g.ir2 = (short)src[1];\n"
        "g.ir3 = (short)src[2];\n}\n"
        "void PC_GTE_OP0(void) {\n"
        "g.mac1 = ir3 * d2 - ir2 * d3;\n"
        "g.mac2 = ir1 * d3 - ir3 * d1;\n"
        "g.mac3 = ir2 * d1 - ir1 * d2;\n}\n"
        "int VectorNormalS(VECTOR *v0, SVECTOR *v1) {\n"
        "double len = sqrt((double)v0->vx * v0->vx + (double)v0->vy * v0->vy + (double)v0->vz * v0->vz);\n"
        "if (len < 1.0) { return 0; }\n"
        "v1->vx = (short)((v0->vx * (double)ONE) / len);\n"
        "v1->vy = (short)((v0->vy * (double)ONE) / len);\n"
        "v1->vz = (short)((v0->vz * (double)ONE) / len);\n"
        "}\n"
        "/* SquareRoot0/SquareRoot12/csqrt:\n"
    )


def synthetic_portable_q12_header():
    return (
        "axes == 1u ? 4096 : axes == 2u ? 2896 : 2364\n"
        "vh_map02_normal_q12(normal, q)\n"
        "vh_map02_q12_tie_count(q, candidate)\n"
        "unsigned __int128 magnitude_sq\n"
    )


class Map02DirectionalSourceTests(unittest.TestCase):
    def test_pc_vectornormal_and_portable_q12_contract(self):
        report = verify_pc_normal_math(
            synthetic_pc_normal_source(), synthetic_portable_q12_header())
        self.assertEqual(report["candidate_q12_scales"], [4096, 2896, 2364])
        self.assertTrue(report["pc_vectornormal_uses_sqrt_and_truncation"])
        self.assertTrue(report["pc_op0_loads_second_edge_as_signed_16bit"])
        self.assertFalse(report["ps1_hardware_gte_rounding_verified"])

    def test_pc_normal_truncation_or_op0_input_mutations_rejected(self):
        source = synthetic_pc_normal_source()
        header = synthetic_portable_q12_header()
        for src, expected in (
            (source.replace("v1->vy = (short)", "v1->vy = (int)"),
             "VectorNormalS rounding"),
            (source.replace("g.ir3 = (short)src[2];",
                            "g.ir3 = src[2];"),
             "OP0 source arithmetic"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    verify_pc_normal_math(src, header)

    def test_q12_2365_error_is_detected(self):
        source = synthetic_pc_normal_source()
        header = synthetic_portable_q12_header()
        with self.assertRaisesRegex(ValueError, "portable PC Q12 reference changed"):
            verify_pc_normal_math(source, header.replace("2364", "2365"))
        with self.assertRaisesRegex(ValueError, "portable PC Q12 reference changed"):
            verify_pc_normal_math(
                source, header.replace("vh_map02_normal_q12(normal, q)",
                                       "vh_map02_candidate_dot(normal, d)"))

    def test_all_26_vectors_match_in_both_languages(self):
        source, header = synthetic_sources()
        result = verify_directions(source, header)
        self.assertEqual(result["direction_count"], 26)
        self.assertEqual(result["source_component_assignments"], 78)
        self.assertTrue(result["portable_direction_table_matches_upstream"])
        self.assertFalse(result["rounding_equivalence_with_gte"])
        self.assertEqual(len(ASSIGN.findall(source)), 78)

    def test_single_source_axis_mutation_is_detected(self):
        source, header = synthetic_sources()
        with self.assertRaisesRegex(ValueError, "direction vectors changed"):
            verify_directions(source.replace("v[15].vz = 1;", "v[15].vz = -1;"),
                              header)

    def test_omitted_or_repeated_assignment_is_rejected(self):
        source, header = synthetic_sources()
        with self.assertRaisesRegex(ValueError, "78 source direction assignments"):
            verify_directions(source.replace("v[25].vz = -1;", ""), header)
        with self.assertRaisesRegex(ValueError, "duplicate source assignment"):
            verify_directions(source.replace("v[25].vz = -1;",
                                             "v[25].vz = -1;\nv[25].vz = -1;")
                              .replace("v[24].vx = -1;", ""), header)

    def test_portable_header_direction_mutations_are_detected(self):
        source, header = synthetic_sources()
        with self.assertRaisesRegex(ValueError, "portable direction array differs"):
            verify_directions(source, header.replace("{1,1,1}", "{-1,1,1}"))
        with self.assertRaisesRegex(ValueError, "portable 26-direction array missing"):
            verify_directions(source, header.replace("vh_map02_directions[26]",
                                                     "vh_map02_directions[25]"))

    def test_unverified_algorithm_or_normalization_is_rejected(self):
        source, header = synthetic_sources()
        for anchor in (FACE_ANCHORS[0], FACE_ANCHORS[8],
                       FACE_ANCHORS[11], FACE_ANCHORS[-1]):
            with self.subTest(statement=anchor):
                with self.assertRaisesRegex(ValueError, "face-normal selection changed"):
                    verify_directions(source.replace(anchor, "/* removed */"), header)
        with self.assertRaisesRegex(ValueError, "normalization call changed"):
            verify_directions(source.replace(
                "VectorNormalS(&v[i], &gSideLightNormals[i]);", "/* missing */"), header)
        with self.assertRaisesRegex(ValueError, "dot product missing"):
            verify_directions(source.replace(
                "gSideLightNormals[j].vy * svec_sp40.vy", "/* missing */"), header)

    def test_modified_function_boundaries_rejected(self):
        source, header = synthetic_sources()
        with self.assertRaisesRegex(ValueError, "must occur exactly once"):
            verify_directions(source.replace("void UpdateMapTileLighting(",
                                             "void Renamed("), header)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            verify_directions(source + "\nvoid SetupLightNormals() {}\n", header)


if __name__ == "__main__":
    unittest.main()
