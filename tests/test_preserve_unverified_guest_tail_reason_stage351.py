#!/usr/bin/env python3
"""Negative controls for failure-only unverified guest CSV quarantine."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from preserve_unverified_guest_tail_reason_stage351 import capture, main, RESULT
from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError

class Stage351QuarantineTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        self.dir=self.root/SUBDIR
        self.dir.mkdir(parents=True)
        self.source=self.dir/"audio-exit-tail-reason-000.csv"
        self.locator=self.root/"guest-root.txt"
        self.locator.write_text(str(self.root),encoding="utf-8")
        self.out=self.root/"quarantine.csv"
        self.receipt=self.root/"quarantine.json"
        self.original=(b"scope,value\nsoftware_exit_tail_reason_only,1\n"
                       b"tail_reason_code,4\n")
        self.source.write_bytes(self.original)

    def test_exact_preservation_never_certifies_failure_reason(self):
        doc=capture(self.locator,self.out,self.receipt,39311305607)
        self.assertEqual(doc["result"],RESULT)
        self.assertEqual(self.out.read_bytes(),self.original)
        self.assertEqual(doc["quarantined_guest_csv_sha256"],
                         hashlib.sha256(self.original).hexdigest())
        self.assertFalse(doc["stage351_reason_code_validated"])
        self.assertFalse(doc["guest_source_authenticated_against_stage313_and_348"])
        self.assertFalse(doc["one_to_one_failure_cause_proven"])
        self.assertFalse(doc["physical_Nintendo_Switch_audio_tested"])
        self.assertEqual(json.loads(self.receipt.read_text()),doc)

    def test_refuse_second_copy_to_existing_output(self):
        capture(self.locator,self.out,self.receipt,1)
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_ambiguous_guest_originals(self):
        (self.dir/"audio-exit-tail-reason-001.csv").write_bytes(self.original)
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_symlinked_original_source(self):
        self.source.unlink()
        self.source.symlink_to(self.locator)
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_symlinked_guest_directory_ancestor(self):
        link=self.root/"alias"
        link.symlink_to(self.root,target_is_directory=True)
        self.locator.write_text(str(link))
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_symlinked_output_parent(self):
        alias=self.root/"out-alias"
        alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,alias/"new.csv",self.receipt,1)

    def test_accept_malformed_numeric_values_without_validating_them(self):
        raw=b"scope,value\ntail_reason_code,not_an_integer\n"
        self.source.write_bytes(raw)
        doc=capture(self.locator,self.out,self.receipt,1)
        self.assertEqual(self.out.read_bytes(),raw)
        self.assertFalse(doc["stage351_reason_code_validated"])

    def test_reject_untrusted_binary(self):
        self.source.write_bytes(b"scope,value\nbinary,\x00\n")
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_nonprintable_control_escape(self):
        self.source.write_bytes(b"scope,value\nbad,\x1b\n")
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_too_large_guest_dump(self):
        self.source.write_bytes(b"scope,value\n"+b"0"*510+b"\n")
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,1)

    def test_reject_invalid_run_id(self):
        with self.assertRaises(ExitTimelineError):
            capture(self.locator,self.out,self.receipt,0)

    def test_missing_file_reports_failure_not_invented_success(self):
        self.source.unlink()
        args=["--guest-root-file",str(self.locator),
              "--output-original",str(self.out),
              "--output-report",str(self.receipt),"--run-id","1"]
        self.assertEqual(main(args),2)
        self.assertFalse(self.out.exists())

if __name__=="__main__":
    unittest.main()
