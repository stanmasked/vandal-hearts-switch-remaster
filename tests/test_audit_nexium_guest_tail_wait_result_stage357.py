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
    def test_reject_symlinked_guest_source(self):
        self.path.symlink_to(self.root/"missing.csv")
        with self.assertRaises(ExitTimelineError):
            audit_guest(self.root,self.old(4))
if __name__=="__main__":
    unittest.main()
