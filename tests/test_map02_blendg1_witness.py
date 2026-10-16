"""Synthetic regression cases for optional BlendG1 witnesses."""
import unittest

from tools.map02_blendg1_witness import compare_blendg1_witnesses


def pixel(step, mode, abr, semi=1):
    return dict(stage="native_putpixel", step=step, frame=7,
                primitive_ordinal=3, x=20, y=40,
                accurate=mode, abr=abr, semi=semi,
                before=0x001f, front=0x7c00,
                after=0x03e0 if semi else 0x7c00)


def witness(p):
    return dict(stage="native_blendg1", putpixel_step=p["step"],
                **{k: p[k] for k in ("frame", "primitive_ordinal", "x",
                                   "y", "accurate", "abr", "before",
                                   "front", "after")})


class BlendG1WitnessTests(unittest.TestCase):
    def test_join_respects_mode_and_abr(self):
        rows = [pixel(0, 0, 0), pixel(1, 0, 2, semi=0),
                pixel(2, 1, 3)]
        result = compare_blendg1_witnesses(rows, [witness(rows[0]),
                                                    witness(rows[2])])
        self.assertEqual(result["observed_blendg1_putpixel_pairs"], 2)
        self.assertEqual(result["observed_blendg1_witnesses_by_accuracy_and_abr"],
                         [[1, 0, 0, 0], [0, 0, 0, 1]])
        self.assertFalse(result["blendg1_arithmetic_equivalence_proven"])
        self.assertFalse(result["ps1_hardware_equivalence_proven"])

    def test_refuses_partial_duplicate_and_reordered_trace(self):
        rows = [pixel(0, 0, 0), pixel(1, 1, 3)]
        for bad in ([witness(rows[0])],
                    [witness(rows[0]), witness(rows[0])],
                    [witness(rows[1]), witness(rows[0])]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                compare_blendg1_witnesses(rows, bad)

    def test_refuses_modified_fields_and_malformed_integers(self):
        p = pixel(0, 0, 2)
        for key, value in (("abr", 1), ("after", 0), ("accurate", 1),
                           ("x", 21), ("frame", 8), ("after", True),
                           ("putpixel_step", 64)):
            w = witness(p)
            w[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                compare_blendg1_witnesses([p], [w])
        bad = witness(p)
        bad["stage"] = "native_putpixel"
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses([p], [bad])

    def test_no_semi_requires_no_blend(self):
        p = pixel(0, 0, 2, semi=0)
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses([p], [])
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses([p], [witness(p)])


if __name__ == "__main__":
    unittest.main()
