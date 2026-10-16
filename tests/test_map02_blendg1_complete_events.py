"""Regress strict SHA-bound witness JSONL framing without publishing pixels."""
import unittest

from tools.verify_map02_blendg1_witness import complete_events, MAX_EVENTS


class CompleteWitnessLogTests(unittest.TestCase):
    def test_accepts_complete_canonical_lines(self):
        self.assertEqual(complete_events(b'{"stage":"x"}\n', "test"),
                         [{"stage": "x"}])
        self.assertEqual(len(complete_events(b'{}\n' * (MAX_EVENTS - 1),
                                             "test")), MAX_EVENTS - 1)

    def test_rejects_missing_newline_empty_and_crlf(self):
        for raw in (b"", b"{}", b'{}\n\n', b'{}\r\n',
                    b'{}\n{}', b'\n', b'{} \n\n', b'{}\n' * MAX_EVENTS):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                complete_events(raw, "test")

    def test_rejects_malformed_json_even_with_newline(self):
        for raw in (b"{oops}\n", b'{"stage":\n', b'[]\n' + b'{}\n'):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                complete_events(raw, "test")


if __name__ == "__main__":
    unittest.main()
