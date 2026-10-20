#!/usr/bin/env python3
"""Stage352 archived-original-source replay regression tests; no fake NeXium proof."""
from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_lease_reconciliation_stage348 import (
    KEYS as LEASE_KEYS, audit_source as audit_lease,
)
from audit_nexium_guest_tail_reason_stage351 import (
    KEYS as REASON_KEYS, audit_source as audit_reason,
)
from audit_nexium_stage352_three_original_tail_sources import (
    VERIFIED, main, reaudited_archive,
)


class Stage352Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)

    def fixture(self,returned=True):
        acquired=1441
        released=1441 if returned else 1440
        abandoned=int(not returned)
        lease_fields={
            "software_lease_only":1,
            "lease_pages_acquired":acquired,
            "lease_pages_released":released,
            "abandoned_sessions":abandoned,
            "busy_begin_rejections":0,
            "mismatched_releases":0,
            "accepted_pages_submitted":1440,
            "submit_failures":0,
        }
        lease_raw=b"scope,value\n"+b"".join(
            f"{k},{lease_fields[k]}\n".encode("ascii") for k in LEASE_KEYS
        )
        lease_report=audit_lease(lease_raw)
        tail_fields={
            "page_return_count":1440,
            "last_page_return_guest_ns":100,
            "last_page_frames":256,
            "tail_attempt_guest_ns":200,
            "tail_success_return_guest_ns":210 if returned else 0,
        }
        tail_raw=b"event,value\n"+b"".join(
            f"{k},{v}\n".encode("ascii") for k,v in tail_fields.items()
        )
        tail_hash=hashlib.sha256(tail_raw).hexdigest()
        stage313={
            "schema":"vh-guest-last-audout-page-release-versus-exit/v1",
            "result":"GUEST_LAST_AUDOUT_RELEASE_SOFTWARE_TIMING_VALIDATED",
            "original_guest_page_witness_sha256":tail_hash,
            "original_guest_page_witness_observed":True,
            "tail_bounded_attempt_observed":True,
            "tail_release_confirmed":returned,
            "last_page_return_is_not_DAC_or_speaker_output":True,
            "normal_exit_taper_is_not_PS1_SPU_rendered_music":True,
            "hardware_Nintendo_Switch_audio_tested":False,
            "audible_dropout_verified":False,
            **{k:(v if v or not k.endswith("_guest_ns") else None)
               for k,v in tail_fields.items()},
        }
        stage314={
            "result":"ORIGINAL_GUEST_LAST_AUDOUT_SOURCE_PRESERVED_AND_REAUDITED",
            "original_guest_output_csv_sha256":tail_hash,
            "original_guest_output_csv_preserved":True,
            "original_guest_source_bytes_reaudited":True,
            "source_stage313_reproduced":True,
            "physical_Nintendo_Switch_audio_tested":False,
            "audout_buffer_release_not_speaker_playback":True,
        }
        reason_fields={
            "software_exit_tail_reason_only":1,
            "tail_reason_code":7 if returned else 4,
            "tail_attempted":1,
            "tail_descriptor_return_confirmed":int(returned),
            "tail_lease_acquired":1,
            "lease_pages_acquired":acquired,
            "lease_pages_released":released,
            "abandoned_sessions":abandoned,
        }
        reason_raw=b"scope,value\n"+b"".join(
            f"{k},{reason_fields[k]}\n".encode("ascii") for k in REASON_KEYS
        )
        reason_receipt=audit_reason(reason_raw,stage313,lease_report)
        data={
            "tail":tail_raw,"lease":lease_raw,"reason":reason_raw,
            "stage313":stage313,"stage314":stage314,
            "stage348":lease_report,"stage351":reason_receipt,
        }
        paths={}
        for key,value in data.items():
            path=self.root/("audio-"+key+(".csv" if isinstance(value,bytes) else ".json"))
            if isinstance(value,bytes): path.write_bytes(value)
            else: path.write_text(json.dumps(value),encoding="utf-8")
            paths[key]=path
        pins={k:hashlib.sha256(data[k]).hexdigest() for k in ("tail","lease","reason")}
        return paths,pins

    def test_successful_exact_tail_original_replay(self):
        paths,pins=self.fixture()
        report=reaudited_archive(paths,pins,39308380160)
        self.assertEqual(report["result"],VERIFIED)
        self.assertEqual(report["tail_reason_code"],7)
        self.assertEqual(report["lease_pages_acquired"],1441)
        self.assertEqual(report["lease_pages_released"],1441)
        self.assertFalse(report["physical_Nintendo_Switch_audio_tested"])

    def test_failed_bounded_wait_source_can_be_consistent(self):
        paths,pins=self.fixture(returned=False)
        report=reaudited_archive(paths,pins,1)
        self.assertEqual(report["tail_reason_code"],4)
        self.assertEqual(report["abandoned_sessions"],1)
        self.assertFalse(report["older_unconfirmed_tail_failure_cause_proven"])

    def test_reject_wrong_run_id(self):
        paths,pins=self.fixture()
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,0)

    def test_reject_unpinned_tail_source(self):
        paths,pins=self.fixture()
        pins["tail"]="0"*64
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,39308380160)

    def test_reject_unpinned_pcm_lease_source(self):
        paths,pins=self.fixture()
        pins["lease"]="0"*64
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,39308380160)

    def test_reject_unpinned_stage351_source(self):
        paths,pins=self.fixture()
        pins["reason"]="0"*64
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,39308380160)

    def test_reject_modified_tail_original(self):
        paths,pins=self.fixture()
        paths["tail"].write_bytes(paths["tail"].read_bytes()+b"new,1\n")
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_modified_lease_original(self):
        paths,pins=self.fixture()
        paths["lease"].write_bytes(paths["lease"].read_bytes()+b"new,1\n")
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_modified_reason_original(self):
        paths,pins=self.fixture()
        paths["reason"].write_bytes(paths["reason"].read_bytes()+b"new,1\n")
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_forged_success_reason_receipt(self):
        paths,pins=self.fixture()
        r=json.loads(paths["stage351"].read_text())
        r["reason_code"]=4
        paths["stage351"].write_text(json.dumps(r))
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_forged_hardware_claim(self):
        paths,pins=self.fixture()
        r=json.loads(paths["stage351"].read_text())
        r["physical_Nintendo_Switch_audio_tested"]=True
        paths["stage351"].write_text(json.dumps(r))
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_forged_stage313_receipt(self):
        paths,pins=self.fixture()
        r=json.loads(paths["stage313"].read_text())
        r["tail_release_confirmed"]=False
        paths["stage313"].write_text(json.dumps(r))
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_forged_stage348_receipt(self):
        paths,pins=self.fixture()
        r=json.loads(paths["stage348"].read_text())
        r["lease_pages_released"]=1440
        paths["stage348"].write_text(json.dumps(r))
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_reject_symlinked_original(self):
        paths,pins=self.fixture()
        link=self.root/"alias.csv"
        link.symlink_to(paths["reason"])
        paths["reason"]=link
        with self.assertRaises(ValueError):
            reaudited_archive(paths,pins,1)

    def test_refuse_existing_report(self):
        paths,pins=self.fixture()
        target=self.root/"stage352.json"
        args=[]
        for key in ("tail","lease","reason"):
            args += ["--"+key+"-csv",str(paths[key]),
                     "--"+key+"-sha256",pins[key]]
        for key in ("stage313","stage314","stage348","stage351"):
            args += ["--"+key,str(paths[key])]
        args += ["--original-run-id","39308380160","--output",str(target)]
        self.assertEqual(main(args),0)
        self.assertEqual(json.loads(target.read_text())["result"],VERIFIED)
        self.assertEqual(main(args),2)


if __name__=="__main__":
    unittest.main()
