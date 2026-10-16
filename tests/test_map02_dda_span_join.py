import unittest
from dataclasses import replace
from tools.map02_dda_span_join import Span, reconcile

class JoinTests(unittest.TestCase):
    def setUp(self):
        self.span = Span(12, 2, 9, 10, 20, 5, 25, 10, 15)
        self.event = dict(frame=12, primitive_ordinal=2, y=9, x=12, reason=4, step=0)

    def test_matching_top_both_walks(self):
        for reason in (4, 7):
            r = reconcile([dict(self.event, reason=reason)], [self.span])[0]
            self.assertTrue(r["vertical_rejected_and_x_in_supplied_span"])
            self.assertFalse(r["original_triangle_coverage_verified"])

    def test_matching_bottom_both_walks(self):
        for reason in (5, 6):
            span = replace(self.span, y=16)
            event = dict(self.event, y=16, reason=reason)
            self.assertTrue(reconcile([event], [span])[0]["x_inside_supplied_unclipped_span"])

    def test_span_end_exclusive(self):
        self.assertFalse(reconcile([dict(self.event, x=20)], [self.span])[0]["x_inside_supplied_unclipped_span"])

    def test_reason_boundary_refusal(self):
        with self.assertRaises(ValueError): reconcile([dict(self.event, y=10)], [replace(self.span, y=10)])

    def test_mismatched_primitive(self):
        with self.assertRaisesRegex(ValueError, 'no unique'): reconcile([self.event], [replace(self.span, primitive_ordinal=3)])

    def test_duplicate_span(self):
        with self.assertRaisesRegex(ValueError, 'duplicate span'): reconcile([self.event], [self.span, self.span])

    def test_duplicate_event(self):
        with self.assertRaises(ValueError): reconcile([self.event, dict(self.event, step=1)], [self.span])

    def test_reordered_steps(self):
        with self.assertRaises(ValueError): reconcile([dict(self.event, step=1)], [self.span])

    def test_truncation_barrier(self):
        with self.assertRaises(ValueError): reconcile([dict(self.event, step=i) for i in range(64)], [self.span])

    def test_wrong_frame_and_bool_refused(self):
        with self.assertRaises(ValueError): reconcile([self.event], [replace(self.span, frame=13)])
        with self.assertRaises(ValueError): reconcile([dict(self.event, x=True)], [self.span])

    def test_unexpected_fields_refused(self):
        with self.assertRaises(ValueError): reconcile([dict(self.event, provenance_verified=True)], [self.span])

if __name__ == '__main__':
    unittest.main()
