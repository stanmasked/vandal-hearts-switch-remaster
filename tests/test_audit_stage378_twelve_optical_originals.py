"""Stage378 synthetic fail-closed controls. Fixtures never constitute original NeXium data."""
from pathlib import Path
from unittest import TestCase,mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage373_six_optical_originals as original
import audit_stage374_eight_optical_originals as eight
import audit_stage378_twelve_optical_originals as module

def session(run,tag,i):
    return {"run_id":run,"trial":tag,"dwell_seconds":6 if tag=="a" else 12,
     "guest_result":0,"released_descriptors":1,"complete_scene_serials":4,
     "guest_event_rows":23,"dropped_guest_events":0,"tail_interval_ms":4.8,
     "pcm_pages_acquired_and_released":2100+i,
     "pixel_packet_sha256":f"{i+1:064x}",
     "original_optical_sha256":f"{i+101:064x}",
     "original_reason_sha256":f"{i+201:064x}",
     "pixel_packet_crc32":f"{i+1:08x}"}
def fixture():
    rows=[session(r,t,i) for i,(r,t) in enumerate((r,t) for r in module.RUNS for t in ("a","b"))]
    old={"result":eight.RESULT,"source_workflow_run_ids":list(module.RUNS[:4]),
      "nro_sha256":original.NRO_SHA,"original_guest_session_count":8,
      "all_eight_guest_optical_packets_unique":True,
      "all_eight_wait_results_zero":True,"all_eight_returned_descriptors_one":True,
      "physical_switch_speaker_audio_tested":False,
      "historical_0xEA01_root_cause_proven":False,
      "new_guest_sessions_created_by_replay":False,"sessions":rows[:8]}
    return old,rows[8:10],rows[10:]

class Stage378Tests(TestCase):
    def test_twelve_exactly_once_and_no_hardware_claim(self):
        report=module.combine(*fixture())
        self.assertEqual(report["guest_sessions"],12)
        self.assertEqual(report["source_run_ids"],list(module.RUNS))
        self.assertFalse(report["physical_switch_speaker_audio_tested"])

    def test_duplicate_packet_png_or_reason_hash_is_rejected(self):
        for name in module.HASHES:
            old,fifth,sixth=fixture()
            sixth[1][name]=old["sessions"][0][name]
            with self.subTest(name=name),self.assertRaises(ValueError):
                module.combine(old,fifth,sixth)

    def test_invalid_wait_pcm_tail_and_optical_rows_are_rejected(self):
        for name,value in (("guest_result",0xEA01),("released_descriptors",0),
             ("pcm_pages_acquired_and_released",0),("tail_interval_ms",12),
             ("tail_interval_ms",-1),("complete_scene_serials",3),
             ("guest_event_rows",22),("dropped_guest_events",1)):
            old,fifth,sixth=fixture();fifth[0][name]=value
            with self.subTest(name=name,value=value),self.assertRaises(ValueError):
                module.combine(old,fifth,sixth)

    def test_trial_dwell_or_run_substitution_rejected(self):
        for name,value in (("run_id",99),("trial","b"),("dwell_seconds",12)):
            old,fifth,sixth=fixture();fifth[0][name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):
                module.combine(old,fifth,sixth)

    def test_missing_or_extra_sessions_rejected(self):
        old,fifth,sixth=fixture();old["sessions"].pop()
        with self.assertRaises(ValueError):module.combine(old,fifth,sixth)
        old,fifth,sixth=fixture();sixth.append(sixth[-1])
        with self.assertRaises(ValueError):module.combine(old,fifth,sixth)

    def test_old_stage374_status_cannot_be_forged(self):
        for name,value in (("source_workflow_run_ids",[0,0,0,0]),
             ("nro_sha256","0"*64),("physical_switch_speaker_audio_tested",True),
             ("all_eight_wait_results_zero",False),
             ("new_guest_sessions_created_by_replay",True)):
            old,fifth,sixth=fixture();old[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):
                module.combine(old,fifth,sixth)

    def test_bad_sha_rejected(self):
        for bad in ("","A"*64,"short","0"*63):
            old,fifth,sixth=fixture();sixth[0]["original_reason_sha256"]=bad
            with self.subTest(value=bad),self.assertRaises(ValueError):
                module.combine(old,fifth,sixth)

    def test_failed_second_original_verification_restores_source_pins(self):
        old,fifth,sixth=fixture();pinned=dict(original.RUNS)
        def verify(run,*args):
            if run==module.NEW_RUNS[0]:return fifth
            raise ValueError("original sixth source absent")
        with mock.patch.object(eight,"audit",return_value=old), \
             mock.patch.object(original,"verify",side_effect=verify):
            with self.assertRaises(ValueError):
                module.audit(Path("/absent"),Path("/absent"))
        self.assertEqual(pinned,original.RUNS)

    def test_reject_colliding_historical_source_pin(self):
        with mock.patch.dict(original.RUNS,{module.NEW_RUNS[0]:{"fake":True}}):
            with self.assertRaises(ValueError):
                module.audit(Path("/absent"),Path("/absent"))
