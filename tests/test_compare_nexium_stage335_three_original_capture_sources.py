"""Stage335 tests for authentic three-capture guest and host source comparison."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage334_capture_manifest import audit_original_capture
from compare_nexium_stage335_three_original_capture_sources import (
    audit_three,locate_runtime_root,ALL_PINS,RESULT,
)
from test_audit_nexium_stage334_capture_manifest import sample_source
from test_compare_nexium_stage326_original_host_clocks import sample as host_source


def sample_capture(index:int,*,last_duration:int,prior_duration:int)->dict:
    combined=sample_source(last_duration=last_duration,prior_duration=prior_duration)
    base=100000*(index+1)
    host=host_source(
        base,
        sizes=(100000+index*100000,101000+index*100000,120000+index*100000),
        wall_intervals=(357+index,4270+index),
        monotonic_intervals=(357687151+index*123,4269790190+index*1111))
    for k in ("legacy_csv","stage325","stage304","stage305"):
        combined[k]=host[k]
    combined["monotonic_csv"]=host["dual_csv"]
    return combined


class ThreeRealNeXiumCohortReplayTests(unittest.TestCase):
    def setUp(self):
        self.a=sample_capture(0,last_duration=11225937,prior_duration=32154011)
        self.b=sample_capture(1,last_duration=22352500,prior_duration=31247083)
        self.c=sample_capture(2,last_duration=40000000,prior_duration=30000000)

    def compare(self,a=None,b=None,c=None,old=None,new_receipt=None):
        first=self.a if a is None else a
        second=self.b if b is None else b
        third=self.c if c is None else c
        expected=[{k:audit_original_capture(first)[k] for k in ALL_PINS},
                  {k:audit_original_capture(second)[k] for k in ALL_PINS}]
        return audit_three([first,second,third],expected if old is None else old,
                           audit_original_capture(third) if new_receipt is None else new_receipt)

    def test_three_distinct_replayed_original_guest_and_host_sources(self):
        r=self.compare()
        self.assertEqual(r["result"],RESULT)
        self.assertEqual(len(r["cohorts"]),3)
        self.assertEqual([x["guest_last_software_duration_ns"] for x in r["cohorts"]],
                         [11225937,22352500,40000000])
        self.assertEqual([x["guest_prior_lower_median_software_ns"]
                          for x in r["cohorts"]],[32154011,31247083,30000000])
        self.assertEqual(r["cohorts"][2]["guest_prior_median_minus_last_software_ns"],
                         -10000000)
        self.assertEqual(r["cohorts"][2]["guest_last_first_possible_rank"],16)
        self.assertEqual([x["third_minus_original_guest_software_last_duration_ns"]
                          for x in r["third_minus_each_earlier_guest_software_deltas"]],
                         [28774063,17647500])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])
        self.assertTrue(r["new_original_stage334_receipt_reproduced_exactly"])

    def test_valid_new_fast_call_can_still_be_accepted(self):
        fast=sample_capture(2,last_duration=10000000,prior_duration=30000000)
        r=self.compare(c=fast)
        self.assertEqual(r["cohorts"][2]["guest_prior_median_minus_last_software_ns"],20000000)
        self.assertEqual(r["cohorts"][2]["guest_last_first_possible_rank"],1)

    def test_tampered_saved_new_stage334_manifest_rejected(self):
        saved=audit_original_capture(self.c)
        saved["original_guest_last_call_duration_software_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.compare(new_receipt=saved)

    def test_archived_old_pinned_guest_digest_mismatch_rejected(self):
        originals=[{k:audit_original_capture(s)[k] for k in ALL_PINS}
                   for s in (self.a,self.b)]
        originals[0]["original_guest_history_csv_sha256"]="0"*64
        with self.assertRaises(ExitTimelineError):
            self.compare(old=originals)

    def test_archived_old_host_digest_mismatch_rejected(self):
        originals=[{k:audit_original_capture(s)[k] for k in ALL_PINS}
                   for s in (self.a,self.b)]
        originals[1]["original_host_legacy_csv_sha256"]="0"*64
        with self.assertRaises(ExitTimelineError):
            self.compare(old=originals)

    def test_same_original_guest_cohort_is_not_three_independent_runs(self):
        with self.assertRaises(ExitTimelineError):
            self.compare(c=self.a)

    def test_duplicate_host_clock_sources_not_three_independent_runs(self):
        changed=copy.deepcopy(self.c)
        for k in ("legacy_csv","monotonic_csv","stage325","stage304"):
            changed[k]=copy.deepcopy(self.a[k])
        with self.assertRaises(ExitTimelineError):
            self.compare(c=changed)

    def test_original_new_guest_stage322_receipt_tampering_rejected(self):
        changed=copy.deepcopy(self.c)
        changed["stage322"]["final_call_duration_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.compare(c=changed)

    def test_original_new_strict_stage304_failure_rejected(self):
        changed=copy.deepcopy(self.c)
        changed["stage304"]["result"]="SOURCE_UNVERIFIED"
        with self.assertRaises(ExitTimelineError):
            self.compare(c=changed)

    def test_original_new_strict_stage305_failure_rejected(self):
        changed=copy.deepcopy(self.c)
        changed["stage305"]["all_original_stage299_through_stage304_evidence_replayed"]=False
        with self.assertRaises(ExitTimelineError):
            self.compare(c=changed)

    def test_ambiguous_original_host_archive_roots_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ExitTimelineError):
                locate_runtime_root(root)
            for parent in (root/"one",root/"two"):
                parent.mkdir()
                (parent/"host-dual-clock-stage325.json").write_text("{}")
            with self.assertRaises(ExitTimelineError):
                locate_runtime_root(root)

    def test_symlink_original_host_archive_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"real").mkdir()
            (root/"alias").symlink_to(root/"real",target_is_directory=True)
            with self.assertRaises(ExitTimelineError):
                locate_runtime_root(root/"alias")

    def test_report_contains_no_absolute_guest_or_host_clock_epochs(self):
        doc=self.compare()
        payload=json.dumps(doc,sort_keys=True)
        self.assertNotIn("begin_guest_ns",payload)
        self.assertNotIn("end_guest_ns",payload)
        self.assertNotIn("host_epoch_ms",payload)
        self.assertNotIn("123450000000",payload)
        self.assertFalse(doc["original_soundtrack_or_plus_audible_dropout_verified"])


if __name__=="__main__":
    unittest.main()
