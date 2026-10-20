"""ROM-free smoke checks for Stage285 counter snapshot transition semantics."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_callback_transition import require,SCHEMA,KEYS


class SnapshotSemantics(unittest.TestCase):
    def test_schema_is_explicit(self):
        self.assertEqual(SCHEMA,"vh-map02-stage285-cpal-callback-transition-window/v1")
    def test_all_actual_host_reporter_counter_names(self):
        self.assertEqual(len(KEYS),7)
        self.assertIn("cpal_entries",KEYS)
        self.assertIn("cpal_returns",KEYS)
        self.assertIn("audioout_releases",KEYS)
    def test_missing_marker_is_fatal(self):
        with self.assertRaises(ValueError):
            require(False,"missing")
    def test_positive_validation_is_not_permissive(self):
        self.assertIsNone(require(True,"pass"))
    def test_exact_callback_timestamp_not_present_in_reporter(self):
        self.assertNotIn("cpal_entry_timestamp_ns",KEYS)
    def test_stream_error_lifecycle_not_present_in_counter_series(self):
        self.assertNotIn("cpal_error_callback_count",KEYS)


if __name__=="__main__":
    unittest.main()
