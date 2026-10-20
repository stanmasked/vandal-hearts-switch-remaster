#!/usr/bin/env python3
"""Stage368 synthetic *negative controls*, not original NeXium guest evidence."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_nexium_stage368_attested_guest as m
import audit_nexium_stage368_wait_descriptor as fmt
from test_audit_nexium_stage368_wait_descriptor import make_sources

RUN=39387200000
SHA="a"*40
ATTEMPT=1
def fresh(root):
    source=root/f"vh-nexium-stage266-{RUN}"
    sd=source/"sdmc/switch/vandal-hearts-remake"
    make_sources(sd)
    old351=(sd/fmt.NAMES["reason"]).read_bytes()
    old357=(sd/fmt.NAMES["result"]).read_bytes()
    h351=hashlib.sha256(old351).hexdigest()
    h357=hashlib.sha256(old357).hexdigest()
    nro={
      "result":m.EXPECTED_NRO,"git_sha":SHA,"run_id":RUN,"run_attempt":ATTEMPT,
      "nro_bytes":123456,"nro_sha256":"b"*64,
    }
    prior351={
      "result":m.EXPECTED_S351,
      "original_guest_tail_reason_bytes_preserved":True,
      "prior_stage313_and_stage348_original_bytes_reaudited":True,
      "physical_Nintendo_Switch_audio_tested":False,
      "original_guest_tail_reason_csv_sha256":h351,
      "original_guest_tail_reason_source_observed":True,
      "reason_code":7,
    }
    prior357={
      "result":m.EXPECTED_S357,
      "original_guest_wait_result_bytes_preserved":True,
      "physical_Nintendo_Switch_audio_tested":False,
      "original_guest_wait_result_csv_sha256":h357,
      "original_stage351_source_sha256":h351,
      "original_guest_wait_result_source_observed":True,
      "stage351_reason_code":7,"audout_wait_result_raw":0,
    }
    return source,sd,nro,prior351,prior357,old351,old357

class Stage368OriginalRunBindings(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.source,self.sd,self.nro,self.reason,self.wait,
         self.old_reason,self.old_wait)=fresh(self.root)
    def verify(self,**changed):
        args={
          "source_root":self.source,"guest_root":self.sd,"run_id":RUN,
          "git_sha":SHA,"attempt":ATTEMPT,"preflight":self.nro,
          "stage351":self.reason,"stage357":self.wait,
          "reason_copy":self.old_reason,"wait_copy":self.old_wait
        }
        args.update(changed)
        return m.attest(**args)
    def test_valid_synthetic_fixture_proves_only_binding_algorithm(self):
        result=self.verify()
        self.assertEqual(result["result"],m.VERDICT)
        self.assertTrue(result["original_neXium_archive_proven"])
        self.assertFalse(result["physical_Nintendo_Switch_audio_tested"])
        self.assertFalse(result["old_0xEA01_cause_proven"])
        self.assertEqual(result["neXium_nro_git_sha"],SHA)
    def test_wrong_run_attempt_head_or_nro_status_rejected(self):
        for key,value in (("run_id",RUN+1),("run_attempt",2),
                          ("git_sha","f"*40),
                          ("result","NOT_A_VALIDATED_NRO")):
            with self.subTest(key=key):
                changed=copy.deepcopy(self.nro)
                changed[key]=value
                with self.assertRaises(ValueError):
                    self.verify(preflight=changed)
    def test_stage351_and_357_false_signatures_rejected(self):
        for source,key,value in (
            ("reason","original_guest_tail_reason_csv_sha256","0"*64),
            ("reason","prior_stage313_and_stage348_original_bytes_reaudited",False),
            ("wait","original_guest_wait_result_csv_sha256","0"*64),
            ("wait","original_stage351_source_sha256","0"*64),
            ("wait","audout_wait_result_raw",59905),
            ("wait","original_guest_wait_result_bytes_preserved",False),
        ):
            with self.subTest(source=source,key=key):
                changed=copy.deepcopy(getattr(self,source))
                changed[key]=value
                with self.assertRaises(ValueError):
                    self.verify(**({"stage351" if source=="reason" else "stage357":changed}))
    def test_original_copy_swaps_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(reason_copy=self.old_wait)
        with self.assertRaises(ValueError):
            self.verify(wait_copy=self.old_reason)
    def test_guest_root_outside_same_run_and_replaced_descriptor_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(run_id=RUN+1)
        with self.assertRaises(ValueError):
            self.verify(guest_root=self.root)
        path=self.sd/fmt.NAMES["descriptor"]
        raw=path.read_text()
        path.write_text(raw.replace("released_count_reported,1",
                                         "released_count_reported,0"))
        with self.assertRaises(ValueError):
            self.verify()
    def test_real_timeout_fixture_never_proves_cause(self):
        make_sources(self.sd,code=4,raw=0xEA01,count=0,present=0,same=0)
        reason=(self.sd/fmt.NAMES["reason"]).read_bytes()
        wait=(self.sd/fmt.NAMES["result"]).read_bytes()
        self.reason["original_guest_tail_reason_csv_sha256"]=hashlib.sha256(reason).hexdigest()
        self.reason["reason_code"]=4
        self.wait["original_guest_wait_result_csv_sha256"]=hashlib.sha256(wait).hexdigest()
        self.wait["original_stage351_source_sha256"]=hashlib.sha256(reason).hexdigest()
        self.wait["audout_wait_result_raw"]=0xEA01
        self.wait["stage351_reason_code"]=4
        r=self.verify(reason_copy=reason,wait_copy=wait)
        self.assertEqual(r["raw_wait_result"],0xEA01)
        self.assertFalse(r["old_0xEA01_cause_proven"])
        self.assertFalse(r["actual_queue_depth_measured"])

if __name__=="__main__":
    unittest.main()
