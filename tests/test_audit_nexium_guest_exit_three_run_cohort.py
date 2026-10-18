"""Stage312 verify three guest exits, truthful original-byte provenance tiers."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"tools"))
sys.path.insert(0,str(HERE/"tests"))

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks
from replay_nexium_original_guest_exit_archive import (
    reconstructed_stage310, independent_archive_replay,
)
from audit_nexium_guest_exit_three_run_cohort import audit_three
from test_compare_nexium_guest_exit_cohort import fixture


class MixedGuestExitProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.samples=[fixture(0,raw_original=False),
                      fixture(1,raw_original=False),fixture(2)]
        # Stage308's second historical capture includes an independent
        # optical/guest SHA receipt. The first older Stage307 archive
        # cannot cryptographically reverify its absent original CSV.
        second=list(self.samples[1])
        second[4]=audit_guest_clocks(second[1],second[2])
        self.samples[1]=tuple(second)
        src=list(self.samples[2])
        self.stage308=audit_guest_clocks(src[1],src[2])
        src[4]=self.stage308
        self.samples[2]=tuple(src)
        self.replay_inputs=(src[3],src[1],src[2],src[4],
                            reconstructed_stage310(src[3],src[4]))
        self.record=independent_archive_replay(
            *self.replay_inputs,src[0])
        self.raw_id=src[0]

    def check(self,samples=None,inputs=None,record=None,run=None):
        return audit_three(
            self.samples if samples is None else samples,
            self.raw_id if run is None else run,
            self.replay_inputs if inputs is None else inputs,
            self.record if record is None else record)

    def test_three_distinct_captures_mixed_provenance_and_guest_median(self):
        r=self.check()
        self.assertEqual(r["run_count"],3)
        self.assertEqual(r["original_csv_byte_verified_runs"],[self.raw_id])
        self.assertEqual(len(r["capture_time_source_audited_JSON_only_runs"]),2)
        dist=r["guest_software_duration_distribution_ns"]["plus_to_join_ns"]
        self.assertEqual(dist["median_ns"],2630)
        self.assertEqual([x["guest_software_ns"] for x in dist["observations"]],
                         [2600,2630,2660])
        self.assertTrue(r["older_guest_csv_bytes_NOT_reaudited"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_other_archives_cannot_fake_raw_source_evidence(self):
        samples=list(self.samples)
        old=list(samples[1])
        old[3]=fixture(1)[3]
        samples[1]=tuple(old)
        with self.assertRaises(TraceError):
            self.check(samples=samples)

    def test_raw_original_requires_exact_matching_independent_source(self):
        bad=list(self.replay_inputs)
        bad[0]=bad[0]+b"\n"
        with self.assertRaises(TraceError):
            self.check(inputs=tuple(bad))

    def test_replaced_original_optical_png_is_rejected(self):
        bad=list(self.replay_inputs)
        bad[1]=self.samples[1][1]
        with self.assertRaises(TraceError):
            self.check(inputs=tuple(bad))

    def test_wrong_independent_stage311_checksum_rejected(self):
        x=copy.deepcopy(self.record)
        x["original_guest_csv_sha256"]="f"*64
        with self.assertRaises(TraceError):
            self.check(record=x)

    def test_second_archived_stage308_binds_guest_csv_hash(self):
        x=copy.deepcopy(self.samples)
        source=list(x[1])
        fake=copy.deepcopy(source[2])
        fake["guest_exit_csv_sha256"]="0"*64
        source[2]=fake
        x[1]=tuple(source)
        with self.assertRaises(TraceError):
            self.check(samples=x)

    def test_source_run_must_be_present_with_original_bytes(self):
        with self.assertRaises(TraceError):
            self.check(run=999)
        with self.assertRaises(TraceError):
            self.check(run=self.samples[0][0])

    def test_identical_source_images_are_not_independent(self):
        x=list(self.samples)
        broken=list(x[1])
        broken[1]=x[0][1]
        x[1]=tuple(broken)
        with self.assertRaises(TraceError):
            self.check(samples=x)

    def test_more_or_fewer_than_three_reruns_are_not_accepted(self):
        with self.assertRaises(TraceError):
            self.check(samples=self.samples[:2])
        with self.assertRaises(TraceError):
            self.check(samples=self.samples+self.samples[:1])

    def test_guest_exit_stage311_intervals_must_match_real_original(self):
        x=copy.deepcopy(self.record)
        x["guest_software_exit_intervals_ns"]["audout_close_to_worker_join_ns"]+=1
        with self.assertRaises(TraceError):
            self.check(record=x)

    def test_verified_archived_stage308_cannot_be_forged(self):
        x=copy.deepcopy(self.samples)
        src=list(x[2])
        stage=copy.deepcopy(src[4])
        stage["guest_exit_order_verified"]=False
        src[4]=stage
        x[2]=tuple(src)
        with self.assertRaises(TraceError):
            self.check(samples=x)

    def test_repeatable_never_infers_physical_audio_or_PCM_clock(self):
        r=self.check()
        self.assertEqual(r,self.check())
        self.assertIs(r["host_pcm_to_guest_software_clock_calibrated"],False)
        self.assertIs(r["audible_audio_dropout_verified"],False)
        self.assertIs(r["original_retail_soundtrack_verified"],False)


if __name__=="__main__":
    unittest.main()
