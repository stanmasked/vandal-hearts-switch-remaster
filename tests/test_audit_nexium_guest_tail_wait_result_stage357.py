#!/usr/bin/env python3
"""Stage357 separate original guest raw Result source mutation controls."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_tail_wait_result_stage357 import (
    parse_source,audit_guest,VERIFIED,ExitTimelineError,SOURCE,
)
from audit_nexium_guest_exit_timeline import SUBDIR
from audit_nexium_guest_tail_reason_stage351 import (
    SCHEMA as OLD_SCHEMA,VERIFIED as OLD_VERDICT,
)
class Stage357Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.dir=self.root/SUBDIR
        self.dir.mkdir(parents=True)
        self.path=self.dir/SOURCE
    def old(self,code):
        return {
            "schema":OLD_SCHEMA,"result":OLD_VERDICT,
            "reason_code":code,
            "bound_to_original_stage313_tail_observation":True,
            "bound_to_original_stage348_lease_observation":True,
            "prior_stage313_and_stage348_original_bytes_reaudited":True,
            "physical_Nintendo_Switch_audio_tested":False,
            "original_guest_tail_reason_csv_sha256":"a"*64,
        }
    def csv(self,code,observed,raw):
        return (f"scope,value\nsoftware_wait_result_only,1\n"
                f"wait_result_observed,{observed}\n"
                f"audout_wait_result_raw,{raw}\n"
                f"stage351_tail_reason_code,{code}\n").encode("ascii")
    def test_actual_wait_failure_numeric_nonzero(self):
        raw=self.csv(4,1,0x2001)
        doc=parse_source(raw,self.old(4))
        self.assertEqual(doc["result"],VERIFIED)
        self.assertEqual(doc["audout_wait_result_raw"],0x2001)
        self.assertFalse(doc["physical_Nintendo_Switch_audio_tested"])
        self.assertFalse(doc["underlying_result_symbolic_meaning_proven"])
        self.assertEqual(doc["original_guest_wait_result_csv_sha256"],
                         hashlib.sha256(raw).hexdigest())
    def test_returned_wait_zero_code(self):
        self.assertEqual(parse_source(self.csv(7,1,0),self.old(7))["audout_wait_result_raw"],0)
    def test_early_skip_has_no_result(self):
        self.assertFalse(parse_source(self.csv(2,0,0),self.old(2))["wait_result_observed"])
    def test_reject_zero_error_result(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(4,1,0),self.old(4))
    def test_reject_nonzero_success_result(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(7,1,5),self.old(7))
    def test_reject_spurious_wait_before_append(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(3,1,5),self.old(3))
    def test_reject_missing_wait_observation(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(5,0,0),self.old(5))
    def test_reject_stage351_reason_disagreement(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(4,1,5),self.old(7))
    def test_reject_leading_zero(self):
        raw=self.csv(4,1,5).replace(b"audout_wait_result_raw,5\n",b"audout_wait_result_raw,05\n")
        with self.assertRaises(ExitTimelineError):parse_source(raw,self.old(4))
    def test_reject_overflow(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(4,1,2**32),self.old(4))
    def test_reject_extra_rows(self):
        with self.assertRaises(ExitTimelineError):
            parse_source(self.csv(4,1,5)+b"extra,1\n",self.old(4))
    def test_reject_ambiguous_guest_files(self):
        self.path.write_bytes(self.csv(4,1,5))
        self.assertEqual(audit_guest(self.root,self.old(4))[0]["audout_wait_result_raw"],5)
        (self.dir/"audio-exit-tail-wait-result-001.csv").write_bytes(self.csv(4,1,5))
        with self.assertRaises(ExitTimelineError):
            audit_guest(self.root,self.old(4))
    def test_cli_reject_forged_old_stage351_reason_against_original_stage313(self):
        from audit_nexium_guest_tail_wait_result_stage357 import main
        from audit_nexium_guest_tail_reason_stage351 import audit_source,KEYS
        from audit_nexium_guest_lease_reconciliation_stage348 import audit_source as audit_lease,KEYS as LEASE_KEYS
        import contextlib,io
        # Real-format synthetic old original sources and two old receipts.
        a=23;r=22
        st313={
            "schema":"vh-guest-last-audout-page-release-versus-exit/v1",
            "result":"GUEST_LAST_AUDOUT_RELEASE_SOFTWARE_TIMING_VALIDATED",
            "original_guest_page_witness_observed":True,
            "tail_bounded_attempt_observed":True,
            "tail_release_confirmed":False,
            "hardware_Nintendo_Switch_audio_tested":False,
        }
        lease_fields={
            "software_lease_only":1,"lease_pages_acquired":a,
            "lease_pages_released":r,"abandoned_sessions":1,
            "busy_begin_rejections":0,"mismatched_releases":0,
            "accepted_pages_submitted":r,"submit_failures":0,
        }
        lease_raw=b"scope,value\n"+b"".join(
            f"{k},{lease_fields[k]}\n".encode() for k in LEASE_KEYS)
        st348=audit_lease(lease_raw)
        fields={
            "software_exit_tail_reason_only":1,"tail_reason_code":4,
            "tail_attempted":1,"tail_descriptor_return_confirmed":0,
            "tail_lease_acquired":1,"lease_pages_acquired":a,
            "lease_pages_released":r,"abandoned_sessions":1,
        }
        prior=b"scope,value\n"+b"".join(
            f"{k},{fields[k]}\n".encode() for k in KEYS)
        st351=audit_source(prior,st313,st348)
        st351["prior_stage313_and_stage348_original_bytes_reaudited"]=True
        old=self.root/"stage351.csv";old.write_bytes(prior)
        q351=self.root/"stage351.json";q351.write_text(json.dumps(st351))
        q313=self.root/"stage313.json";q313.write_text(json.dumps(st313))
        q348=self.root/"stage348.json";q348.write_text(json.dumps(st348))
        locator=self.root/"root.txt";locator.write_text(str(self.root))
        self.path.write_bytes(self.csv(4,1,8193))
        argv=[
            "--guest-root-file",str(locator),"--stage351",str(q351),
            "--stage351-original",str(old),"--stage313",str(q313),
            "--stage348",str(q348),"--output",str(self.root/"out.json"),
            "--output-original",str(self.root/"out.csv"),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(argv),0)
        self.assertEqual(
            json.loads((self.root/"out.json").read_text())["audout_wait_result_raw"],8193)
        # Preserve the original source and receipt hash but falsify its
        # already-confirmed return flag. Stage357 must detect the forgery.
        (self.root/"out.json").unlink()
        (self.root/"out.csv").unlink()
        st351["tail_descriptor_return_confirmed"]=True
        q351.write_text(json.dumps(st351))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(argv),2)
        self.assertFalse((self.root/"out.csv").exists())

    def test_reject_symlinked_guest_source(self):
        self.path.symlink_to(self.root/"missing.csv")
        with self.assertRaises(ExitTimelineError):
            audit_guest(self.root,self.old(4))
if __name__=="__main__":
    unittest.main()
