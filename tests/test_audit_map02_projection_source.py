"""Static failure-closed source-contract tests for MAP02 GPU projection order."""
import unittest
from tools.audit_map02_projection_source import (
    RENDER_ORDER, verify_renderer
)

def renderer(text=None):
    statements = list(RENDER_ORDER) if text is None else text
    return (
        "void RenderMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {\n"
        + "\n".join(statements)
        + "\n}\nvoid RenderEdgeMapTile(void) {}\n"
    )

class Map02ProjectionSourceTests(unittest.TestCase):
    def test_exact_order_and_corner_mapping(self):
        report=verify_renderer(renderer())
        self.assertTrue(report["matches_normal_terrain_source_order"])
        self.assertEqual(report["projected_face_vertex_to_ft4_corner"],[0,1,3,2])
        self.assertFalse(report["original_renderer_checks_ot_upper_bound"])
        self.assertFalse(report["ps1_hardware_projection_verified"])

    def test_cull_after_rtpt_and_fourth_vertex_after_cull(self):
        for left,right in ((2,3),(3,4),(5,6),(6,8),(9,10),(10,11),(12,13)):
            with self.subTest(pair=(left,right)):
                parts=list(RENDER_ORDER)
                parts[left],parts[right]=parts[right],parts[left]
                with self.assertRaisesRegex(ValueError,"GTE/GPU order changed"):
                    verify_renderer(renderer(parts))

    def test_missing_submission_or_duplicate_rtps_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"GTE/GPU order changed"):
            verify_renderer(renderer(RENDER_ORDER[:-1]))
        with self.assertRaisesRegex(ValueError,"number of MAP02 projection"):
            verify_renderer(renderer() .replace("gte_rtps();", "gte_rtps();\ngte_rtps();"))
        with self.assertRaisesRegex(ValueError,"number of MAP02 OT"):
            verify_renderer(renderer().replace(
                "AddPrim(ot + OT_SIZE - otz, poly);",
                "AddPrim(ot + OT_SIZE - otz, poly);\nAddPrim(ot + OT_SIZE - otz, poly);"))

if __name__ == "__main__":
    unittest.main()
