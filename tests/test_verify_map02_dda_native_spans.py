import json
import unittest
from tools.verify_map02_dda_native_spans import parse_native_spans

BASE = {"stage":"native_dda_span","step":0,"frame":3,
        "primitive_ordinal":9,"primitive_type":2,"y":12,
        "x_start":10,"x_bound":20,"clip_l":5,"clip_r":25,
        "clip_t":10,"clip_b":15}

def serialize(*rows):
    return b"".join((json.dumps(row, sort_keys=True)+"\n").encode() for row in rows)

class SpanJournalTests(unittest.TestCase):
    def test_one_entered_span(self):
        item, = parse_native_spans(serialize(BASE))
        self.assertEqual((item.x_start, item.x_bound), (10, 20))

    def test_contiguous_rows(self):
        rows = [dict(BASE, step=i, y=12+i) for i in range(2)]
        self.assertEqual(len(parse_native_spans(serialize(*rows))), 2)

    def test_reject_bad_step(self):
        with self.assertRaises(ValueError):
            parse_native_spans(serialize(dict(BASE, step=1)))

    def test_reject_bool_and_extra(self):
        for row in (dict(BASE, y=True), dict(BASE, attested=True)):
            with self.assertRaises(ValueError): parse_native_spans(serialize(row))

    def test_reject_inverted_geometry(self):
        for row in (dict(BASE, x_start=21), dict(BASE, clip_t=20)):
            with self.assertRaises(ValueError): parse_native_spans(serialize(row))

    def test_reject_missing_newline_and_saturation(self):
        with self.assertRaises(ValueError): parse_native_spans(serialize(BASE).rstrip(b"\n"))
        with self.assertRaises(ValueError):
            parse_native_spans(serialize(*(dict(BASE, step=i) for i in range(64))))

    def test_reject_nonfinite(self):
        with self.assertRaises(ValueError):
            parse_native_spans(serialize(BASE).replace(b"12", b"NaN", 1))

    def test_reject_duplicate_json_keys(self):
        raw = serialize(BASE)
        raw = raw.replace(b'"frame": 3', b'"frame": 3, "frame": 3')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_native_spans(raw)

    def test_reject_crlf(self):
        with self.assertRaises(ValueError):
            parse_native_spans(serialize(BASE).replace(b"\n", b"\r\n"))

    def test_reject_entered_row_outside_vertical_clip(self):
        for row in (dict(BASE, y=9), dict(BASE, y=16)):
            with self.assertRaisesRegex(ValueError, "geometry"):
                parse_native_spans(serialize(row))

    def test_reject_duplicate_entered_primitive_row(self):
        rows = (dict(BASE, step=0), dict(BASE, step=1))
        with self.assertRaisesRegex(ValueError, "duplicate entered"):
            parse_native_spans(serialize(*rows))

    def test_reject_backward_primitive(self):
        with self.assertRaises(ValueError):
            parse_native_spans(serialize(dict(BASE, step=0, primitive_ordinal=10),
                                         dict(BASE, step=1, primitive_ordinal=9)))

if __name__ == "__main__":
    unittest.main()
