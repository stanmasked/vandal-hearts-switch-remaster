#!/usr/bin/env python3
"""Stage351 synthetic source mutation tests; not original NeXium evidence."""
import hashlib
import json
import contextlib
import io
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

    def test_real_nexium_original_source_dependency_order(self):
        """Stage351 must consume Stage313/348 only after Stage314 copied CSV."""
        workflow=(Path(__file__).resolve().parents[1]/
                  ".github"/"workflows"/"emulator-smoke.yml").read_text(
                      encoding="utf-8")
        labels=(
            "Stage313 verify guest last audout PCM page return",
            "Stage348 independently verify actual Stage347 post-join guest",
            "Stage314 preserve original guest-created last audout page",
            "Stage351 verify original post-join tail failure cause",
            "Capture ten additional A/B transitions in isolated NeXium",
        )
        positions=[]
        for label in labels:
            self.assertEqual(workflow.count("- name: "+label),1,label)
            positions.append(workflow.index("- name: "+label))
        self.assertEqual(positions,sorted(positions))
        stage314=workflow[positions[2]:positions[3]]
        self.assertIn(
            "--output-original runtime-evidence/audio-exit-output-000.csv",
            stage314)
        stage351=workflow[positions[3]:positions[4]]
        self.assertIn(
            "--stage313-original runtime-evidence/audio-exit-output-000.csv",
            stage351)
        self.assertIn(
            "--stage348-original runtime-evidence/audio-lease-reconciliation-000.csv",
            stage351)
        self.assertIn(
            "prior_stage313_and_stage348_original_bytes_reaudited",stage351)

    def test_cli_missing_source_reports_input_phase_without_guest_claim(self):
        raw,a,b=self.fixture()
        (self.directory/"audio-exit-tail-reason-000.csv").write_bytes(raw)
        locator=self.root/"source-root.txt"
        locator.write_text(str(self.root),encoding="utf-8")
        stage313=self.root/"313.json";stage313.write_text(json.dumps(a))
        stage348=self.root/"348.json";stage348.write_text(json.dumps(b))
        argv=["--guest-root-file",str(locator),
              "--stage313",str(stage313),"--stage348",str(stage348),
              "--stage313-original",str(self.root/"missing313.csv"),
              "--stage348-original",str(self.root/"missing348.csv"),
              "--output",str(self.root/"out.json"),
              "--output-original",str(self.root/"out.csv")]
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            status=main(argv)
        self.assertEqual(status,2)
        diagnostic=json.loads(buf.getvalue())
        self.assertEqual(diagnostic["failed_phase"],"required-input-files")
        self.assertFalse(diagnostic["stage351_reason_code_validated"])
        self.assertFalse((self.root/"out.json").exists())

    def test_cli_mismatched_guest_reason_reports_distinct_phase(self):
        raw,a,b=self.fixture()
        first,second=self.original_sources(a,b)
        r313=self.root/"313.json";r313.write_text(json.dumps(a))
        r348=self.root/"348.json";r348.write_text(json.dumps(b))
        old313=self.root/"old313.csv";old313.write_bytes(first)
        old348=self.root/"old348.csv";old348.write_bytes(second)
        locator=self.root/"source-root.txt"
        locator.write_text(str(self.root),encoding="utf-8")
        forged=raw.replace(b"tail_reason_code,4\\n",b"tail_reason_code,7\\n")
        (self.directory/"audio-exit-tail-reason-000.csv").write_bytes(forged)
        argv=["--guest-root-file",str(locator),
              "--stage313",str(r313),"--stage348",str(r348),
              "--stage313-original",str(old313),
              "--stage348-original",str(old348),
              "--output",str(self.root/"out.json"),
              "--output-original",str(self.root/"out.csv")]
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            status=main(argv)
        self.assertEqual(status,2)
        diagnostic=json.loads(buf.getvalue())
        self.assertEqual(diagnostic["failed_phase"],"stage351-guest-source-reaudit")
        self.assertFalse(diagnostic["stage351_reason_code_validated"])
        self.assertFalse((self.root/"out.csv").exists())

    def test_workflow_quarantine_only_follows_failed_stage351(self):
        workflow=(Path(__file__).resolve().parents[1]/
                  ".github"/"workflows"/"emulator-smoke.yml").read_text(
                      encoding="utf-8")
        self.assertEqual(workflow.count("id: stage351_audit"),1)
        self.assertEqual(workflow.count(
            "if: ${{ failure() && steps.stage351_audit.outcome == 'failure' }}"),1)
        source=workflow.index("- name: Stage351 verify original")
        quarantine=workflow.index("- name: Preserve bounded unverified")
        self.assertLess(source,quarantine)
        self.assertLess(quarantine,workflow.index(
            "- name: Capture ten additional A/B transitions"))

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

    def test_reject_indirect_guest_root_symlink_escape(self):
        raw,a,b=self.fixture()
        (self.directory/"audio-exit-tail-reason-000.csv").write_bytes(raw)
        linked=self.root/"linked-parent"
        linked.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ExitTimelineError):
            audit_guest(linked/SUBDIR.parent,a,b)

    def test_reject_symlinked_ancestor_of_original_receipt(self):
        raw,a,b=self.fixture()
        (self.directory/"audio-exit-tail-reason-000.csv").write_bytes(raw)
        first,second=self.original_sources(a,b)
        src313=self.root/"source313.csv";src313.write_bytes(first)
        src348=self.root/"source348.csv";src348.write_bytes(second)
        receipt313=self.root/"313.json";receipt313.write_text(json.dumps(a))
        receipt348=self.root/"348.json";receipt348.write_text(json.dumps(b))
        locator=self.root/"guest.txt";locator.write_text(str(self.root))
        linked=self.root/"linked-root"
        linked.symlink_to(self.root,target_is_directory=True)
        argv=[
            "--guest-root-file",str(locator),
            "--stage313",str(linked/"313.json"),
            "--stage348",str(receipt348),
            "--stage313-original",str(src313),
            "--stage348-original",str(src348),
            "--output",str(self.root/"new.json"),
            "--output-original",str(self.root/"new.csv"),
        ]
        self.assertEqual(main(argv),2)
        self.assertFalse((self.root/"new.csv").exists())

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
