"""Synthetic fail-closed Stage374 controls, not original guest captures."""
import copy
from pathlib import Path
from unittest import TestCase, mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage373_six_optical_originals as old
import audit_stage374_eight_optical_originals as module


def one(run,tag,i):
    return {"run_id":run,"trial":tag,"dwell_seconds":6 if tag=="a" else 12,
            "guest_result":0,"released_descriptors":1,"complete_scene_serials":4,
            "guest_event_rows":23,"dropped_guest_events":0,"tail_interval_ms":4.8,
            "pcm_pages_acquired_and_released":2000+i,
            "pixel_packet_sha256":f"{i+1:064x}",
            "original_reason_sha256":f"{i+20:064x}",
            "original_optical_sha256":f"{i+40:064x}"}


def fixture():
    six=[one(run,tag,idx) for idx,(run,tag) in enumerate((r,t) for r in module.SIX_RUNS for t in ("a","b"))]
    report={"result":old.RESULT,"source_workflow_run_ids":list(module.SIX_RUNS),
            "nro_sha256":old.NRO_SHA,"all_six_optical_packets_unique":True,
            "all_six_original_guest_waits_succeeded":True,
            "physical_nintendo_switch_audio_tested":False,"sessions":six}
    fourth=[one(module.FOURTH_RUN,"a",6),one(module.FOURTH_RUN,"b",7)]
    return report,fourth


class Stage374Tests(TestCase):
    def test_valid_eight_distinct_records_and_explicit_claim_boundary(self):
        six,fourth=fixture();result=module.combine(six,fourth)
        self.assertEqual(result["original_guest_session_count"],8)
        self.assertEqual(result["result"],module.RESULT)
        self.assertFalse(result["physical_switch_speaker_audio_tested"])
        self.assertFalse(result["historical_0xEA01_root_cause_proven"])

    def test_duplicate_pixels_rejected(self):
        six,fourth=fixture();fourth[1]["pixel_packet_sha256"]=six["sessions"][0]["pixel_packet_sha256"]
        with self.assertRaises(ValueError):module.combine(six,fourth)

    def test_lease_or_wait_or_return_forgery_rejected(self):
        for key,value in (("guest_result",0xEA01),("released_descriptors",0),
                          ("pcm_pages_acquired_and_released",0),
                          ("tail_interval_ms",13),("complete_scene_serials",3),
                          ("dropped_guest_events",1)):
            six,fourth=fixture();fourth[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.combine(six,fourth)

    def test_substituted_guest_trial_or_missing_source_rejected(self):
        six,fourth=fixture();fourth[0]["run_id"]=39396243731
        with self.assertRaises(ValueError):module.combine(six,fourth)
        six,fourth=fixture();six["sessions"].pop()
        with self.assertRaises(ValueError):module.combine(six,fourth)

    def test_no_source_pin_mutation_on_guest_download_failure(self):
        six,_=fixture()
        with mock.patch.object(old,"audit",return_value=six), mock.patch.object(old,"verify",side_effect=ValueError("guest missing")):
            before=dict(old.RUNS)
            with self.assertRaises(ValueError):
                module.audit(Path("/not-found"),Path("/not-found"))
            self.assertEqual(old.RUNS,before)

    def test_original_stage373_identity_cannot_be_replaced(self):
        six,fourth=fixture();six["source_workflow_run_ids"]=[0,0,0]
        with self.assertRaises(ValueError):module.combine(six,fourth)
