#!/usr/bin/env python3
"""Synthetic/negative Stage370 three-original-cohort provenance checks."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage370_distinct_original_wait_cohorts as a

def fixture():
    old={
      "result":a.OLD_VERDICT,
      "timeout_original_run_id":a.OLD_RUN,
      "success_original_run_id":a.PREVIOUS_SUCCESS_RUN,
      "two_distinct_original_archives_reaudited":True,
      "timeout_software_wait_raw_result":59905,
      "timeout_software_wait_raw_hex":"0xEA01",
      "success_software_wait_raw_result":0,
      "timeout_software_acquired_released_abandoned":[1414,1413,1],
      "success_software_acquired_released_abandoned":[1438,1438,0],
      "timeout_old_stage360_queue_probe_recorded":False,
      "timeout_old_pre_submit_queue_depth":None,
      "timeout_old_pre_submit_probe_age_ns":None,
      "timeout_and_success_have_same_schema_queue_telemetry":False,
      "causal_inference_about_old_timeout_proven":False,
      "timeout_root_cause_unique_to_kernel_callsite_proven":False,
      "real_hardware_Nintendo_Switch_speaker_or_DAC_verified":False,
      "timeout_stage313_348_351_357_sha256":{
        "stage313":"a"*64,"stage348":"b"*64,
        "stage351":"c"*64,"stage357":"d"*64},
      "timeout_original_guest_receipt_sha256":{
        "stage313":"e"*64,"stage314":"f"*64,
        "stage348":"1"*64,"stage351":"2"*64,"stage357":"3"*64},
    }
    latest={
      "result":a.LATEST_VERDICT,
      "source_run_id":a.LATEST_SUCCESS_RUN,
      "source_artifact_id":12249301260,
      "source_attempt":1,
      "source_git_sha":"4"*40,
      "same_run_nro_sha256":"5"*64,
      "original_stage368_step_succeeded":True,
      "whole_runtime_run_succeeded":True,
      "stage351_reason_code":7,
      "service_result_raw":0,
      "service_returned_descriptor_count":1,
      "returned_pointer_present":True,
      "returned_pointer_matches_submitted":True,
      "old_0xEA01_cause_proven":False,
      "exit_queue_depth_measured":False,
      "physical_Switch_sound_tested":False,
      "independently_reopened_original_csv_sha256":{
        "reason":"6"*64,"result":"7"*64,"descriptor":"8"*64},
    }
    metas=[]
    for key,run in (("stage365",a.STAGE365_RUN),("stage369",a.STAGE369_RUN)):
        ident,name,digest=a.ARTIFACTS[key]
        metas.append({"id":ident,"name":name,"digest":digest,
                      "expired":False,"size_in_bytes":1000,
                      "workflow_run":{"id":run,"head_sha":"9"*40}})
    return old,latest,*metas

class Stage370Tests(unittest.TestCase):
    def setUp(self):
        self.old,self.latest,self.meta365,self.meta369=fixture()
    def check(self,**changed):
        args={"old":self.old,"latest":self.latest,
              "meta365":self.meta365,"meta369":self.meta369}
        args.update(changed)
        return a.compare(**args)
    def test_three_distinct_originals_no_causal_pairing(self):
        result=self.check()
        self.assertEqual(result["result"],a.VERDICT)
        self.assertEqual(result["earlier_original_timeout_run"],a.OLD_RUN)
        self.assertIsNone(result["old_timeout_stage368_descriptor_count"])
        self.assertIsNone(result["older_success_stage368_descriptor_count"])
        self.assertFalse(result["old_0xEA01_causality_proven"])
        self.assertTrue(result["latest_success_pointer_matches_submitted"])
    def test_wrong_timeout_or_old_success_run_rejected(self):
        for key,value in (("timeout_original_run_id",a.LATEST_SUCCESS_RUN),
                          ("success_original_run_id",a.LATEST_SUCCESS_RUN)):
            with self.subTest(key=key):
                x=copy.deepcopy(self.old);x[key]=value
                with self.assertRaises(ValueError):self.check(old=x)
    def test_forged_timeout_zero_lease_or_probe_rejected(self):
        for key,value in (("timeout_software_wait_raw_result",0),
                          ("timeout_software_acquired_released_abandoned",[1414,1414,0]),
                          ("timeout_old_pre_submit_queue_depth",0),
                          ("timeout_old_stage360_queue_probe_recorded",True),
                          ("causal_inference_about_old_timeout_proven",True)):
            with self.subTest(key=key):
                x=copy.deepcopy(self.old);x[key]=value
                with self.assertRaises(ValueError):self.check(old=x)
    def test_changed_latest_descriptor_and_success_rejected(self):
        for key,value in (("source_run_id",a.OLD_RUN),
                          ("source_artifact_id",0),
                          ("service_returned_descriptor_count",0),
                          ("returned_pointer_matches_submitted",False),
                          ("old_0xEA01_cause_proven",True),
                          ("whole_runtime_run_succeeded",False)):
            with self.subTest(key=key):
                x=copy.deepcopy(self.latest);x[key]=value
                with self.assertRaises(ValueError):self.check(latest=x)
    def test_cross_cohort_substituted_csv_sha_rejected(self):
        x=copy.deepcopy(self.latest)
        x["independently_reopened_original_csv_sha256"]["descriptor"]="d"*64
        with self.assertRaises(ValueError):self.check(latest=x)
    def test_wrong_archived_report_metadata_rejected(self):
        for key in ("stage365","stage369"):
            source=copy.deepcopy(getattr(self,"meta365" if key=="stage365" else "meta369"))
            source["digest"]="sha256:"+"0"*64
            with self.assertRaises(ValueError):
                self.check(**({"meta365" if key=="stage365" else "meta369":source}))
            source=copy.deepcopy(getattr(self,"meta365" if key=="stage365" else "meta369"))
            source["workflow_run"]["id"]+=1
            with self.assertRaises(ValueError):
                self.check(**({"meta365" if key=="stage365" else "meta369":source}))
    def test_bool_disguised_as_service_zero_rejected(self):
        for source,key in (("old","success_software_wait_raw_result"),
                           ("latest","service_result_raw"),
                           ("latest","service_returned_descriptor_count")):
            with self.subTest(source=source,key=key):
                x=copy.deepcopy(getattr(self,source));x[key]=False
                with self.assertRaises(ValueError):self.check(**{source:x})
    def test_tampered_original_guest_digest_proof_rejected(self):
        x=copy.deepcopy(self.old)
        x["timeout_stage313_348_351_357_sha256"]["stage357"]="missing"
        with self.assertRaises(ValueError):self.check(old=x)
        x=copy.deepcopy(self.latest)
        x["independently_reopened_original_csv_sha256"].pop("descriptor")
        with self.assertRaises(ValueError):self.check(latest=x)

if __name__=="__main__":
    unittest.main()
