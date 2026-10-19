"""Stage348 negative/positive tests of strict original guest software lease source."""
from __future__ import annotations
import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_nexium_guest_exit_timeline import SUBDIR,ExitTimelineError
from audit_nexium_guest_lease_reconciliation_stage348 import (
    audit_source,audit_guest,main,VERIFIED
)

def csv(**update)->bytes:
    original=[
        ("software_lease_only",1),("lease_pages_acquired",513),
        ("lease_pages_released",512),("abandoned_sessions",1),
        ("busy_begin_rejections",170),("mismatched_releases",171),
        ("accepted_pages_submitted",510),("submit_failures",5),
    ]
    return ("scope,value\n"+"".join(
        f"{k},{update.get(k,v)}\n" for k,v in original)).encode("ascii")

class Stage348OriginalGuestSoftwareLeaseTests(unittest.TestCase):
    def test_exact_original_guest_lease_source(self):
        raw=csv()
        r=audit_source(raw)
        self.assertEqual(r["result"],VERIFIED)
        self.assertEqual(r["lease_pages_acquired"],513)
        self.assertEqual(r["lease_pages_released"],512)
        self.assertEqual(r["original_guest_software_lease_csv_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])
    def test_valid_no_abandonment(self):
        self.assertEqual(audit_source(csv(lease_pages_acquired=512,abandoned_sessions=0))["abandoned_sessions"],0)
    def test_missing_header_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv().replace(b"scope,value",b"name,value"))
    def test_crlf_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv().replace(b"\n",b"\r\n"))
    def test_noncanonical_integer_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv(lease_pages_acquired="0513"))
    def test_swapped_rows_rejected(self):
        raw=csv().replace(b"lease_pages_acquired,513",b"lease_pages_released,513",1)
        with self.assertRaises(ExitTimelineError):audit_source(raw)
    def test_duplicate_or_extra_rows_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv()+b"arbitrary,1\n")
    def test_truncated_source_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv()[:-1])
    def test_software_only_flag_cannot_claim_hardware(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv(software_lease_only=0))
    def test_busy_lease_without_session_close_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv(abandoned_sessions=0))
    def test_invented_abandonments_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv(abandoned_sessions=2))
    def test_release_count_above_acquired_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv(lease_pages_released=514))
    def test_unreleased_accepted_pcm_pages_rejected(self):
        with self.assertRaises(ExitTimelineError):audit_source(csv(accepted_pages_submitted=513))
    def test_counter_saturation_rejected(self):
        with self.assertRaises(ExitTimelineError):
            audit_source(csv(lease_pages_acquired=2**64-1))
        with self.assertRaises(ExitTimelineError):
            audit_source(csv(abandoned_sessions=2**32-1))
    def test_original_guest_path_and_source_bytes_preserved(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/SUBDIR).mkdir(parents=True)
            target=root/SUBDIR/"audio-lease-reconciliation-000.csv"
            target.write_bytes(csv())
            receipt,raw=audit_guest(root)
            self.assertEqual(raw,csv())
            self.assertEqual(receipt["result"],VERIFIED)
            self.assertEqual(receipt["original_guest_source_relative_path"],str(SUBDIR/"audio-lease-reconciliation-000.csv"))
            locator=root/"guest-sd-root.txt"
            locator.write_text(str(root)+"\n",encoding="utf-8")
            report=root/"test-report.json"
            original=root/"original-source.csv"
            self.assertEqual(main(["--guest-root-file",str(locator),
                     "--output",str(report),"--output-original",str(original)]),0)
            self.assertEqual(json.loads(report.read_text())["result"],VERIFIED)
            self.assertEqual(original.read_bytes(),csv())
            self.assertEqual(main(["--guest-root-file",str(locator),
                     "--output",str(report),"--output-original",str(original)]),2)
    def test_missing_ambiguous_or_symlinked_guest_source_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            directory=root/SUBDIR
            directory.mkdir(parents=True)
            with self.assertRaises(ExitTimelineError):audit_guest(root)
            target=directory/"audio-lease-reconciliation-000.csv"
            target.write_bytes(csv())
            second=directory/"audio-lease-reconciliation-001.csv"
            second.write_bytes(csv())
            with self.assertRaises(ExitTimelineError):audit_guest(root)
            second.unlink()
            target.unlink()
            target.symlink_to(root/"other.csv")
            with self.assertRaises(ExitTimelineError):audit_guest(root)
if __name__=="__main__": unittest.main()
