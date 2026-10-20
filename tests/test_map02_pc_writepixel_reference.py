"""Asset-free golden vectors from pinned original PC WritePixel / BlendG1.

Expected values were independently checked against a native C11 extraction
of pc_raster.c at the pinned upstream commit. This is PC-source equivalence,
not PlayStation GPU pixel or real MAP02 capture authentication.
"""
import unittest

from tools.map02_pc_writepixel_reference import expected_write_pixel


# (before BGR555, front BGR555, ABR, semi, textured, accurate, after)
GOLDEN = [
    (0x0421,0x821f,0,1,0,0,0x0110),
    (0x0421,0x821f,0,1,1,0,0x0110),
    (0x0421,0x821f,0,1,0,1,0x0110),
    (0x0421,0x821f,0,1,1,1,0x8110),
    (0x0421,0x821f,1,1,0,0,0x063f),
    (0x0421,0x821f,1,1,1,0,0x063f),
    (0x0421,0x821f,1,1,0,1,0x063f),
    (0x0421,0x821f,1,1,1,1,0x863f),
    (0x0421,0x821f,2,1,0,0,0x0400),
    (0x0421,0x821f,2,1,1,0,0x0400),
    (0x0421,0x821f,2,1,0,1,0x0400),
    (0x0421,0x821f,2,1,1,1,0x8400),
    (0x0421,0x821f,3,1,0,0,0x04a8),
    (0x0421,0x821f,3,1,1,0,0x04a8),
    (0x0421,0x821f,3,1,0,1,0x04a8),
    (0x0421,0x821f,3,1,1,1,0x84a8),
    (0xffff,0x7c1f,0,1,1,0,0x7dff),
    (0xffff,0x7c1f,0,1,1,1,0xfdff),
    (0xffff,0x7c1f,1,1,1,0,0x7fff),
    (0xffff,0x7c1f,1,1,1,1,0xffff),
    (0xffff,0x7c1f,2,1,1,0,0x03e0),
    (0xffff,0x7c1f,2,1,1,1,0x83e0),
    (0xffff,0x7c1f,3,1,1,0,0x7fff),
    (0xffff,0x7c1f,3,1,1,1,0xffff),
]


class SourcePinnedPcWritePixelReferenceTests(unittest.TestCase):
    def test_native_c_reference_golden_semitransparent_vectors(self):
        self.assertEqual(len(GOLDEN), 24)
        for before, front, abr, semi, textured, accurate, expected in GOLDEN:
            with self.subTest(abr=abr, textured=textured, accurate=accurate,
                              before=before, front=front):
                self.assertEqual(expected_write_pixel(
                    before, front, abr, semi, textured, accurate), expected)

    def test_opaque_copy_retains_bit15_independent_of_modes(self):
        for front in (0, 0x8000, 0xffff, 0x03e0):
            for abr in range(4):
                for textured in (0, 1):
                    for accurate in (0, 1):
                        self.assertEqual(expected_write_pixel(
                            0x7c1f, front, abr, 0, textured, accurate), front)

    def test_accurate_textured_bit15_and_legacy_clear_are_distinct(self):
        # In pinned BlendG1, the textured result can retain bit15;
        # the legacy PackColor path never does. A zero blend result
        # is not proof of a skipped or masked pixel.
        self.assertEqual(expected_write_pixel(
            0x0421, 0x821f, 1, 1, 1, 1), 0x863f)
        self.assertEqual(expected_write_pixel(
            0x0421, 0x821f, 1, 1, 0, 1), 0x063f)
        self.assertEqual(expected_write_pixel(
            0x0421, 0x821f, 1, 1, 1, 0), 0x063f)

    def test_invalid_blend_mode_does_not_silently_select_another_abr(self):
        for accurate in (0, 1):
            with self.assertRaisesRegex(ValueError, "ABR"):
                expected_write_pixel(0, 0x8000, 4, 1, 1, accurate)


if __name__ == "__main__":
    unittest.main()
