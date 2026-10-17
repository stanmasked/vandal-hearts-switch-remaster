"""Independent journals describe different DDA events, not proven pixels."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.audit_map02_independent_dda_journals import (
    audit, SPAN_FILE, CANDIDATE_FILE,
)

SPAN = {
    "stage": "native_dda_span", "step": 0, "frame": 3,
    "primitive_ordinal": 9, "primitive_type": 2, "y": 12,
    "x_start": 10, "x_bound": 20, "clip_l": 5, "clip_r": 25,
    "clip_t": 10, "clip_b": 15,
}
CANDIDATE = {
    "stage": "rejected_edge_candidate", "step": 0, "frame": 3,
    "primitive_ordinal": 9, "reason": 4, "y": 9,
    "x_start": 10, "x_bound": 20, "clip_t": 10, "clip_b": 15,
}


def write(directory, filename, *rows):
    data = b"".join((json.dumps(row, sort_keys=True) + "\n").encode()
                    for row in rows)
    (directory / filename).write_bytes(data)
    return data


class IndependentJournalAuditTests(unittest.TestCase):
    def test_both_valid_journals_and_hashes_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            span_data = write(root, SPAN_FILE, SPAN)
            candidate_data = write(root, CANDIDATE_FILE, CANDIDATE)
            result = audit(root)
            self.assertEqual(result["schema"], "map02_independent_dda_journal_audit_v1")
            self.assertEqual(result["files"][SPAN_FILE]["sha256"],
                             hashlib.sha256(span_data).hexdigest())
            self.assertEqual(result["files"][CANDIDATE_FILE]["sha256"],
                             hashlib.sha256(candidate_data).hexdigest())
            self.assertEqual(result["shared_frame_ids"], [3])
            self.assertEqual(result["same_primitive_row_keys"], 0)
            for field in ("journal_origin_authenticated", "retail_map02_frame_verified",
                          "rejected_triangle_pixel_coverage_verified",
                          "hd_replacement_authorized"):
                self.assertIs(result[field], False)

    def test_candidate_only_is_missing_span_not_zero_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, CANDIDATE_FILE, CANDIDATE)
            result = audit(root)
            self.assertEqual(result["files"][CANDIDATE_FILE]["event_count"], 1)
            self.assertIsNone(result["files"][SPAN_FILE]["event_count"])
            self.assertFalse(result["files"][SPAN_FILE]["present"])
            self.assertEqual(result["shared_frame_ids"], [])

    def test_span_only_is_missing_candidate_not_zero_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            result = audit(root)
            self.assertIsNone(result["files"][CANDIDATE_FILE]["event_count"])
            self.assertFalse(result["files"][CANDIDATE_FILE]["present"])

    def test_same_row_key_does_not_infer_executed_rejected_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            write(root, CANDIDATE_FILE, dict(CANDIDATE, y=12, clip_t=13))
            result = audit(root)
            self.assertEqual(result["same_primitive_row_keys"], 1)
            self.assertFalse(result["rejected_triangle_pixel_coverage_verified"])

    def test_corruption_and_64_row_saturation_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            write(root, CANDIDATE_FILE, CANDIDATE)
            path = root / CANDIDATE_FILE
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
            with self.assertRaises(ValueError):
                audit(root)
            write(root, CANDIDATE_FILE,
                  *(dict(CANDIDATE, step=i) for i in range(64)))
            with self.assertRaises(ValueError):
                audit(root)

    def test_missing_and_symlinked_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "no native"):
                audit(root)
            write(root, SPAN_FILE, SPAN)
            (root / CANDIDATE_FILE).symlink_to(root / SPAN_FILE)
            with self.assertRaisesRegex(ValueError, "symlink"):
                audit(root)


if __name__ == "__main__":
    unittest.main()
