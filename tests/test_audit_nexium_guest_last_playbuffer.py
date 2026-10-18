"""Stage320 original guest last successful PlayBuffer bracket test corpus."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_exit_timeline import (
    SUBDIR, ExitTimelineError, parse_exit_csv,
)
from audit_nexium_guest_last_buffer_return import audit_source as parse_page
from audit_nexium_guest_worker_stop_observed import audit_worker_stop_csv
from audit_nexium_guest_last_playbuffer import (
    VERIFIED, audit_original, audit_guest_root,
)

def originals():
    exit_raw=("event,guest_monotonic_ns\n"
         "plus_observed,100000\nstop_requested,100700\n"
         "worker_cleanup_entered,115700\naudout_closed,126700\n"
         "worker_joined,130700\n").encode()
    page_raw=("event,value\n"
         "page_return_count,380\nlast_page_return_guest_ns,113000\n"
         "last_page_frames,128\n"
         "tail_attempt_guest_ns,118000\n"
         "tail_success_return_guest_ns,118100\n").encode()
    worker_raw=b"event,guest_monotonic_ns\nworker_stop_observed,114000\n"
    exit_doc=parse_exit_csv(exit_raw)
    page_doc=parse_page(page_raw,exit_doc)
    worker_doc=audit_worker_stop_csv(worker_raw,exit_doc,page_doc)
    return exit_raw,page_raw,worker_raw,exit_doc,page_doc,worker_doc

def csv(begin=100000,end=112900,attempts=380,success=380,
        failed=0,index=380,rejected=0):
    return (f"event,value\nattempts,{attempts}\n"
       f"successes,{success}\nfailures,{failed}\n"
       f"last_success_attempt,{index}\n"
       f"last_success_begin_guest_ns,{begin}\n"
       f"last_success_end_guest_ns,{end}\n"
       f"nonmonotonic_rejected,{rejected}\n").encode()

class LastPlayBufferSoftwareCall(unittest.TestCase):
    def setUp(self):
        self.exit_raw,self.page_raw,self.worker_raw,self.exit,self.page,self.worker=originals()

    def audit(self,source=None,exit_doc=None,page_doc=None,worker_doc=None):
        return audit_original(csv() if source is None else source,
                self.exit if exit_doc is None else exit_doc,
                self.page if page_doc is None else page_doc,
                self.worker if worker_doc is None else worker_doc)

    def test_true_service_call_spans_stop_request(self):
        r=self.audit()
        self.assertEqual(r["result"],VERIFIED)
        self.assertEqual(r["last_successful_PlayBuffer_software_duration_ns"],12900)
        self.assertEqual(r["portion_of_last_call_after_stop_request_ns"],12200)
        self.assertEqual(r["last_successful_PlayBuffer_return_to_page_witness_ns"],100)
        self.assertEqual(r["last_page_witness_to_worker_stop_observed_ns"],1000)
        self.assertEqual(r["last_successful_call_relative_to_stop_request"],
                         "last_successful_PlayBuffer_spanned_stop_request")
        self.assertFalse(r["audible_dropout_verified"])

    def test_service_call_started_after_stop_is_distinct(self):
        r=self.audit(csv(begin=101000,end=112000))
        self.assertEqual(r["last_successful_call_relative_to_stop_request"],
                         "last_successful_PlayBuffer_started_after_stop_request")
        self.assertEqual(r["portion_of_last_call_after_stop_request_ns"],11000)

    def test_service_call_finished_before_stop_cannot_explain_delayed_page(self):
        r=self.audit(csv(begin=99000,end=100600))
        self.assertEqual(r["last_successful_call_relative_to_stop_request"],
                         "last_successful_PlayBuffer_returned_before_stop_request")
        self.assertEqual(r["portion_of_last_call_after_stop_request_ns"],0)

    def test_earlier_failed_attempt_doesnt_replace_final_success(self):
        r=self.audit(csv(attempts=390,success=380,failed=10,index=389))
        self.assertEqual(r["successful_PlayBuffer_call_count"],380)
        self.assertEqual(r["last_successful_PlayBuffer_attempt_index"],389)

    def test_source_missing_or_noncanonical_rejected(self):
        raw=csv()
        corrupts=(b"",raw[:-1],raw.replace(b"\n",b"\r\n"),
                  raw.replace(b"successes",b"SUCCESSes"),
                  raw.replace(b"attempts,380",b"attempts,0380"),
                  raw+b"attempts,381\n",
                  raw.replace(b"attempts,380",b"attempts,-380"),
                  raw.replace(b"attempts,380",b"attempts,18446744073709551616"),
                  raw+b"\x00")
        for data in corrupts:
            with self.subTest(data=data[:45]),self.assertRaises(ExitTimelineError):
                self.audit(data)

    def test_attempt_count_and_last_success_guard(self):
        variants=(csv(attempts=0,success=0,index=0),
                  csv(attempts=380,success=381),
                  csv(attempts=380,success=370,failed=9),
                  csv(attempts=380,index=381),
                  csv(rejected=1))
        for data in variants:
            with self.subTest(data=data[:80]),self.assertRaises(ExitTimelineError):
                self.audit(data)

    def test_inverted_call_and_page_order_fail_closed(self):
        for vals in ((112000,111900),(112000,113001),
                     (114000,114050),(100000,115701)):
            with self.subTest(vals=vals),self.assertRaises(ExitTimelineError):
                self.audit(csv(begin=vals[0],end=vals[1]))

    def test_forged_guest_page_sha_rejected(self):
        doc=dict(self.worker)
        doc["source_last_page_csv_sha256"]="f"*64
        with self.assertRaises(ExitTimelineError):
            self.audit(worker_doc=doc)

    def test_forged_guest_exit_sha_rejected(self):
        doc=dict(self.page)
        doc["original_guest_exit_csv_sha256"]="f"*64
        with self.assertRaises(ExitTimelineError):
            self.audit(page_doc=doc)

    def test_guest_sd_original_saved_and_sha_verified(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/SUBDIR
            directory.mkdir(parents=True)
            (directory/"audio-exit-timeline-000.csv").write_bytes(self.exit_raw)
            (directory/"audio-exit-output-000.csv").write_bytes(self.page_raw)
            (directory/"audio-exit-worker-stop-000.csv").write_bytes(self.worker_raw)
            original=csv()
            (directory/"audio-last-playbuffer-000.csv").write_bytes(original)
            r,raw=audit_guest_root(Path(root))
            self.assertEqual(r["result"],VERIFIED)
            self.assertEqual(raw,original)
            self.assertEqual(r["original_last_playbuffer_csv_sha256"],
                             hashlib.sha256(original).hexdigest())

    def test_ambiguous_source_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/SUBDIR
            directory.mkdir(parents=True)
            (directory/"audio-exit-timeline-000.csv").write_bytes(self.exit_raw)
            (directory/"audio-exit-output-000.csv").write_bytes(self.page_raw)
            (directory/"audio-exit-worker-stop-000.csv").write_bytes(self.worker_raw)
            p=directory/"audio-last-playbuffer-000.csv"
            p.write_bytes(csv())
            (directory/"audio-last-playbuffer-001.csv").write_bytes(csv())
            with self.assertRaises(ExitTimelineError):
                audit_guest_root(Path(root))
            (directory/"audio-last-playbuffer-001.csv").unlink()
            elsewhere=Path(root)/"other.csv"
            elsewhere.write_bytes(csv())
            p.unlink()
            p.symlink_to(elsewhere)
            with self.assertRaises(ExitTimelineError):
                audit_guest_root(Path(root))

    def test_absent_source_explicitly_unobserved(self):
        with tempfile.TemporaryDirectory() as root:
            result,data=audit_guest_root(Path(root))
            self.assertEqual(result["result"],
                             "ORIGINAL_LAST_PLAYBUFFER_GUEST_SD_NOT_OBSERVED")
            self.assertIsNone(data)

    def test_deterministic_without_DAC_claim(self):
        a=self.audit()
        self.assertEqual(a,self.audit())
        self.assertTrue(a["audout_PlayBuffer_return_not_audible_speaker_or_DAC"])
        self.assertTrue(a["guest_clock_not_synchronized_to_host_PCM"])
        self.assertTrue(a["one_call_does_not_explain_entire_stop_delay_automatically"])

if __name__=="__main__":
    unittest.main()
