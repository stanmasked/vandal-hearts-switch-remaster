"""Stage382 synthetic fail-closed controls; no synthetic material counts as a guest run."""
from pathlib import Path
from unittest import TestCase, mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage373_six_optical_originals as original
import audit_stage378_twelve_optical_originals as prior
import audit_stage382_sixteen_optical_originals as module


def row(run,trial,index):
    return {"run_id":run,"trial":trial,"dwell_seconds":6 if trial=="a" else 12,
            "guest_result":0,"released_descriptors":1,"pcm_pages_acquired_and_released":2000+index,
            "tail_interval_ms":4.8,"guest_event_rows":23,"complete_scene_serials":4,
            "dropped_guest_events":0,"pixel_packet_sha256":f"{index+1:064x}",
            "original_optical_sha256":f"{index+101:064x}",
            "original_reason_sha256":f"{index+201:064x}",
            "pixel_packet_crc32":f"{index+1:08x}"}


def fixture():
    sessions=[row(r,tag,i) for i,(r,tag) in enumerate((r,t) for r in module.ALL_RUNS for t in ("a","b"))]
    # The real original source situation: two independent NeXium sessions
    # happen to emit an identical software counter CSV. Optical source differs.
    sessions[11]["original_reason_sha256"]=sessions[13]["original_reason_sha256"]
    previous={"result":prior.RESULT,
      "source_run_ids":list(module.PRIOR_RUNS),"nro_sha256":original.NRO_SHA,
      "guest_sessions":12,"all_wait_results_zero":True,
      "all_release_counts_one":True,"all_optical_packet_hashes_distinct":True,
      "new_guest_sessions_created_by_audit":False,
      "physical_switch_speaker_audio_tested":False,
      "cause_of_historical_0xEA01_proven":False,
      "sessions":sessions[:12]}
    return previous,sessions[12:14],sessions[14:]

class Stage382Tests(TestCase):
    def test_accept_distinct_optical_packets_with_identical_counter_csv(self):
        result=module.combine(*fixture())
        self.assertEqual(result["original_guest_sessions"],16)
        self.assertEqual(result["distinct_reason_csv_sha256_count"],15)
        self.assertEqual(len(result["repeated_reason_csv"]),1)
        self.assertEqual(result["complete_scene_transitions"],64)
        self.assertFalse(result["physical_switch_speaker_audio_tested"])

    def test_reject_duplicate_png_or_decoded_optical_payload(self):
        for key in ("original_optical_sha256","pixel_packet_sha256"):
            prior_source,seventh,eighth=fixture()
            eighth[1][key]=prior_source["sessions"][0][key]
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.combine(prior_source,seventh,eighth)

    def test_reject_service_failure_descriptor_or_pcm_leak(self):
        for key,value in (("guest_result",0xEA01),("released_descriptors",0),
                          ("pcm_pages_acquired_and_released",0),
                          ("pcm_pages_acquired_and_released",True)):
            p,seven,eight=fixture(); seven[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                module.combine(p,seven,eight)

    def test_reject_invalid_scene_timing_and_event_loss(self):
        for key,value in (("tail_interval_ms",12),("tail_interval_ms",-1),
                          ("complete_scene_serials",3),("guest_event_rows",22),
                          ("dropped_guest_events",1)):
            p,seven,eight=fixture();eight[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                module.combine(p,seven,eight)

    def test_reject_new_run_tag_or_dwell_substitution(self):
        for key,value in (("run_id",999),("trial","b"),("dwell_seconds",12)):
            p,seven,eight=fixture();seven[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.combine(p,seven,eight)

    def test_reject_missing_duplicate_or_misordered_record(self):
        p,seven,eight=fixture();seven.pop()
        with self.assertRaises(ValueError):module.combine(p,seven,eight)
        p,seven,eight=fixture();eight.append(eight[-1])
        with self.assertRaises(ValueError):module.combine(p,seven,eight)
        p,seven,eight=fixture();eight.reverse()
        with self.assertRaises(ValueError):module.combine(p,seven,eight)

    def test_reject_old_twelve_source_forged_pass(self):
        for key,value in (("source_run_ids",[1]*6),("nro_sha256","0"*64),
                          ("all_wait_results_zero",False),
                          ("physical_switch_speaker_audio_tested",True),
                          ("new_guest_sessions_created_by_audit",True)):
            p,seven,eight=fixture();p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.combine(p,seven,eight)

    def test_noncanonical_hash_crc_and_missing_key_rejected(self):
        for key,value in (("original_reason_sha256","G"*64),
                          ("original_optical_sha256","123"),
                          ("pixel_packet_crc32","123")):
            p,seven,eight=fixture();eight[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.combine(p,seven,eight)
        p,seven,eight=fixture();del eight[0]["original_reason_sha256"]
        with self.assertRaises(ValueError):module.combine(p,seven,eight)

    def test_verify_error_restores_original_source_pins(self):
        p,seven,_=fixture();existing=dict(original.RUNS)
        def verify(run,*args):
            if run==module.NEW_RUNS[0]:return seven
            raise ValueError("second original source unavailable")
        with mock.patch.object(prior,"audit",return_value=p), \
             mock.patch.object(original,"verify",side_effect=verify):
            with self.assertRaises(ValueError):
                module.audit(Path("/missing"),Path("/missing"))
        self.assertEqual(original.RUNS,existing)

    def test_colliding_source_pin_fails_closed(self):
        with mock.patch.dict(original.RUNS,{module.NEW_RUNS[0]:{"invalid":True}}):
            with self.assertRaises(ValueError):
                module.audit(Path("/missing"),Path("/missing"))
