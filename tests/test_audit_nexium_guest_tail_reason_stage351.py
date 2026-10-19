#!/usr/bin/env python3
"""Stage351 synthetic source mutation tests; not original NeXium evidence."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_tail_reason_stage351 import (
    KEYS, REASONS, VERIFIED, audit_source, audit_guest,
    audit_existing_original_sources, main,
)
from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError


class Stage351Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.directory=self.root/SUBDIR
        self.directory.mkdir(parents=True)

    def fixture(self,code=4,acquired=22,released=21,abandoned=1):
        fields={
            "software_exit_tail_reason_only":1,
            "tail_reason_code":code,
            "tail_attempted":int(code!=0),
            "tail_descriptor_return_confirmed":int(code==7),
            "tail_lease_acquired":int(3<=code<=7),
            "lease_pages_acquired":acquired,
            "lease_pages_released":released,
            "abandoned_sessions":abandoned,
        }
        raw=b"scope,value\n"+b"".join(
            f"{key},{fields[key]}\n".encode("ascii") for key in KEYS
        )
        stage313={
            "schema":"vh-guest-last-audout-page-release-versus-exit/v1",
            "result":"GUEST_LAST_AUDOUT_RELEASE_SOFTWARE_TIMING_VALIDATED",
            "original_guest_page_witness_observed":True,
            "tail_bounded_attempt_observed":bool(fields["tail_attempted"]),
            "tail_release_confirmed":bool(fields["tail_descriptor_return_confirmed"]),
            "hardware_Nintendo_Switch_audio_tested":False,
        }
        stage348={
            "schema":"vh-stage348-original-software-lease-reconciliation/v1",
            "result":"ORIGINAL_GUEST_SOFTWARE_PCM_LEASE_BALANCE_SOURCE_VERIFIED",
            "original_guest_software_lease_source_observed":True,
            "physical_Nintendo_Switch_audio_tested":False,
            "lease_pages_acquired":acquired,
            "lease_pages_released":released,
            "abandoned_sessions":abandoned,
            "accepted_pages_submitted":released,
        }
        return raw,stage313,stage348


    def original_sources(self, report313, report348):
        """Build separately hashed canonical originals for paired receipt checks."""
        tail={
            "page_return_count":20,
            "last_page_return_guest_ns":100,
            "last_page_frames":256,
            "tail_attempt_guest_ns":200 if report313["tail_bounded_attempt_observed"] else 0,
            "tail_success_return_guest_ns":210 if report313["tail_release_confirmed"] else 0,
        }
        source313=b"event,value\n"+b"".join(
            f"{name},{value}\n".encode("ascii") for name,value in tail.items()
        )
        report313["original_guest_page_witness_sha256"]=hashlib.sha256(source313).hexdigest()
        for k,v in tail.items():
            report313[k]=v if v or not k.endswith("_guest_ns") else None
        original_lease={
            "software_lease_only":1,
            "lease_pages_acquired":report348["lease_pages_acquired"],
            "lease_pages_released":report348["lease_pages_released"],
            "abandoned_sessions":report348["abandoned_sessions"],
            "busy_begin_rejections":0,
            "mismatched_releases":0,
            "accepted_pages_submitted":report348["accepted_pages_submitted"],
            "submit_failures":0,
        }
        source348=b"scope,value\n"+b"".join(
            f"{k},{v}\n".encode("ascii") for k,v in original_lease.items()
        )
        report348.update({
            "original_guest_software_lease_csv_sha256":
                hashlib.sha256(source348).hexdigest(),
            "busy_begin_rejections":0,
            "mismatched_releases":0,
            "submit_failures":0,
            "only_software_owner_counters_checked":True,
        })
        return source313,source348

    def test_prior_original_sources_reaudited(self):
        _,a,b=self.fixture()
        first,second=self.original_sources(a,b)
        report=audit_existing_original_sources(first,second,a,b)
        self.assertTrue(report["prior_stage313_and_stage348_original_bytes_reaudited"])

    def test_reject_forged_original_stage313_source(self):
        _,a,b=self.fixture()
        first,second=self.original_sources(a,b)
        with self.assertRaises(ExitTimelineError):
            audit_existing_original_sources(first+b"EXTRA,1\n",second,a,b)

    def test_reject_forged_original_stage348_source(self):
        _,a,b=self.fixture()
        first,second=self.original_sources(a,b)
        other=second.replace(b"lease_pages_acquired,22\n",b"lease_pages_acquired,23\n")
        with self.assertRaises(ExitTimelineError):
            audit_existing_original_sources(first,other,a,b)

    def test_reject_mismatched_original_stage313_receipt(self):
        _,a,b=self.fixture()
        first,second=self.original_sources(a,b)
        a["tail_attempt_guest_ns"]=201
        with self.assertRaises(ExitTimelineError):
            audit_existing_original_sources(first,second,a,b)

    def test_reject_mismatched_original_stage348_receipt(self):
        _,a,b=self.fixture()
        first,second=self.original_sources(a,b)
        b["busy_begin_rejections"]=1
        with self.assertRaises(ExitTimelineError):
            audit_existing_original_sources(first,second,a,b)

    def test_each_code_is_source_consistent(self):
        for code in range(len(REASONS)):
            abandoned=int(3<=code<=6)
            raw,a,b=self.fixture(code,22,22-abandoned,abandoned)
            doc=audit_source(raw,a,b)
            self.assertEqual(doc["reason_name"],REASONS[code])
            self.assertFalse(doc["DAC_or_speaker_audio_verified"])

    def test_reject_wrong_stage313_tail_return(self):
        raw,a,b=self.fixture()
        a["tail_release_confirmed"]=True
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_wrong_stage313_tail_attempt(self):
        raw,a,b=self.fixture()
        a["tail_bounded_attempt_observed"]=False
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_forged_stage348_abandoned(self):
        raw,a,b=self.fixture()
        b["abandoned_sessions"]=0
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_forged_stage348_acquired(self):
        raw,a,b=self.fixture()
        b["lease_pages_acquired"]=77
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_wrong_reason_confirmed(self):
        raw,a,b=self.fixture()
        raw=raw.replace(b"tail_descriptor_return_confirmed,0\n",
                        b"tail_descriptor_return_confirmed,1\n")
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_tail_failure_without_abandoned(self):
        raw,a,b=self.fixture(code=4,acquired=22,released=22,abandoned=0)
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_wrong_lease_balance(self):
        raw,a,b=self.fixture()
        raw=raw.replace(b"lease_pages_released,21\n",b"lease_pages_released,20\n")
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_unknown_reason(self):
        raw,a,b=self.fixture()
        raw=raw.replace(b"tail_reason_code,4\n",b"tail_reason_code,8\n")
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_leading_zeros(self):
        raw,a,b=self.fixture()
        raw=raw.replace(b"tail_reason_code,4\n",b"tail_reason_code,04\n")
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_reordered_rows(self):
        raw,a,b=self.fixture()
        raw=raw.replace(b"tail_lease_acquired,1\n",b"tail_LEASE_acquired,1\n")
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_reject_extra_rows(self):
        raw,a,b=self.fixture()
        with self.assertRaises(ExitTimelineError):
            audit_source(raw+b"extra,1\n",a,b)

    def test_reject_saturation(self):
        raw,a,b=self.fixture()
        raw=raw.replace(b"lease_pages_acquired,22\n",
                        f"lease_pages_acquired,{2**64-1}\n".encode())
        with self.assertRaises(ExitTimelineError):
            audit_source(raw,a,b)

    def test_guest_source_exclusive_and_link_guard(self):
        raw,a,b=self.fixture()
        p=self.directory/"audio-exit-tail-reason-000.csv"
        p.write_bytes(raw)
        doc,saved=audit_guest(self.root,a,b)
        self.assertEqual(saved,raw)
        self.assertEqual(doc["result"],VERIFIED)
        self.assertEqual(doc["original_guest_tail_reason_csv_sha256"],
                         hashlib.sha256(raw).hexdigest())
        (self.directory/"audio-exit-tail-reason-001.csv").write_bytes(raw)
        with self.assertRaises(ExitTimelineError):
            audit_guest(self.root,a,b)

    def test_guest_directory_symlink_rejected(self):
        raw,a,b=self.fixture()
        p=self.directory/"audio-exit-tail-reason-000.csv"
        p.write_bytes(raw)
        link=self.root/"link"
        link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ExitTimelineError):
            audit_guest(link,a,b)

    def test_cli_preserves_original_bytes_no_overwrite(self):
        raw,a,b=self.fixture()
        (self.directory/"audio-exit-tail-reason-000.csv").write_bytes(raw)
        locator=self.root/"guest-sd-root.txt"
        locator.write_text(str(self.root))
        first,second=self.original_sources(a,b)
        old313=self.root/"audio-exit-output-000.csv"
        old313.write_bytes(first)
        old348=self.root/"audio-lease-reconciliation-000.csv"
        old348.write_bytes(second)
        r313=self.root/"stage313.json";r313.write_text(json.dumps(a))
        r348=self.root/"stage348.json";r348.write_text(json.dumps(b))
        output=self.root/"stage351.json"
        original=self.root/"saved-stage351.csv"
        argv=["--guest-root-file",str(locator),"--stage313",str(r313),
              "--stage348",str(r348),"--stage313-original",str(old313),
              "--stage348-original",str(old348),"--output",str(output),
              "--output-original",str(original)]
        self.assertEqual(main(argv),0)
        self.assertEqual(original.read_bytes(),raw)
        report=json.loads(output.read_text())
        self.assertTrue(report["prior_stage313_and_stage348_original_bytes_reaudited"])
        self.assertEqual(main(argv),2)


if __name__=="__main__":
    unittest.main()
