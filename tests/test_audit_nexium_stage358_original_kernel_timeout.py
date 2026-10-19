#!/usr/bin/env python3
"""Stage358 original timeout source pairing regressions; synthetic ONLY."""
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_stage358_original_kernel_timeout import (
    verify,WAIT,TAPER,LEASE,REASON,RUN_ID,VERIFIED
)
from audit_nexium_guest_tail_wait_result_stage357 import (
    parse_source,VERIFIED as WAIT_VERDICT
)
from audit_nexium_stage352_three_original_tail_sources import (
    VERIFIED as TRIPLE_VERDICT
)

class TestStage358(unittest.TestCase):
    def fixture(self):
        raw=(b"scope,value\n"
             b"software_wait_result_only,1\n"
             b"wait_result_observed,1\n"
             b"audout_wait_result_raw,59905\n"
             b"stage351_tail_reason_code,4\n")
        self.assertEqual(hashlib.sha256(raw).hexdigest(),WAIT)
        old={
            "result":TRIPLE_VERDICT,
            "original_neXium_run_id":RUN_ID,
            "original_guest_csv_sha256":{
                "stage313_last_audio_page_and_tail":TAPER,
                "stage348_software_PCM_lease":LEASE,
                "stage351_exit_tail_reason":REASON,
            },
            "tail_reason_code":4,"tail_reason_name":"wait_failed",
            "tail_attempted":True,
            "tail_descriptor_return_confirmed":False,
            "lease_pages_acquired":1414,"lease_pages_released":1413,
            "abandoned_sessions":1,
            "exact_archived_original_CSV_bytes_reaudited":True,
            "three_distinct_guest_source_receipts_matched":True,
            "physical_Nintendo_Switch_audio_tested":False,
        }
        old351={
            "schema":"vh-stage351-original-guest-exit-tail-reason/v1",
            "result":"ORIGINAL_GUEST_EXIT_TAIL_CAUSE_SOURCE_VERIFIED",
            "reason_code":4,
            "original_guest_tail_reason_csv_sha256":REASON,
            "prior_stage313_and_stage348_original_bytes_reaudited":True,
            "bound_to_original_stage313_tail_observation":True,
            "bound_to_original_stage348_lease_observation":True,
            "physical_Nintendo_Switch_audio_tested":False,
        }
        r=parse_source(raw,old351)
        r["original_guest_source_relative_path"]=(
            "sdmc/switch/vandal-hearts-remake/audio-exit-tail-wait-result-000.csv"
        )
        self.assertEqual(r["result"],WAIT_VERDICT)
        return old,old351,r,raw

    def test_canonical_original_shape_proves_kernel_timeout(self):
        x=verify(*self.fixture())
        self.assertEqual(x["result"],VERIFIED)
        self.assertEqual(x["stage357_audout_wait_raw_result_hex"],"0xEA01")
        self.assertEqual(x["result_module"],1)
        self.assertEqual(x["result_description"],117)
        self.assertFalse(x["underlying_event_wait_call_site_uniquely_proven"])
    def test_reject_modified_original_guest_wait(self):
        a,b,c,d=self.fixture()
        with self.assertRaises(ValueError):verify(a,b,c,d.replace(b"59905",b"59906"))
    def test_reject_old_run_id(self):
        a,b,c,d=self.fixture();a["original_neXium_run_id"]-=1
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_fake_original_sha(self):
        a,b,c,d=self.fixture();a["original_guest_csv_sha256"]["stage348_software_PCM_lease"]="0"*64
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_lease_imbalance(self):
        a,b,c,d=self.fixture();a["lease_pages_released"]+=1
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_success_claim(self):
        a,b,c,d=self.fixture();a["tail_reason_code"]=7
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_new_original_receipt_forgery(self):
        a,b,c,d=self.fixture();c["audout_wait_result_raw"]=2
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_stage351_receipt_sha_forgery(self):
        a,b,c,d=self.fixture();b["original_guest_tail_reason_csv_sha256"]="0"*64
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_hardware_claim(self):
        a,b,c,d=self.fixture();c["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_raw_receipt_missing(self):
        a,b,c,d=self.fixture();del c["original_guest_wait_result_bytes_preserved"]
        with self.assertRaises(ValueError):verify(a,b,c,d)
    def test_reject_fabricated_earlier_stage_flag(self):
        a,b,c,d=self.fixture();a["three_distinct_guest_source_receipts_matched"]=False
        with self.assertRaises(ValueError):verify(a,b,c,d)

if __name__=="__main__":
    unittest.main()
