#!/usr/bin/env python3
"""Stage359 mutation tests are SYNTHETIC; originals get replayed in CI."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_stage359_same_source_tail_outcomes import (
    compare, PINS, FAIL_RUN, OK_RUN, AUDIO_BLOB, VERIFIED
)

def dummy(run,code,result,count,abandoned,reason,returned,elapsed):
    return {
        "run_id":run,"source_sha256":dict(PINS[run]),
        "code":code,"reason":reason,"raw_result":result,
        "wait_observed":True,"tail_return_confirmed":returned,
        "acquired":count,"released":count-abandoned,"abandoned":abandoned,
        "software_tail_attempt_to_return_ns":elapsed,
        "all_original_guest_sources_reaudited":True,
        "hardware_audio_verified":False,
    }
class Stage359Tests(unittest.TestCase):
    def pair(self):
        return (dummy(FAIL_RUN,4,59905,1414,1,"wait_failed",False,None),
                dummy(OK_RUN,7,0,1366,0,"return_confirmed",True,2000000))
    def run_check(self,a,b,sha1=AUDIO_BLOB,sha2=AUDIO_BLOB):
        return compare(a,b,sha1,sha2)
    def test_successful_same_worker_comparison(self):
        a,b=self.pair()
        r=self.run_check(a,b)
        self.assertEqual(r["result"],VERIFIED)
        self.assertEqual(r["both_original_tail_wait_bound_ns"],12000000)
        self.assertFalse(r["causal_scheduler_explanation_proven"])
        self.assertFalse(r["matched_controlled_experiment_completed"])
    def test_different_git_worker_blob_rejected(self):
        a,b=self.pair()
        with self.assertRaises(ValueError):self.run_check(a,b,sha2="0"*40)
    def test_unverified_audio_source_rejected(self):
        a,b=self.pair()
        with self.assertRaises(ValueError):self.run_check(a,b,sha1="0"*40)
    def test_false_failure_result_rejected(self):
        a,b=self.pair();a["raw_result"]=0
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_false_success_result_rejected(self):
        a,b=self.pair();b["raw_result"]=59905
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_contradictory_abandonment_rejected(self):
        a,b=self.pair();a["abandoned"]=0
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_not_the_exact_original_run_rejected(self):
        a,b=self.pair();a["run_id"]=True
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_same_guest_raw_source_rejected(self):
        a,b=self.pair();b["source_sha256"]=dict(a["source_sha256"])
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_claim_of_hardware_sound_rejected(self):
        a,b=self.pair();b["hardware_audio_verified"]=True
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_fabricated_failed_return_stamp_rejected(self):
        a,b=self.pair();a["software_tail_attempt_to_return_ns"]=12000000
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_missing_success_return_stamp_rejected(self):
        a,b=self.pair();b["software_tail_attempt_to_return_ns"]=None
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_forged_original_source_proof_rejected(self):
        a,b=self.pair();a["all_original_guest_sources_reaudited"]=False
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_false_timeout_reason_rejected(self):
        a,b=self.pair();a["reason"]="release_mismatch"
        with self.assertRaises(ValueError):self.run_check(a,b)
    def test_forged_return_flag_rejected(self):
        a,b=self.pair();b["tail_return_confirmed"]=False
        with self.assertRaises(ValueError):self.run_check(a,b)

if __name__=="__main__":
    unittest.main()
