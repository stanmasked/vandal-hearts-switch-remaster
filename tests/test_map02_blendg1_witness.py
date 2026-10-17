"""Synthetic regression cases for optional BlendG1 witnesses."""
import unittest

from tools.map02_blendg1_witness import compare_blendg1_witnesses


def pixel(step, mode, abr, semi=1):
    return dict(stage="native_putpixel", step=step, frame=7,
                primitive_ordinal=3, primitive_type=4, x=20, y=40,
                accurate=mode, abr=abr, semi=semi,
                before=0x001f, front=0x7c00,
                after=0x03e0 if semi else 0x7c00)


def witness(p):
    return dict(stage="native_blendg1", putpixel_step=p["step"],
                blend_fg=p["front"] | 0x8000, blend_bg=p["before"],
                blend_result=p["after"],
                **{k: p[k] for k in ("frame", "primitive_ordinal", "primitive_type", "x",
                                   "y", "accurate", "abr", "before",
                                   "front", "after")})


class BlendG1WitnessTests(unittest.TestCase):
    def test_join_respects_mode_and_abr(self):
        rows = [pixel(0, 1, 0), pixel(1, 0, 2, semi=0),
                pixel(2, 1, 3)]
        result = compare_blendg1_witnesses(rows, [witness(rows[0]),
                                                    witness(rows[2])])
        self.assertEqual(result["observed_blendg1_putpixel_pairs"], 2)
        self.assertEqual(result["observed_blendg1_witnesses_by_accuracy_and_abr"],
                         [[0, 0, 0, 0], [1, 0, 0, 1]])
        self.assertFalse(result["blendg1_arithmetic_equivalence_proven"])
        self.assertFalse(result["ps1_hardware_equivalence_proven"])

    def test_refuses_partial_duplicate_and_reordered_trace(self):
        rows = [pixel(0, 1, 0), pixel(1, 1, 3)]
        for bad in ([witness(rows[0])],
                    [witness(rows[0]), witness(rows[0])],
                    [witness(rows[1]), witness(rows[0])]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                compare_blendg1_witnesses(rows, bad)

    def test_refuses_modified_fields_and_malformed_integers(self):
        p = pixel(0, 1, 2)
        for key, value in (("abr", 1), ("primitive_type", 8), ("after", 0), ("accurate", 0),
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

    def test_rejects_untrusted_putpixel_stream(self):
        p = pixel(0, 1, 0)
        bad_inputs = [
            [None],
            [dict(p, stage="native_blendg1")],
            [dict(p, step=True)],
            [dict(p, semi=True)],
            [p, p],
            [dict(p, step=2), dict(p, step=1)],
            [dict(pixel(0, 0, 0, semi=0), after=0)],
        ]
        for rows in bad_inputs:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                compare_blendg1_witnesses(rows, [witness(p)])

    def test_legacy_semi_needs_no_blendg1(self):
        rows = [pixel(0, 0, 2), pixel(1, 1, 3)]
        result = compare_blendg1_witnesses(rows, [witness(rows[1])])
        self.assertEqual(result["legacy_semi_putpixel_calls_without_blendg1"], 1)
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses(rows, [witness(rows[0]), witness(rows[1])])

    def test_independent_blend_inputs_and_output_required(self):
        p = pixel(0, 1, 0)
        for field, value in (("blend_fg", p["front"]),
                             ("blend_bg", p["before"] ^ 1),
                             ("blend_result", p["after"] ^ 1)):
            w = witness(p)
            w[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare_blendg1_witnesses([p], [w])
            del w[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                compare_blendg1_witnesses([p], [w])

    def test_no_semi_requires_no_blendg1(self):
        p = pixel(0, 0, 2, semi=0)
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses([p], [])
        with self.assertRaises(ValueError):
            compare_blendg1_witnesses([p], [witness(p)])


if __name__ == "__main__":
    unittest.main()
