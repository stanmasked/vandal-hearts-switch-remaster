"""Stage338 strict Stage303 stop source diagnostic never replaces approval."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_nexium_stage338_failed_stage303_diagnostic import (
    bounded_stop_diagnosis,SCHEMA,RESULT,
)
from test_audit_nexium_pcm_recorder_stop import lifecycle


class Stage303SourceFailureClassificationTests(unittest.TestCase):
    def setUp(self):
        self.raw=b"\0"*4000
        self.stage302={"total_pcm_frames":1000,
                       "scene_pcm_sha256":__import__("hashlib").sha256(self.raw).hexdigest()}

    def test_stop_source_synthetically_valid_needs_original_strict_replay(self):
        r=bounded_stop_diagnosis(self.raw,self.stage302,lifecycle(3900,4000))
        self.assertEqual(r["gate"],"stage303_strict_replay_rejected_other")
        self.assertEqual(r["after_wait_minus_original_final_pcm_bytes"],0)
        self.assertFalse(r["strict_stage303_accepted"])

    def test_after_wait_more_than_final_original_PCM(self):
        r=bounded_stop_diagnosis(self.raw,self.stage302,lifecycle(3900,4004))
        self.assertEqual(r["gate"],"stage303_after_wait_not_equal_raw_pcm_bytes")
        self.assertEqual(r["after_wait_minus_original_final_pcm_bytes"],4)

    def test_after_wait_less_than_final_original_PCM(self):
        r=bounded_stop_diagnosis(self.raw,self.stage302,lifecycle(3900,3996))
        self.assertEqual(r["gate"],"stage303_after_wait_not_equal_raw_pcm_bytes")
        self.assertEqual(r["after_wait_minus_original_final_pcm_bytes"],-4)

    def test_stage302_claimed_frame_count_mismatch(self):
        bad=dict(self.stage302,total_pcm_frames=999)
        r=bounded_stop_diagnosis(self.raw,bad,lifecycle(3900,4000))
        self.assertEqual(r["gate"],"stage303_after_wait_not_equal_stage302_pcm_bytes")

    def test_scene_pcm_source_digest_mismatch(self):
        bad=dict(self.stage302,scene_pcm_sha256="0"*64)
        r=bounded_stop_diagnosis(self.raw,bad,lifecycle(3900,4000))
        self.assertEqual(r["gate"],"stage303_scene_pcm_SHA_differs_from_stage302")

    def test_sigint_snapshot_after_final_rejected_without_inventing_guest_clock(self):
        r=bounded_stop_diagnosis(self.raw,self.stage302,lifecycle(4100,4200))
        self.assertEqual(r["gate"],"stage303_after_wait_not_equal_raw_pcm_bytes")
        self.assertFalse(r["strict_stage303_accepted"])

    def test_stop_csv_wrong_order_not_reported_as_success(self):
        raw=lifecycle(3900,4000).replace(b"before_sigint",b"after_wait",1)
        r=bounded_stop_diagnosis(self.raw,self.stage302,raw)
        self.assertEqual(r["gate"],"stage303_stop_csv_invalid")

    def test_signal_fail_not_reported_as_success(self):
        r=bounded_stop_diagnosis(self.raw,self.stage302,lifecycle(3900,4000,signal=0))
        self.assertEqual(r["gate"],"stage303_stop_csv_invalid")

    def test_no_absolute_wall_times_reported(self):
        r=bounded_stop_diagnosis(self.raw,self.stage302,
                                 lifecycle(3999,4000,before=1712345678000,
                                           after=1712345678100))
        text=__import__("json").dumps(r,sort_keys=True)
        self.assertNotIn("1712345678000",text)
        self.assertNotIn("1712345678100",text)
        self.assertTrue(r["partial_frame_before_sigint"])
        self.assertEqual(r["stop_wall_interval_ms"],100)

    def test_invalid_stop_failed_signal_is_located_precisely(self):
        doc=bounded_stop_diagnosis(self.raw,self.stage302,
                                   lifecycle(3900,4000,signal=0))
        self.assertEqual(doc["original_stop_csv_failure"]["kind"],
                         "stop_csv_failed_or_missing_sigint_success")
        self.assertEqual(doc["original_stop_csv_failure"]["stop_signal_success_flags"],
                         [0,0])

    def test_invalid_stop_wall_regression_reports_only_relative_interval(self):
        doc=bounded_stop_diagnosis(self.raw,self.stage302,
                                   lifecycle(3900,4000,before=100200,after=100100))
        self.assertEqual(doc["original_stop_csv_failure"]["kind"],
                         "stop_csv_host_wall_clock_regression")
        self.assertEqual(doc["original_stop_csv_failure"]["original_stop_wall_delta_ms"],-100)
        self.assertNotIn("100200",__import__("json").dumps(doc))

    def test_invalid_stop_pcm_regression_is_source_rejected(self):
        doc=bounded_stop_diagnosis(self.raw,self.stage302,lifecycle(4100,4000))
        self.assertEqual(doc["original_stop_csv_failure"]["kind"],
                         "stop_csv_pcm_size_regression")
        self.assertEqual(doc["original_stop_csv_failure"][
            "after_wait_minus_before_sigint_pcm_bytes"],-100)

    def test_invalid_stop_row_order_is_explicit(self):
        bad=lifecycle(3900,4000).replace(b"before_sigint",b"after_wait",1)
        doc=bounded_stop_diagnosis(self.raw,self.stage302,bad)
        self.assertEqual(doc["original_stop_csv_failure"]["kind"],
                         "stop_csv_wrong_row_count_or_order")

    def test_invalid_stop_line_endings_are_explicit(self):
        bad=lifecycle(3900,4000).replace(b"\n",b"\r\n")
        doc=bounded_stop_diagnosis(self.raw,self.stage302,bad)
        self.assertEqual(doc["original_stop_csv_failure"]["kind"],
                         "stop_csv_noncanonical_line_endings_or_empty")

    def test_no_diagnostic_claims_physical_audio(self):
        for csv in (lifecycle(4000,4000),lifecycle(3990,4004),
                    lifecycle(4000,4000,signal=0)):
            self.assertFalse(bounded_stop_diagnosis(
                self.raw,self.stage302,csv)["strict_stage303_accepted"])


if __name__=="__main__":
    unittest.main()
