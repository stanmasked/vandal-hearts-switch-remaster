#!/usr/bin/env python3
"""Stage369 adversarial original-archive audit tests; synthetic fixtures only."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_stage369_original_nexium_archive as a
from test_audit_nexium_stage368_wait_descriptor import make_sources


def fixture(root:Path):
    artifact=root/"artifact"
    d=artifact/"runtime-evidence"
    make_sources(d)
    gh_sha="1"*40
    nro_sha="2"*64
    attempt=1
    digest={key:hashlib.sha256((d/name).read_bytes()).hexdigest()
            for key,name in a.FILES.items()}
    (artifact/"integrated-nro-preflight.json").write_text(json.dumps({
      "result":"SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
      "git_sha":gh_sha,"run_id":a.RUN_ID,"run_attempt":attempt,
      "nro_bytes":147000,"nro_sha256":nro_sha,
    }))
    report351={
      "result":"ORIGINAL_GUEST_EXIT_TAIL_CAUSE_SOURCE_VERIFIED",
      "prior_stage313_and_stage348_original_bytes_reaudited":True,
      "original_guest_tail_reason_csv_sha256":digest["reason"],
      "physical_Nintendo_Switch_audio_tested":False,
      "reason_code":7,
    }
    report357={
      "result":"ORIGINAL_NEIXUM_GUEST_EXIT_TAIL_WAIT_RESULT_SOURCE_VERIFIED",
      "original_guest_wait_result_csv_sha256":digest["result"],
      "original_stage351_source_sha256":digest["reason"],
      "physical_Nintendo_Switch_audio_tested":False,
      "stage351_reason_code":7,"audout_wait_result_raw":0,
    }
    report368={
      "result":a.EXPECTED_368,
      "stage368_guest_original_source_bound_to_verified_prior_originals":True,
      "original_neXium_archive_proven":True,
      "source_sha256":digest,
      "neXium_original_guest_run_id":a.RUN_ID,
      "neXium_nro_git_sha":gh_sha,
      "neXium_nro_sha256":nro_sha,
      "neXium_nro_run_attempt":attempt,
      "raw_wait_result":0,
      "reported_released_count":1,
      "returned_pointer_present":True,
      "returned_pointer_matches_submitted":True,
      "old_0xEA01_cause_proven":False,
      "physical_Nintendo_Switch_audio_tested":False,
      "kernel_wait_subcall_uniquely_proven":False,
      "actual_queue_depth_measured":False,
    }
    for k,doc in (("reason",report351),("result",report357),("descriptor",report368)):
        (d/a.REPORTS[k]).write_text(json.dumps(doc))
    run={
      "id":a.RUN_ID,"status":"completed","conclusion":"success",
      "run_attempt":attempt,"head_sha":gh_sha,
      "repository":{"full_name":"stanmasked/vandal-hearts-switch-remaster"},
    }
    jobs={"jobs":[
      {"name":"Build libnx NRO for runtime smoke test",
       "conclusion":"success","run_id":a.RUN_ID},
      {"name":"Launch current-workflow audout NRO in NeXium",
       "run_id":a.RUN_ID,"status":"completed","conclusion":"success",
       "steps":[{"name":s,"conclusion":"success"} for s in a.STEPS]},
    ]}
    meta={
      "id":12249600000,"name":a.EVIDENCE_NAME,
      "size_in_bytes":130000,"expired":False,
      "digest":"sha256:"+"a"*64,
      "workflow_run":{"id":a.RUN_ID,"head_sha":gh_sha},
    }
    return artifact,run,jobs,meta


class Stage369OriginalArtifactAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.archive,self.run,self.jobs,self.meta=fixture(self.root)
    def evaluate(self,**updates):
        inputs={"archive":self.archive,"run":self.run,"jobs":self.jobs,
                "artifact":self.meta}
        inputs.update(updates)
        return a.verify(**inputs)
    def test_valid_synthetic_does_not_infer_dac_or_cause(self):
        result=self.evaluate()
        self.assertEqual(result["result"],a.VERIFIED)
        self.assertEqual(result["source_run_id"],a.RUN_ID)
        self.assertTrue(result["original_stage368_step_succeeded"])
        self.assertEqual(result["service_returned_descriptor_count"],1)
        self.assertTrue(result["returned_pointer_matches_submitted"])
        self.assertFalse(result["physical_Switch_sound_tested"])
        self.assertFalse(result["old_0xEA01_cause_proven"])
    def test_wrong_run_status_commit_attempt_rejected(self):
        for key,bad in (("id",a.RUN_ID+1),("status","in_progress"),
                        ("head_sha","b"*40),("run_attempt",2)):
            with self.subTest(key=key):
                run=copy.deepcopy(self.run);run[key]=bad
                with self.assertRaises(ValueError):
                    self.evaluate(run=run)
    def test_original_job_not_attested_or_duplicate_rejected(self):
        jobs=copy.deepcopy(self.jobs)
        jobs["jobs"][1]["steps"][2]["conclusion"]="failure"
        with self.assertRaises(ValueError):
            self.evaluate(jobs=jobs)
        jobs=copy.deepcopy(self.jobs)
        jobs["jobs"].append(copy.deepcopy(jobs["jobs"][1]))
        with self.assertRaises(ValueError):
            self.evaluate(jobs=jobs)
        jobs=copy.deepcopy(self.jobs)
        jobs["jobs"][0]["conclusion"]="failure"
        with self.assertRaises(ValueError):
            self.evaluate(jobs=jobs)
    def test_wrong_artifact_identity_digest_or_source_rejected(self):
        for field,value in (("name","other"),("digest","no-digest"),
                            ("expired",True),("size_in_bytes",0)):
            with self.subTest(field=field):
                m=copy.deepcopy(self.meta);m[field]=value
                with self.assertRaises(ValueError):
                    self.evaluate(artifact=m)
        m=copy.deepcopy(self.meta)
        m["workflow_run"]["head_sha"]="b"*40
        with self.assertRaises(ValueError):
            self.evaluate(artifact=m)
    def test_original_bytes_and_pinned_hashes_rejected(self):
        d=self.archive/"runtime-evidence"
        file=d/a.FILES["descriptor"]
        old=file.read_bytes()
        file.write_bytes(old.replace(
            b"released_count_reported,1",b"released_count_reported,2"))
        with self.assertRaises(ValueError):
            self.evaluate()
        file.write_bytes(old)
        report=d/a.REPORTS["descriptor"]
        old=report.read_text()
        report.write_text(old.replace('"source_sha256"', '"forged_sha256"'))
        with self.assertRaises(ValueError):
            self.evaluate()
        report.write_text(old)
    def test_mismatched_raw_service_result_and_false_kernel_cause_rejected(self):
        path=self.archive/"runtime-evidence"/a.REPORTS["descriptor"]
        old=path.read_text()
        for key,oldval,newval in (
            ("raw_wait_result","\"raw_wait_result\": 0","\"raw_wait_result\": 59905"),
            ("old_0xEA01_cause_proven","\"old_0xEA01_cause_proven\": false","\"old_0xEA01_cause_proven\": true"),
            ("physical_Nintendo_Switch_audio_tested","\"physical_Nintendo_Switch_audio_tested\": false","\"physical_Nintendo_Switch_audio_tested\": true"),
        ):
            with self.subTest(key=key):
                self.assertIn(oldval,old)
                path.write_text(old.replace(oldval,newval))
                with self.assertRaises(ValueError):
                    self.evaluate()
        path.write_text(old)
    def test_no_evidence_file_and_link_rejected(self):
        p=self.archive/"runtime-evidence"/a.FILES["reason"]
        data=p.read_bytes();p.unlink()
        with self.assertRaises(ValueError):
            self.evaluate()
        p.symlink_to(self.archive/"runtime-evidence"/a.FILES["descriptor"])
        with self.assertRaises(ValueError):
            self.evaluate()
        p.unlink();p.write_bytes(data)
    def test_original_timeout_fixture_does_not_prove_old_cause(self):
        d=self.archive/"runtime-evidence"
        make_sources(d,code=4,raw=0xEA01,count=0,present=0,same=0)
        hashes={k:hashlib.sha256((d/name).read_bytes()).hexdigest()
                for k,name in a.FILES.items()}
        for k in ("reason","result","descriptor"):
            p=d/a.REPORTS[k];x=json.loads(p.read_text())
            if k=="reason":
                x["original_guest_tail_reason_csv_sha256"]=hashes["reason"]
                x["reason_code"]=4
            elif k=="result":
                x["original_guest_wait_result_csv_sha256"]=hashes["result"]
                x["original_stage351_source_sha256"]=hashes["reason"]
                x["stage351_reason_code"]=4
                x["audout_wait_result_raw"]=0xEA01
            else:
                x["source_sha256"]=hashes
                x["raw_wait_result"]=0xEA01
                x["reported_released_count"]=0
                x["returned_pointer_present"]=False
                x["returned_pointer_matches_submitted"]=False
            p.write_text(json.dumps(x))
        result=self.evaluate()
        self.assertEqual(result["service_result_raw"],0xEA01)
        self.assertFalse(result["old_0xEA01_cause_proven"])
        self.assertFalse(result["exit_queue_depth_measured"])


if __name__=="__main__":
    unittest.main()
