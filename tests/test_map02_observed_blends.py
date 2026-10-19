"""Synthetic regressions; not authenticated MAP02 or PS1 evidence."""
import unittest

from tools.map02_observed_blends import summarize_observed_blends


def event(accurate, abr, semi, before, front, after):
    return dict(accurate=accurate, abr=abr, semi=semi,
                before=before, front=front, after=after)


class ObservedBlendTests(unittest.TestCase):
    def test_separates_modes_and_abr(self):
        rows = [event(0, 0, 1, 0x001f, 0x7c00, 0x03e0),
                event(1, 0, 1, 0x001f, 0x7c00, 0x001f),
                event(1, 3, 1, 0x0000, 0x0001, 0x8001),
                event(0, 2, 0, 0x0100, 0x0200, 0x0200)]
        report = summarize_observed_blends(rows)
        bins = report["observed_semi_putpixel_by_accuracy_and_abr"]
        self.assertEqual(bins[0][0]["changed"], 1)
        self.assertEqual(bins[1][0]["same_color"], 1)
        self.assertEqual(bins[1][3]["bit15_rises"], 1)
        self.assertEqual(bins[0][2]["calls"], 0)
        self.assertEqual(report["observed_opaque_putpixel_by_accuracy"], [1, 0])
        self.assertFalse(report["blendg1_equation_verified"])
        self.assertFalse(report["ps1_hardware_abr_equivalence_verified"])

    def test_rejects_bad_observations(self):
        valid = event(0, 0, 1, 0, 0, 0)
        for key, value in (("abr", 4), ("abr", True), ("semi", -1),
                           ("accurate", 2), ("after", 65536),
                           ("front", -1), ("before", True)):
            row = dict(valid, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                summarize_observed_blends([row])
        with self.assertRaises(ValueError):
            summarize_observed_blends([event(0, 1, 0, 0, 1, 2)])

    def test_empty_log_does_not_fake_proof(self):
        report = summarize_observed_blends([])
        self.assertEqual(sum(b["calls"] for mode in
                             report["observed_semi_putpixel_by_accuracy_and_abr"]
                             for b in mode), 0)


if __name__ == "__main__":
    unittest.main()
