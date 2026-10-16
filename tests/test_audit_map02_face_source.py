"""Fail-closed tests for pinned map face and PS1 GPU vertex/UV semantics."""
import unittest

from tools.audit_map02_face_source import (
    FIELD_LAYOUT, RENDERER_ANCHORS, RENDERERS, UV_MACRO,
    verify_source_contract,
)


def synthetic_c_sources():
    field = "#ifndef FIELD_H\n" + FIELD_LAYOUT + "\n#endif\n"
    gpu = "#ifndef GPU_H\n" + UV_MACRO + "\n#endif\n"
    blocks = []
    for name, _ in RENDERERS:
        lines = "\n".join(RENDERER_ANCHORS)
        uv = (
            "setUVWH(poly, texX, texY, texW, texH);"
            if name != "RenderOverheadMapTile"
            else "setUVWH(poly, gGfxSubTextures[gfx][0], gGfxSubTextures[gfx][1], "
                 "gGfxSubTextures[gfx][2], gGfxSubTextures[gfx][3]);"
        )
        blocks.append(f"void {name}(u32 *ot) {{\n{lines}\n{uv}\n}}\n")
    blocks.append("s32 GetBestViewOfTarget(s8 z, s8 x, s32 arg) { return 0; }\n")
    return field, "\n".join(blocks), gpu


class Map02FaceSourceTests(unittest.TestCase):
    def test_exact_model_and_all_render_paths_match(self):
        result = verify_source_contract(*synthetic_c_sources())
        self.assertTrue(result["field_and_gpu_layout_verified"])
        self.assertEqual(result["source_layout"]["tile_bytes"], 304)
        self.assertEqual(result["source_layout"]["gfx_offset"], 176)
        self.assertEqual(result["source_layout"]["faces_offset"], 212)
        self.assertEqual(result["source_layout"]["face_count_offset"], 302)
        self.assertEqual(result["source_face_perimeter_to_polygon_vertices"],
                         [0, 1, 3, 2])
        self.assertEqual(result["source_face_perimeter_to_uv"],
                         ["uv0", "uv1", "uv3", "uv2"])
        self.assertEqual(len(result["renderer_paths"]), 3)
        self.assertEqual(result["terrain_polygon_code"], "GPU_CODE_POLY_FT4 (0x2c)")
        self.assertFalse(result["terrain_abe_enabled"])

    def test_malformed_map_tile_model_fails_closed(self):
        field, graphics, gpu = synthetic_c_sources()
        for before, after in (
            ("vertices[22]", "vertices[21]"),
            ("s16 gfx[18]", "u8 gfx[18]"),
            ("faces[18][4]", "faces[18][3]"),
            ("u8 faceCt;", "s16 faceCt;"),
        ):
            with self.subTest(change=before):
                with self.assertRaisesRegex(ValueError, "MapTileModel"):
                    verify_source_contract(field.replace(before, after), graphics, gpu)

    def test_flip_in_gpu_macro_detected(self):
        field, graphics, gpu = synthetic_c_sources()
        with self.assertRaisesRegex(ValueError, "setUVWH"):
            verify_source_contract(
                field, graphics,
                gpu.replace("(p)->u3 = (_u0) + (_w)",
                            "(p)->u3 = (_u0)"),
            )

    def test_each_renderer_path_must_retain_face_vertex_mapping(self):
        field, graphics, gpu = synthetic_c_sources()
        for statement in (
            "gte_stsxy3(&poly->x0, &poly->x1, &poly->x3);",
            "gte_ldv0(&tileModel->vertices[pFaceVerts[3]]);",
            "gte_stsxy(&poly->x2);",
        ):
            with self.subTest(statement=statement):
                with self.assertRaisesRegex(ValueError, "GPU face mapping changed"):
                    verify_source_contract(
                        field, graphics.replace(statement, "/* removed */"), gpu
                    )

    def test_missing_or_duplicated_render_function_is_rejected(self):
        field, graphics, gpu = synthetic_c_sources()
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            verify_source_contract(
                field, graphics.replace("void RenderOverheadMapTile(",
                                        "void SomethingElse("), gpu)
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            verify_source_contract(field, graphics + "\nvoid RenderMapTile() {}\n", gpu)

    def test_normal_edge_and_overhead_terrain_reject_blending(self):
        field, graphics, gpu = synthetic_c_sources()
        for renderer in ("RenderMapTile", "RenderEdgeMapTile", "RenderOverheadMapTile"):
            with self.subTest(renderer=renderer):
                # Alter only one renderer, preserving others.
                start = graphics.index(f"void {renderer}(")
                stop = graphics.index("\n}", start)
                modified = (graphics[:stop] + "\nGPU_CODE_SEMI_TRANS;" +
                            graphics[stop:])
                with self.assertRaisesRegex(ValueError, f"{renderer} unexpectedly enables"):
                    verify_source_contract(field, modified, gpu)

    def test_missing_opaque_polygon_code_is_rejected(self):
        field, graphics, gpu = synthetic_c_sources()
        with self.assertRaisesRegex(ValueError, "GPU face mapping changed"):
            verify_source_contract(
                field, graphics.replace("poly->code = GPU_CODE_POLY_FT4;",
                                        "poly->code = 0x2e;"), gpu
            )

    def test_each_renderer_uses_texture_table_uvwh(self):
        field, graphics, gpu = synthetic_c_sources()
        for marker in (
            "setUVWH(poly, texX, texY, texW, texH);",
            "setUVWH(poly, gGfxSubTextures[gfx][0], gGfxSubTextures[gfx][1],",
        ):
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(ValueError, "UVWH"):
                    verify_source_contract(field, graphics.replace(marker, "void();"), gpu)


if __name__ == "__main__":
    unittest.main()
