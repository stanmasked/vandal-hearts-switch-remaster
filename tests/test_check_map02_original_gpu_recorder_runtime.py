"""Asset-free ordering checks for the real original-PC DrawOTag recorder."""
import unittest

from tools.check_map02_original_gpu_recorder_runtime import (
    require_original_ot_pairs,
)


def events_for(primitives):
    result = []
    for kind in primitives:
        result.append({"operation": "draw", "phase": "before",
                       "primitive_type": kind})
        result.append({"operation": "draw", "phase": "after",
                       "primitive_type": kind})
    return result


class OriginalNativeDrawOTagPairTests(unittest.TestCase):
    def test_closed_original_ot_has_mode_f4_ft4_pairs(self):
        self.assertEqual(require_original_ot_pairs(
            events_for((5, 1, 2)), (5, 1, 2)), 3)

    def test_overflow_stores_only_first_32_f4_pairs(self):
        self.assertEqual(require_original_ot_pairs(
            events_for((1,) * 32), (1,) * 32), 32)

    def test_window_001_starts_at_state_only_dr_mode(self):
        rows = events_for((5, 1, 2))
        self.assertEqual(require_original_ot_pairs(rows, (5, 1, 2)), 3)
        for altered in ((1, 1, 2), (5, 2, 1)):
            with self.subTest(altered=altered), self.assertRaisesRegex(
                    ValueError, "order/phase"):
                require_original_ot_pairs(events_for(altered), (5, 1, 2))

    def test_missing_after_phase_and_transfer_packet_fail_closed(self):
        rows = events_for((5, 1, 2))
        with self.assertRaisesRegex(ValueError, "count"):
            require_original_ot_pairs(rows[:-1], (5, 1, 2))
        rows[1]["phase"] = "before"
        with self.assertRaisesRegex(ValueError, "order/phase"):
            require_original_ot_pairs(rows, (5, 1, 2))
        rows[1]["phase"] = "after"
        rows[0]["operation"] = "load"
        with self.assertRaisesRegex(ValueError, "order/phase"):
            require_original_ot_pairs(rows, (5, 1, 2))


if __name__ == "__main__":
    unittest.main()
