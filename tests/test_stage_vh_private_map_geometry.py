"""Asset-free acceptance for owner map geometry staging and topology gate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from private_sd_nexium_check import (  # noqa: E402
    synthetic_geometry_models, synthetic_depth_geometry_models, stage_depth,
    synthetic_distant_shading_models, stage_distance,
)
from inspect_vh_map_geometry import (  # noqa: E402
    MAP_11_BYTES, MAP_11_STRIDE, TILE_BYTES, parse_tile,
)
from stage_vh_private_map_geometry import (  # noqa: E402
    GEOMETRY_MANIFEST, GEOMETRY_NAME,
    stage_map11_geometry, validate_map11_models,
)
from stage_vh_private_map_bank import RELATIVE_DESTINATION  # noqa: E402


class StagedModelTests(unittest.TestCase):
    def setUp(self):
        self.models = synthetic_geometry_models()

    def test_fixture_has_one_backface_and_two_front_faces(self):
        self.assertEqual(len(self.models), MAP_11_BYTES)
        faces = parse_tile(self.models,6,3)["faces"]
        self.assertEqual(len(faces),3)
        self.assertEqual([f["local_gfx_slot"] for f in faces],[242,241,242])
        # Source front triangle 0,1,3 becomes reversed 1,0,2.
        self.assertEqual(faces[0]["vertex_indices"],[1,0,2,3])
        self.assertEqual(faces[1]["vertex_indices"],[0,1,3,2])
        self.assertEqual(faces[0]["vertex_xyz"][0],[0,0,-16])
        self.assertEqual(faces[1]["vertex_xyz"][0],[-32,0,-16])
        self.assertEqual(faces[2]["vertex_xyz"][2],[32,0,24])
        self.assertEqual(faces[2]["vertex_xyz"][3],[0,0,24])
        self.assertEqual(validate_map11_models(self.models)["active_faces"],3)
        self.assertEqual(validate_map11_models(self.models)["populated_tiles"],1)

    def test_native_raster_follows_exact_nclip_depth_pipeline(self):
        source = (ROOT / "probes" / "pinned_drawotag_switch_smoke.c").read_text()
        start = source.index("static int draw_private_map_preview(void)")
        end = source.index("/* Test-only inert providers", start)
        region = source[start:end]
        ops = (
            "gte_ldv3(&source_vertices[0]",
            "gte_rtpt();",
            "gte_nclip();",
            "gte_stopz(&opz);",
            "if (opz <= 0) continue;",
            "gte_stsxy3(&poly->x0, &poly->x1, &poly->x3);",
            "gte_ldv0(&source_vertices[3]);",
            "gte_rtps();",
            "gte_stsxy(&poly->x2);",
            "gte_avsz4();",
            "gte_stotz(&otz);",
            "AddPrim(&ot[PRIVATE_OT_BUCKETS - otz], poly);",
        )
        positions = [region.index(part) for part in ops]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("ClearOTag(ot, PRIVATE_OT_BUCKETS);", region)
        self.assertIn("AddPrim(&ot[0], &clear);", region)

    def test_overlapping_far_first_near_last_faces(self):
        """Different source depths must keep the SAME screenshot footprint."""
        data=synthetic_depth_geometry_models()
        self.assertEqual(len(data),MAP_11_BYTES)
        tile=parse_tile(data,6,3)
        self.assertEqual(tile["face_count"],2)
        far,near=tile["faces"]
        self.assertEqual([far["local_gfx_slot"],near["local_gfx_slot"]],
                         [242,241])
        self.assertEqual(far["vertex_indices"],[0,1,2,3])
        self.assertEqual(near["vertex_indices"],[4,5,6,7])
        for f,n in zip(far["vertex_xyz"],near["vertex_xyz"]):
            self.assertEqual(f[0],2*n[0])
            self.assertEqual(f[1],2*n[1]-68)
            self.assertEqual(f[2],2*n[2]+68)
        self.assertEqual(validate_map11_models(data)["active_faces"],2)

    def test_depth_stage_uses_separate_non_overwriting_sd_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=stage_depth(root)
            self.assertEqual(result["active_faces"],2)
            p=root/RELATIVE_DESTINATION
            self.assertEqual((p/GEOMETRY_NAME).read_bytes(),
                             synthetic_depth_geometry_models())
            self.assertTrue((p/"F_TEX01.DAT").is_file())
            self.assertTrue((p/"LAND_DT.DAT").is_file())
            with self.assertRaises(FileExistsError):
                stage_depth(root)

    def test_distant_shading_fixture_preserves_perspective_shape(self):
        data=synthetic_distant_shading_models()
        self.assertEqual(len(data),MAP_11_BYTES)
        face=parse_tile(data,6,3)["faces"][0]
        self.assertEqual(face["local_gfx_slot"],242)
        near=((-32,0,-16),(0,0,-16),(0,0,24),(-32,0,24))
        for p,n in zip(face["vertex_xyz"],near):
            self.assertEqual(p,[8*n[0],8*n[1]-476,8*n[2]+476])
        self.assertEqual(validate_map11_models(data)["active_faces"],1)

    def test_stage_distance_fixture_independently(self):
        with tempfile.TemporaryDirectory() as d:
            report=stage_distance(Path(d))
            self.assertEqual(report["active_faces"],1)
            p=Path(d)/RELATIVE_DESTINATION
            self.assertEqual((p/GEOMETRY_NAME).read_bytes(),
                             synthetic_distant_shading_models())
            self.assertTrue((p/"F_TEX01.DAT").is_file())

    def test_stage_readback_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            report = stage_map11_geometry(self.models,d)
            path = Path(d)/RELATIVE_DESTINATION
            self.assertEqual((path/GEOMETRY_NAME).read_bytes(),self.models)
            self.assertEqual(json.loads((path/GEOMETRY_MANIFEST).read_text()),report)
            self.assertEqual(report["tile_records"],336)
            with self.assertRaises(FileExistsError):
                stage_map11_geometry(self.models,d)

    def test_rejects_truncation_before_file_write(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"102144"):
                stage_map11_geometry(self.models[:-1],d)
            self.assertFalse((Path(d)/RELATIVE_DESTINATION).exists())

    def test_rejects_corrupt_other_tile_before_file_write(self):
        corrupt=bytearray(self.models)
        corrupt[302]=19
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"faceCt"):
                stage_map11_geometry(bytes(corrupt),d)
            self.assertFalse((Path(d)/RELATIVE_DESTINATION).exists())

    def test_rejects_invalid_vertex_index(self):
        corrupt=bytearray(self.models)
        offset=(3*MAP_11_STRIDE+6)*TILE_BYTES
        corrupt[offset+212]=22
        with self.assertRaisesRegex(ValueError,"vertex"):
            validate_map11_models(corrupt)


if __name__ == "__main__":
    unittest.main()
