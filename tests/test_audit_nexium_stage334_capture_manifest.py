"""Stage334 independent guest-software / host-clock capture manifest tests."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_nexium_stage334_capture_manifest import audit_original_capture,RESULT
from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_host_clock_pairs import ClockPairError
from test_compare_nexium_stage328_original_playbuffer_histories import cohort
from test_compare_nexium_stage326_original_host_clocks import sample


def sample_source(last_duration=11225937,prior_duration=32154011):
    g=cohort(last_duration=last_duration,prior_duration=prior_duration)
    h=sample(100000)
    return {**g,**h,
            "monotonic_csv":h.pop("dual_csv"),
            "stage304":{
                "result":"SOURCE_BOUND_BUFFERED_EXIT_CONTROL_TIMELINE_RECONCILED",
                "all_original_source_witnesses_replayed":True,
                "physical_Nintendo_Switch_audio_tested":False,
                "exit_control_snapshots":[{
                    "event":row.split(",")[0],
                    "pcm_bytes":int(row.split(",")[1]),
                    "host_epoch_ms":int(row.split(",")[2]),
                } for row in h["legacy_csv"].decode().splitlines()[1:]],
            },
            "stage305":{
                "result":"SOURCE_BOUND_PLUS_BUFFERED_ZERO_RUN_ONSET_FENCED",
                "all_original_stage299_through_stage304_evidence_replayed":True,
                "physical_Nintendo_Switch_audio_tested":False,
            },
           }


class OriginalSingleNeXiumSourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.data=sample_source()

    def audit(self,data=None):
        return audit_original_capture(self.data if data is None else data)

    def test_successful_source_manifest_guest_and_host_exact_deltas(self):
        r=self.audit()
        self.assertEqual(r["result"],RESULT)
        self.assertEqual(r["original_guest_last_call_duration_software_ns"],11225937)
        self.assertEqual(r["original_guest_prior_lower_median_software_ns"],32154011)
        self.assertEqual(r["original_guest_prior_median_minus_last_software_ns"],20928074)
        self.assertEqual(r["original_guest_prior_faster_equal_slower_counts"],[0,0,15])
        self.assertEqual(r["original_guest_last_call_first_possible_rank"],1)
        self.assertEqual(len(r["original_host_control_deltas"]),2)
        self.assertTrue(r["original_stage320_322_325_receipts_recomputed_from_exact_sources"])
        self.assertTrue(r["original_stage304_305_strict_success_receipts_checked"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_later_new_real_sample_may_have_slower_final_call(self):
        r=self.audit(sample_source(last_duration=40_000_000,prior_duration=32_000_000))
        self.assertEqual(r["original_guest_prior_faster_equal_slower_counts"],[15,0,0])
        self.assertEqual(r["original_guest_last_call_first_possible_rank"],16)
        self.assertEqual(r["original_guest_prior_median_minus_last_software_ns"],-8_000_000)

    def test_original_guest_history_byte_tampering_rejected(self):
        x=copy.deepcopy(self.data)
        x["history_csv"]+=b"tamper"
        with self.assertRaises((ValueError,ExitTimelineError)):
            self.audit(x)

    def test_original_guest_stage322_forged_summary_rejected(self):
        x=copy.deepcopy(self.data)
        x["stage322"]["prior_successful_duration_lower_median_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(x)

    def test_original_guest_stage320_forged_source_sha_rejected(self):
        x=copy.deepcopy(self.data)
        x["stage320"]["original_last_playbuffer_csv_sha256"]="0"*64
        with self.assertRaises(ExitTimelineError):
            self.audit(x)

    def test_original_host_monotonic_csv_changed_rejected(self):
        x=copy.deepcopy(self.data)
        x["monotonic_csv"]=x["monotonic_csv"].replace(b"123450000000",b"123450000001")
        with self.assertRaises((ClockPairError,ValueError)):
            self.audit(x)

    def test_original_host_stage325_forged_receipt_rejected(self):
        x=copy.deepcopy(self.data)
        x["stage325"]["wall_epoch_equal_pair_count"]+=1
        with self.assertRaises(ClockPairError):
            self.audit(x)

    def test_original_host_stage304_control_identity_rejected(self):
        x=copy.deepcopy(self.data)
        x["stage304"]["exit_control_snapshots"][1]["pcm_bytes"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(x)

    def test_original_strict_pcm_stage305_failure_rejected(self):
        x=copy.deepcopy(self.data)
        x["stage305"]["result"]="STAGE305_NOT_VERIFIED"
        with self.assertRaises(ExitTimelineError):
            self.audit(x)

    def test_original_guest_or_host_timestamps_not_exposed_in_manifest(self):
        r=self.audit()
        s=json.dumps(r,sort_keys=True)
        self.assertNotIn("begin_guest_ns",s)
        self.assertNotIn("end_guest_ns",s)
        self.assertNotIn("host_epoch_ms",s)
        self.assertNotIn("123450000000",s)
        self.assertNotIn("pcm_samples",s)
        self.assertFalse(r["no_guest_to_host_clock_alignment_proven"] is False)


if __name__=="__main__":
    unittest.main()
