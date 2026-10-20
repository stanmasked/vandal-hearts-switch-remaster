"""Stage383 host-only anti-substitution tests. Fixtures are not guest evidence."""
from pathlib import Path
from unittest import TestCase,mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage373_six_optical_originals as original
import audit_stage382_sixteen_optical_originals as prior
import audit_stage383_eighteen_optical_originals as module

def row(run,tag,i):
    return {"run_id":run,"trial":tag,"dwell_seconds":6 if tag=="a" else 12,
            "guest_result":0,"released_descriptors":1,
            "pcm_pages_acquired_and_released":2000+i,
            "tail_interval_ms":4.8,"guest_event_rows":23,
            "complete_scene_serials":4,"dropped_guest_events":0,
            "original_reason_sha256":f"{i+201:064x}",
            "original_optical_sha256":f"{i+101:064x}",
            "pixel_packet_sha256":f"{i+1:064x}",
            "pixel_packet_crc32":f"{i+1:08x}"}

def fixture():
    rows=[row(run,tag,i) for i,(run,tag) in enumerate(
        (r,t) for r in module.ALL_RUNS for t in ("a","b"))]
    rows[13]["original_reason_sha256"]=rows[11]["original_reason_sha256"]
    prev={"result":prior.RESULT,"source_run_ids":list(prior.ALL_RUNS),
          "nro_sha256":original.NRO_SHA,"original_guest_sessions":16,
          "all_software_wait_results_zero":True,
          "all_returned_descriptors_exactly_one":True,
          "all_sixteen_optical_pngs_and_packets_distinct":True,
          "physical_switch_speaker_audio_tested":False,
          "new_guest_sessions_created_by_audit":False,
          "cause_of_historical_0xEA01_proven":False,
          "sessions":rows[:16]}
    return prev,rows[16:]

class Stage383Tests(TestCase):
    def test_accept_unique_optical_and_repeated_counter_csv(self):
        report=module.combine(*fixture())
        self.assertEqual(report["original_guest_sessions"],18)
        self.assertEqual(report["distinct_reason_csv_sha256_count"],17)
        self.assertEqual(report["complete_music_scene_transitions"],72)
        self.assertFalse(report["physical_switch_speaker_audio_tested"])

    def test_reject_reused_source_png_and_optical_packet(self):
        for field in ("original_optical_sha256","pixel_packet_sha256"):
            p,n=fixture();n[0][field]=p["sessions"][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.combine(p,n)

    def test_reject_wait_error_descriptor_count_and_pcm_accounting(self):
        for field,value in (("guest_result",0xEA01),("released_descriptors",0),
                            ("pcm_pages_acquired_and_released",0),
                            ("pcm_pages_acquired_and_released",True)):
            p,n=fixture();n[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.combine(p,n)

    def test_reject_missing_or_wrong_optical_scene_chronology(self):
        for field,value in (("tail_interval_ms",12),("tail_interval_ms",-1),
                            ("guest_event_rows",22),("complete_scene_serials",3),
                            ("dropped_guest_events",1)):
            p,n=fixture();n[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.combine(p,n)

    def test_reject_run_tag_and_dwell_substitution(self):
        for field,value in (("run_id",123),("trial","b"),("dwell_seconds",12)):
            p,n=fixture();n[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.combine(p,n)

    def test_reject_missing_extra_and_reversed_pair(self):
        p,n=fixture();n.pop()
        with self.assertRaises(ValueError):module.combine(p,n)
        p,n=fixture();n.append(n[1])
        with self.assertRaises(ValueError):module.combine(p,n)
        p,n=fixture();n.reverse()
        with self.assertRaises(ValueError):module.combine(p,n)

    def test_reject_forged_previous_original_source_receipt(self):
        for field,value in (("source_run_ids",[0]*8),("nro_sha256","0"*64),
                            ("all_software_wait_results_zero",False),
                            ("physical_switch_speaker_audio_tested",True),
                            ("new_guest_sessions_created_by_audit",True)):
            p,n=fixture();p[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.combine(p,n)

    def test_reject_malformed_sha256_and_pixel_crc(self):
        for field,value in (("original_reason_sha256","A"*64),
                            ("original_optical_sha256","123"),
                            ("pixel_packet_crc32","bad")):
            p,n=fixture();n[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.combine(p,n)

    def test_error_does_not_leave_extra_source_pin(self):
        p,n=fixture()
        old=dict(original.RUNS)
        with mock.patch.object(prior,"audit",return_value=p), \
             mock.patch.object(original,"verify",side_effect=ValueError("missing")):
            with self.assertRaises(ValueError):
                module.audit(Path("/absent"),Path("/absent"))
        self.assertEqual(original.RUNS,old)

    def test_original_source_pin_collision_rejected(self):
        with mock.patch.dict(original.RUNS,{module.NINTH_RUN:{"forged":True}}):
            with self.assertRaises(ValueError):
                module.audit(Path("/absent"),Path("/absent"))
