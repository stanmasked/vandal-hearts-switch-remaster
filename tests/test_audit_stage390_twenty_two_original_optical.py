"""Synthetic anti-substitution tests: NOT genuine NeXium or Nintendo Switch audio."""
from pathlib import Path
from unittest import TestCase,mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage373_six_optical_originals as original
import audit_stage386_twenty_optical_nexium_sources as prior
import audit_stage390_twenty_two_original_optical as a

def scenario():
    rows=[]
    for i,(run,tag) in enumerate((r,t) for r in a.RUNS for t in ("a","b")):
        rows.append({"run_id":run,"trial":tag,"dwell_seconds":6 if tag=="a" else 12,
                     "guest_result":0,"released_descriptors":1,
                     "pcm_pages_acquired_and_released":2000+i,"tail_interval_ms":5.0,
                     "complete_scene_serials":4,"guest_event_rows":23,"dropped_guest_events":0,
                     "original_optical_sha256":f"{i+301:064x}",
                     "pixel_packet_sha256":f"{i+401:064x}",
                     "original_reason_sha256":f"{i+501:064x}"})
    rows[13]["original_reason_sha256"]=rows[11]["original_reason_sha256"]
    rows[19]["original_reason_sha256"]=a.PIN["reason"][1]
    rows[21]["original_reason_sha256"]=a.PIN["reason"][1]
    old={"result":prior.RESULT,"source_run_ids":list(prior.ALL_RUNS),
         "original_guest_sessions":20,"guest_wait_result_zero":20,
         "exact_returned_descriptors":20,"unique_crc_verified_optical_packets":20,
         "complete_music_scene_transitions":80,"dropped_guest_events":0,
         "nro_sha256":original.NRO_SHA,"physical_switch_speaker_audio_tested":False,
         "cause_of_historical_0xEA01_proven":False,
         "tenth_run_neixum_emulator":{
             "archive_sha256":prior.EXPECTED_EMULATOR_TAR,
             "binary_sha256":prior.EXPECTED_EMULATOR_BIN,
             "same_binary_in_earlier_nine_runs_proven":False,
             "physical_switch_audio_tested":False},
         "sessions":rows[:20]}
    e={"archive_sha256":prior.EXPECTED_EMULATOR_TAR,
       "binary_sha256":prior.EXPECTED_EMULATOR_BIN,
       "same_neixum_binary_on_runs_10_and_11":True,
       "same_neixum_binary_on_runs_1_to_9_proven":False}
    return old,rows[20:],e

class Stage390Tests(TestCase):
    def test_accept_22_distinct_optical_guests_and_20_reason_shas(self):
        d=a.combine(*scenario())
        self.assertEqual(d["original_guest_sessions"],22)
        self.assertEqual(d["complete_music_scene_transitions"],88)
        self.assertEqual(d["distinct_reason_counter_csv_sha256_count"],20)
        self.assertFalse(d["physical_switch_speaker_audio_tested"])

    def test_reject_duplicate_png_or_decoded_packet(self):
        for key in ("original_optical_sha256","pixel_packet_sha256"):
            p,q,e=scenario();q[0][key]=p["sessions"][0][key]
            with self.subTest(field=key),self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_result_descriptor_lease_or_event_mismatch(self):
        for key,val in (("guest_result",59905),("released_descriptors",0),
                        ("pcm_pages_acquired_and_released",0),
                        ("pcm_pages_acquired_and_released",True),
                        ("tail_interval_ms",12),("complete_scene_serials",3),
                        ("guest_event_rows",21),("dropped_guest_events",1)):
            p,q,e=scenario();q[0][key]=val
            with self.subTest(field=key),self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_swapped_missing_extra_or_cross_run_source(self):
        for mutation in ("swap","missing","extra","wrongrun"):
            p,q,e=scenario()
            if mutation=="swap":q.reverse()
            if mutation=="missing":q.pop()
            if mutation=="extra":q.append(q[-1])
            if mutation=="wrongrun":q[0]["run_id"]=0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_claim_that_unknown_earlier_emulator_versions_match(self):
        for key,val in (("binary_sha256","0"*64),("archive_sha256","0"*64),
                        ("same_neixum_binary_on_runs_10_and_11",False),
                        ("same_neixum_binary_on_runs_1_to_9_proven",True)):
            p,q,e=scenario();e[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_prior_source_proof_tampering(self):
        for key,val in (("result","bogus"),("original_guest_sessions",19),
                        ("source_run_ids",[0]),
                        ("physical_switch_speaker_audio_tested",True)):
            p,q,e=scenario();p[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_unauthenticated_repeated_reason_counter(self):
        p,q,e=scenario();q[1]["original_reason_sha256"]=p["sessions"][0]["original_reason_sha256"]
        with self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_prior_tenth_original_counter_tampering(self):
        p,q,e=scenario();p["sessions"][19]["original_reason_sha256"]="f"*64
        with self.assertRaises(ValueError):a.combine(p,q,e)

    def test_reject_malformed_guest_source_digest(self):
        p,q,e=scenario();q[0]["pixel_packet_sha256"]="invalid"
        with self.assertRaises(ValueError):a.combine(p,q,e)

    def test_no_new_run_pin_remains_on_original_source_failure(self):
        p,q,e=scenario();old=dict(original.RUNS)
        with mock.patch.object(prior,"audit",return_value=p), \
             mock.patch.object(original,"verify",side_effect=ValueError("missing")):
            with self.assertRaises(ValueError):a.audit(Path("/absent"),Path("/absent"))
        self.assertEqual(original.RUNS,old)

    def test_reject_pin_collision(self):
        with mock.patch.dict(original.RUNS,{a.NEW_RUN:{"forged":True}}):
            with self.assertRaises(ValueError):a.audit(Path("/absent"),Path("/absent"))
