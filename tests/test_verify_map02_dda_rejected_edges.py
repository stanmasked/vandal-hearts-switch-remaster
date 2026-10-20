"""Fail-closed rejected edge candidate evidence checks."""
import json
import unittest
from tools.verify_map02_dda_rejected_edges import validate


def event(reason=7, y=9, step=0):
    return {"stage": "rejected_edge_candidate", "step": step,
            "frame": 2, "primitive_ordinal": 3, "reason": reason,
            "y": y, "x_start": 7, "x_bound": 18,
            "clip_t": 10, "clip_b": 15}


def pack(*events):
    return b"\n".join(json.dumps(e, separators=(",", ":")).encode()
                      for e in events) + b"\n"


class CandidateJournalTests(unittest.TestCase):
    def test_four_vertical_branches(self):
        items = [event(4, 9, 0), event(5, 16, 1),
                 event(6, 16, 2), event(7, 9, 3)]
        self.assertEqual(validate(pack(*items)), items)

    def test_reject_tampering(self):
        base = event()
        cases = [
            pack(event(5, 9)), pack(event(99, 9)),
            pack(dict(base, step=1)), pack(dict(base, frame=0)),
            pack(dict(base, clip_t=17, clip_b=15)),
            pack(dict(base, y=10)), pack(dict(base, reason=True)),
            pack(dict(base, stage="executed_span")),
            pack(dict(base, unexpected=1)),
            pack(dict(base, x_bound=float("nan"))),
            pack(dict(base, x_start=1 << 40)),
            pack(dict(base, frame=1 << 40)),
            pack(base).replace(b"\n", b"\r\n"),
            pack(base)[:-1], b"", b"{}\n",
            b'{"step":0,"step":1}\n',
            pack(*[event(step=i) for i in range(64)]),
        ]
        for candidate in cases:
            with self.subTest(candidate=candidate[:70]):
                with self.assertRaises(ValueError):
                    validate(candidate)


if __name__ == "__main__":
    unittest.main()
