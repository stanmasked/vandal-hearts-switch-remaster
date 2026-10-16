"""Synthetic, asset-free end-to-end decoded MAP02 OP0 audit tests."""
import struct
import tempfile
import unittest
from pathlib import Path

from tools.audit_map02_op0_geometry import read_owned_input, scan_decoded
from tools.compare_map02_variants import EXPECTED_LENGTH
from tools.map02_face_geometry import RECORD_SIZE, STRIDE

def new_map():
    return bytearray(EXPECTED_LENGTH)

def add_tile(blob, z, x, vertices, *, face=(0,1,2,3), count=1):
    ofs = (z * STRIDE + x) * RECORD_SIZE
    for i, coords in enumerate(vertices):
        struct.pack_into("<hhh", blob, ofs + i * 8, *coords)
    blob[ofs + 212:ofs + 216] = bytes(face)
    blob[ofs + 302] = count

class Map02Op0GeometryAuditTests(unittest.TestCase):
    def test_empty_map_stays_explicitly_synthetic(self):
        result = scan_decoded(new_map())
        self.assertEqual(result["active_tiles"], 288)
        self.assertEqual(result["occupied_tiles"], 0)
        self.assertEqual(result["faces"], 0)
        self.assertFalse(result["matches_prior_prs_sha256"])
        self.assertFalse(result["ps1_hardware_gte_verified"])
        self.assertFalse(result["camera_projection_verified"])
        self.assertFalse(result["raw_game_bytes_emitted"])
        self.assertEqual([p["present"] for p in result["bridge_faces"]], [False, False])

    def test_extreme_face_distinguishes_all_three_normals(self):
        blob = new_map()
        add_tile(blob, 8, 19, [
            (-32768,-32768,-32768), (32767,-32768,-32768),
            (-32768,-32768,32767), (-32768,-32768,32767)])
        add_tile(blob, 11, 11, [
            (0,0,0),(100,0,0),(0,0,100),(0,0,100)])
        result = scan_decoded(blob)
        self.assertEqual(result["occupied_tiles"], 2)
        self.assertEqual(result["faces"], 2)
        self.assertEqual(result["degenerate_wide"], 0)
        self.assertEqual(result["zero_pc_mac"], 0)
        self.assertEqual(result["zero_ps1_mac_model"], 0)
        self.assertEqual(result["wide_pc_classification_differences"], 1)
        self.assertEqual(result["pc_ps1_classification_differences"], 1)
        self.assertEqual(result["wide_pc_classifications_compared"], 2)
        self.assertEqual(result["pc_ps1_classifications_compared"], 2)
        self.assertGreater(result["first_edge_components_truncated_by_ps1"], 0)
        self.assertGreater(result["second_edge_components_truncated_by_both"], 0)
        first, second = result["bridge_faces"]
        self.assertEqual((first["z"],first["x"],first["face"]), (8,19,0))
        self.assertTrue(first["present"])
        self.assertEqual((first["wide_direction"], first["pc_direction"],
                          first["ps1_model_direction"]), (1,0,1))
        self.assertFalse(first["wide_pc_equal"])
        self.assertFalse(first["pc_ps1_equal"])
        self.assertTrue(second["present"])
        self.assertEqual((second["wide_direction"], second["pc_direction"],
                          second["ps1_model_direction"]), (1,1,1))
        self.assertTrue(second["wide_pc_equal"])
        self.assertTrue(second["pc_ps1_equal"])

    def test_repeated_corner_and_degenerate_face_accounted_separately(self):
        blob = new_map()
        # Duplicate index 0 triggers original first-corner branch;
        # chosen edges are (vertex0-vertex1),(vertex2-vertex1).
        add_tile(blob, 0, 0, [(0,0,0),(100,0,0),(0,0,100)],
                 face=(0,0,1,2))
        add_tile(blob, 0, 1, [(0,0,0),(100,0,0),(200,0,0)],
                 face=(0,1,2,2))
        result = scan_decoded(blob)
        self.assertEqual(result["faces"], 2)
        self.assertEqual(result["degenerate_wide"], 1)
        self.assertEqual(result["zero_pc_mac"], 1)
        self.assertEqual(result["zero_ps1_mac_model"], 1)
        self.assertEqual(result["wide_pc_classifications_compared"], 1)
        self.assertEqual(result["pc_ps1_classifications_compared"], 1)
        self.assertEqual(result["pc_ps1_classification_differences"], 0)

    def test_reject_invalid_face_count_or_vertex_index(self):
        blob = new_map()
        at = (4 * STRIDE + 5) * RECORD_SIZE
        blob[at + 302] = 19
        with self.assertRaisesRegex(ValueError,"faceCt"):
            scan_decoded(blob)
        blob[at + 302] = 1
        blob[at + 212] = 22
        with self.assertRaisesRegex(ValueError,"invalid face geometry"):
            scan_decoded(blob)

    def test_provenance_is_strict_not_inferred_from_shape(self):
        with self.assertRaisesRegex(ValueError, "prior PRS provenance"):
            scan_decoded(new_map(), require_prior_provenance=True)
        with self.assertRaisesRegex(ValueError,"decompressed length"):
            scan_decoded(b"tiny")

    def test_bounded_input_checks_before_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.bin"
            path.write_bytes(b"tiny")
            with self.assertRaisesRegex(ValueError, "input size"):
                read_owned_input(path, compressed=False)
            path.write_bytes(b"0" * (EXPECTED_LENGTH + 1))
            with self.assertRaisesRegex(ValueError, "input size"):
                read_owned_input(path, compressed=False)
            path.write_bytes(bytes(EXPECTED_LENGTH))
            decoded, digest = read_owned_input(path, compressed=False)
            self.assertEqual(len(decoded), EXPECTED_LENGTH)
            self.assertEqual(len(digest), 64)
            path.write_bytes(b"abc")
            with self.assertRaisesRegex(ValueError, "input size"):
                read_owned_input(path, compressed=True)

if __name__ == "__main__":
    unittest.main()
