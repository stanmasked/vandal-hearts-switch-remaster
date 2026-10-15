"""Synthetic regression coverage for map02 PRS/DAT disagreement audit."""
import unittest

from tools.compare_map02_variants import (
    EXPECTED_LENGTH, FACE_GFX_OFFSET, RECORD_SIZE, compare_map02,
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
        self.assertEqual(report["difference_count"], 2)
        self.assertEqual([x["absolute_offset"] for x in report["differences"]], [74048, 97152])
        self.assertEqual([x["prs_local_gfx"] for x in report["target_faces"]], [241, 243])
        self.assertEqual([x["dat_local_gfx"] for x in report["target_faces"]], [98, 150])

    def test_additional_difference_is_not_accepted(self):
        prs = bytes(EXPECTED_LENGTH)
        dat = bytearray(prs)
        dat[99] = 1
        report = compare_map02(prs, bytes(dat))
        self.assertFalse(report["matches_prior_disc_audit"])
        self.assertEqual(report["differences"][0]["record_index"], 0)

    def test_invalid_input_sizes(self):
        with self.assertRaisesRegex(ValueError, "decompressed PRS"):
            compare_map02(b"short", bytes(EXPECTED_LENGTH))
        with self.assertRaisesRegex(ValueError, "DAT"):
            compare_map02(bytes(EXPECTED_LENGTH), b"short")


if __name__ == "__main__":
    unittest.main()
