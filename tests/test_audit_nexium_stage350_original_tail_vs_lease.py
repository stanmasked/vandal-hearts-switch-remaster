#!/usr/bin/env python3
"""Stage350 synthetic source tamper controls; no original guest claim."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_nexium_guest_lease_reconciliation_stage348 import (
    KEYS, audit_source as audit_lease_source,
)
from audit_nexium_guest_last_buffer_return import (
    COMPLETE, SCHEMA as TAIL_SCHEMA, FIELDS as TAIL_FIELDS,
)
from compare_nexium_stage349_original_lease_cohorts import read_original
from audit_nexium_stage350_original_tail_vs_lease import (
    PRESERVED, compare_pairs, main, read_pair, read_tail_original,
)


class Stage350Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixtures(self, name="one", abandoned=1, tail_returned=False):
        folder = self.root / name
        folder.mkdir()
        lease_vals = dict(
            software_lease_only=1,
            lease_pages_acquired=20,
            lease_pages_released=20-abandoned,
            abandoned_sessions=abandoned,
            busy_begin_rejections=0,
            mismatched_releases=0,
            accepted_pages_submitted=19,
            submit_failures=0,
        )
        lease_raw=b"scope,value\n"+b"".join(
            f"{key},{lease_vals[key]}\n".encode("ascii") for key in KEYS
        )
        lease_csv = folder/"audio-lease-reconciliation-000.csv"
        lease_csv.write_bytes(lease_raw)
        lease_sha = hashlib.sha256(lease_raw).hexdigest()
        lease_receipt = folder/"guest-lease-reconciliation-stage348.json"
        lease_receipt.write_text(json.dumps(audit_lease_source(lease_raw)))

        tail_vals = dict(
            page_return_count=19,
            last_page_return_guest_ns=100,
            last_page_frames=256,
            tail_attempt_guest_ns=200,
            tail_success_return_guest_ns=210 if tail_returned else 0,
        )
        tail_raw=b"event,value\n"+b"".join(
            f"{key},{tail_vals[key]}\n".encode("ascii") for key in TAIL_FIELDS
        )
        tail_csv=folder/"audio-exit-output-000.csv"
        tail_csv.write_bytes(tail_raw)
        tail_sha=hashlib.sha256(tail_raw).hexdigest()
        stage313=folder/"guest-last-audout-release-stage313.json"
        receipt313={
            "schema":TAIL_SCHEMA,
            "result":COMPLETE,
            "original_guest_page_witness_sha256":tail_sha,
            "original_guest_page_witness_observed":True,
            **{key:(value if value else None) if key.endswith("_guest_ns")
               else value for key,value in tail_vals.items()},
            "tail_bounded_attempt_observed":True,
            "tail_release_confirmed":tail_returned,
            "last_page_return_is_not_DAC_or_speaker_output":True,
            "normal_exit_taper_is_not_PS1_SPU_rendered_music":True,
            "hardware_Nintendo_Switch_audio_tested":False,
            "audible_dropout_verified":False,
        }
        stage313.write_text(json.dumps(receipt313))
        stage314=folder/"guest-original-audout-last-page-stage314.json"
        stage314.write_text(json.dumps({
            "result":PRESERVED,
            "original_guest_output_csv_sha256":tail_sha,
            "original_guest_output_csv_preserved":True,
            "original_guest_source_bytes_reaudited":True,
            "source_stage313_reproduced":True,
            "physical_Nintendo_Switch_audio_tested":False,
            "audout_buffer_release_not_speaker_playback":True,
        }))
        return (lease_csv,lease_receipt,lease_sha,tail_csv,stage313,stage314,tail_sha)

    def load(self, f):
        return read_pair(*f)

    def test_distinct_originals_concordance_without_causality(self):
        a=self.load(self.fixtures("a"))
        b=self.load(self.fixtures("b",0,True))
        doc=compare_pairs(a,b,39292707481,39292997818)
        self.assertTrue(doc["unconfirmed_tail_and_abandoned_lease_coincide_in_both_sources"])
        self.assertFalse(doc["one_to_one_causal_attribution_proven"])
        self.assertFalse(doc["physical_Nintendo_Switch_audio_tested"])

    def test_tail_failure_and_abandonment_can_diverge(self):
        a=self.load(self.fixtures("a",0,False))
        b=self.load(self.fixtures("b",1,True))
        doc=compare_pairs(a,b,1,2)
        self.assertFalse(doc["unconfirmed_tail_and_abandoned_lease_coincide_in_both_sources"])

    def test_reject_same_source_pair(self):
        a=self.load(self.fixtures("a"))
        with self.assertRaises(ValueError):
            compare_pairs(a,a,1,2)

    def test_reject_duplicate_run_id(self):
        a=self.load(self.fixtures("a"))
        b=self.load(self.fixtures("b",0,True))
        with self.assertRaises(ValueError):
            compare_pairs(a,b,5,5)

    def test_reject_missing_run_id(self):
        a=self.load(self.fixtures("a"))
        b=self.load(self.fixtures("b",0,True))
        with self.assertRaises(ValueError):
            compare_pairs(a,b,0,5)

    def test_reject_wrong_tail_hash_pin(self):
        a=self.fixtures()
        with self.assertRaises(ValueError):
            read_tail_original(a[3],a[4],a[5],"0"*64)

    def test_reject_undocumented_tail_hash(self):
        a=self.fixtures()
        with self.assertRaises(ValueError):
            read_tail_original(a[3],a[4],a[5],"NOT_A_SHA")

    def test_reject_original_tail_source_mutation(self):
        a=self.fixtures()
        a[3].write_bytes(a[3].read_bytes()+b"extra,1\n")
        with self.assertRaises(ValueError):
            self.load(a)

    def test_reject_forged_tail_return_receipt(self):
        a=self.fixtures()
        s=json.loads(a[4].read_text())
        s["tail_release_confirmed"]=True
        a[4].write_text(json.dumps(s))
        with self.assertRaises(ValueError):
            self.load(a)

    def test_reject_forged_stage314_source_hash(self):
        a=self.fixtures()
        s=json.loads(a[5].read_text())
        s["original_guest_output_csv_sha256"]="0"*64
        a[5].write_text(json.dumps(s))
        with self.assertRaises(ValueError):
            self.load(a)

    def test_reject_forged_hardware_claim(self):
        a=self.fixtures()
        s=json.loads(a[4].read_text())
        s["hardware_Nintendo_Switch_audio_tested"]=True
        a[4].write_text(json.dumps(s))
        with self.assertRaises(ValueError):
            self.load(a)

    def test_reject_source_stage313_not_reproduced(self):
        a=self.fixtures()
        s=json.loads(a[5].read_text())
        s["source_stage313_reproduced"]=False
        a[5].write_text(json.dumps(s))
        with self.assertRaises(ValueError):
            self.load(a)

    def test_reject_tail_with_wrong_row_order(self):
        a=self.fixtures()
        raw=a[3].read_bytes()
        raw=raw.replace(b"last_page_frames,256\n",b"last_page_FRAMES,256\n")
        a[3].write_bytes(raw)
        with self.assertRaises(ValueError):
            read_tail_original(a[3],a[4],a[5],hashlib.sha256(raw).hexdigest())

    def test_reject_tail_clock_reversal(self):
        a=self.fixtures()
        raw=a[3].read_bytes().replace(b"tail_attempt_guest_ns,200\n",
                                      b"tail_attempt_guest_ns,90\n")
        a[3].write_bytes(raw)
        with self.assertRaises(ValueError):
            read_tail_original(a[3],a[4],a[5],hashlib.sha256(raw).hexdigest())

    def test_reject_symlinked_source(self):
        a=self.fixtures()
        link=self.root/"tail-symlink.csv"
        link.symlink_to(a[3])
        with self.assertRaises(ValueError):
            read_tail_original(link,a[4],a[5],a[6])

    def test_reject_lease_receipt_count_tamper(self):
        a=self.fixtures()
        receipt=json.loads(a[1].read_text())
        receipt["abandoned_sessions"]=0
        a[1].write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.load(a)

    def test_full_cli_receipt_and_no_overwrite(self):
        a=self.fixtures("a")
        b=self.fixtures("b",0,True)
        path=self.root/"stage350.json"
        args=[]
        for label,fx,run_id in (("first",a,"1"),("second",b,"2")):
            for key,value in zip(
                ("lease-csv","lease-receipt","lease-sha256",
                 "tail-csv","stage313","stage314","tail-sha256"),fx
            ):
                args += [f"--{label}-{key}",str(value)]
            args += [f"--{label}-run-id",run_id]
        args += ["--output",str(path)]
        self.assertEqual(main(args),0)
        self.assertTrue(json.loads(path.read_text())[
            "unconfirmed_tail_and_abandoned_lease_coincide_in_both_sources"])
        self.assertEqual(main(args),2)


if __name__=="__main__":
    unittest.main()
