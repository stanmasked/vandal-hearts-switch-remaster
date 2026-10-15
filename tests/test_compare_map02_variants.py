"""Synthetic regression coverage for map02 PRS/DAT disagreement audit."""
import unittest

from tools.compare_map02_variants import (
    EXPECTED_LENGTH, FACE_GFX_OFFSET, RECORD_SIZE, classify_runtime_faces, compare_map02,
)


class Map02VariantTests(unittest.TestCase):
    def test_exact_two_byte_variant(self):
        prs = bytearray(EXPECTED_LENGTH)
        dat = bytearray(EXPECTED_LENGTH + 4)
        for record, p, d in ((243, 241, 98), (319, 243, 150)):
            offset = record * RECORD_SIZE + FACE_GFX_OFFSET
            prs[offset] = p
            dat[offset] = d
        report = compare_map02(bytes(prs), bytes(dat))
        self.assertTrue(report["matches_prior_disc_audit"])
        self.assertFalse(report["matches_prior_prs_digest"])
        self.assertFalse(report["matches_prior_disc_audit_with_provenance"])
        self.assertEqual(report["difference_count"], 2)
        self.assertEqual([x["absolute_offset"] for x in report["differences"]], [74048, 97152])
        self.assertEqual([x["prs_local_gfx"] for x in report["target_faces"]], [241, 243])
        self.assertEqual([x["dat_local_gfx"] for x in report["target_faces"]], [98, 150])
        self.assertEqual([(x["x"], x["z"], x["face"]) for x in report["target_faces"]], [(19, 8, 0), (11, 11, 0)])
        self.assertEqual([x["prs_runtime_gfx"] for x in report["target_faces"]], [641, 643])
        self.assertEqual([x["dat_runtime_gfx"] for x in report["target_faces"]], [498, 550])

    def test_additional_difference_is_not_accepted(self):
        prs = bytes(EXPECTED_LENGTH)
        dat = bytearray(prs)
        dat[99] = 1
        report = compare_map02(prs, bytes(dat))
        self.assertFalse(report["matches_prior_disc_audit"])
        self.assertEqual(report["differences"][0]["record_index"], 0)

    def test_runtime_capture_classifies_prs_and_dat(self):
        prs = bytearray(EXPECTED_LENGTH)
        dat = bytearray(EXPECTED_LENGTH)
        for record, p, d in ((243, 241, 98), (319, 243, 150)):
            offset = record * RECORD_SIZE + FACE_GFX_OFFSET
            prs[offset], dat[offset] = p, d
        report = compare_map02(bytes(prs), bytes(dat))
        prs_capture = [
            {"record_index": 243, "face": 0, "local_gfx": 241, "runtime_gfx": 641},
            {"record_index": 319, "face": 0, "local_gfx": 243, "runtime_gfx": 643},
        ]
        result = classify_runtime_faces(report, prs_capture)
        self.assertTrue(result["all_match_prs"])
        self.assertEqual(result["overall_classification"], "prs")
        self.assertTrue(result["recognized_and_consistent"])
        self.assertFalse(result["all_match_dat"])
        dat_capture = [
            {"record_index": 243, "face": 0, "local_gfx": 98, "runtime_gfx": 498},
            {"record_index": 319, "face": 0, "local_gfx": 150, "runtime_gfx": 550},
        ]
        self.assertTrue(classify_runtime_faces(report, dat_capture)["all_match_dat"])
        self.assertEqual(classify_runtime_faces(report, dat_capture)["overall_classification"], "dat")
        mixed_capture = [prs_capture[0], dat_capture[1]]
        self.assertFalse(classify_runtime_faces(report, mixed_capture)["all_match_prs"])
        self.assertFalse(classify_runtime_faces(report, mixed_capture)["all_match_dat"])
        self.assertEqual(classify_runtime_faces(report, mixed_capture)["overall_classification"], "mixed_or_ambiguous")

    def test_runtime_capture_rejects_invalid_translation_and_missing_faces(self):
        report = compare_map02(bytes(EXPECTED_LENGTH), bytes(EXPECTED_LENGTH))
        faces = [
            {"record_index": 243, "face": 0, "local_gfx": 241, "runtime_gfx": 640},
            {"record_index": 319, "face": 0, "local_gfx": 243, "runtime_gfx": 643},
        ]
        classified = classify_runtime_faces(report, faces)
        self.assertEqual(classified["faces"][0]["classification"], "invalid_translation")
        self.assertEqual(classified["overall_classification"], "invalid_translation")
        self.assertFalse(classified["recognized_and_consistent"])
        with self.assertRaisesRegex(ValueError, "exactly both"):
            classify_runtime_faces(report, faces[:1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            classify_runtime_faces(report, faces + [faces[0]])
        with self.assertRaisesRegex(ValueError, "integer"):
            classify_runtime_faces(report, [{**faces[0], "local_gfx": True}, faces[1]])

    def test_runtime_capture_reports_unrecognized_gfx(self):
        prs = bytearray(EXPECTED_LENGTH)
        dat = bytearray(EXPECTED_LENGTH)
        for record, p, d in ((243, 241, 98), (319, 243, 150)):
            offset = record * RECORD_SIZE + FACE_GFX_OFFSET
            prs[offset], dat[offset] = p, d
        report = compare_map02(bytes(prs), bytes(dat))
        capture = [
            {"record_index": 243, "face": 0, "local_gfx": 77, "runtime_gfx": 477},
            {"record_index": 319, "face": 0, "local_gfx": 243, "runtime_gfx": 643},
        ]
        result = classify_runtime_faces(report, capture)
        self.assertEqual(result["overall_classification"], "unrecognized")
        self.assertFalse(result["recognized_and_consistent"])

    def test_invalid_input_sizes(self):
        with self.assertRaisesRegex(ValueError, "decompressed PRS"):
            compare_map02(b"short", bytes(EXPECTED_LENGTH))
        with self.assertRaisesRegex(ValueError, "DAT"):
            compare_map02(bytes(EXPECTED_LENGTH), b"short")


if __name__ == "__main__":
    unittest.main()
