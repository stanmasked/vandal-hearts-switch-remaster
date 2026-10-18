"""Stage309 independent authentic optical image replay / guest exit receipt tests."""
from __future__ import annotations

import copy
import io
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import EVENTS,parse_exit_csv
from compare_nexium_guest_exit_cohort import compare_sessions
from decode_nexium_guest_trace_frame import encode_fixture,synthetic_image


def fixture(index:int, *, raw_original:bool=True):
    data=[]
    shift=index*50
    for serial,scene in enumerate((2,1,2,1),start=1):
        for kind in (1,2,3,4,5):
            data.append((kind,scene,serial,serial*1000000+kind*1000+shift))
    png=synthetic_image(encode_fixture(data))
    p=io.BytesIO()
    png.save(p,format="PNG")
    first=5000000+index*100
    times=[first,first+300+index,first+1500+index*10,
           first+2100+index*20,first+2600+index*30]
    raw=("event,guest_monotonic_ns\n"+"".join(
        f"{name},{val}\n" for name,val in zip(EVENTS,times))).encode("ascii")
    receipt=parse_exit_csv(raw)
    receipt["guest_sd_receipt_observed"]=True
    receipt["guest_csv_path"]="sdmc/switch/vandal-hearts-remake/audio-exit-timeline-000.csv"
    return (39137949186+index,p.getvalue(),receipt,
            raw if raw_original else None,None)


class GuestExitCohortSynthetic(unittest.TestCase):
    def test_two_independent_guest_exit_timelines(self):
        r=compare_sessions([fixture(0),fixture(1)])
        self.assertEqual(r["run_count"],2)
        self.assertTrue(r["distinct_optical_original_png_sha256"])
        self.assertTrue(r["distinct_exit_receipt_sha256"])
        self.assertTrue(r["all_original_guest_csv_bytes_reaudited"])
        self.assertEqual(
            r["per_milestone_duration_bounds"]["plus_to_stop_request_ns"]
            ["range_ns"],1)
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_archive_without_raw_csv_is_explicitly_report_only(self):
        r=compare_sessions([fixture(0,raw_original=False),fixture(1)])
        self.assertFalse(r["all_original_guest_csv_bytes_reaudited"])
        self.assertFalse(r["source_bound_rows"][0]["original_guest_csv_bytes_reverified"])

    def test_changed_guest_original_csv_rejected(self):
        second=list(fixture(1))
        second[3]=second[3].replace(b"stop_requested",b"STOP_REQUESTED")
        with self.assertRaises(TraceError):
            compare_sessions([fixture(0),tuple(second)])

    def test_old_parsed_guest_receipt_tampering_rejected(self):
        second=list(fixture(1))
        receipt=copy.deepcopy(second[2])
        receipt["guest_monotonic_timestamps_ns"]["worker_joined"]+=100
        second[2]=receipt
        with self.assertRaises(TraceError):
            compare_sessions([fixture(0),tuple(second)])

    def test_optical_png_duplicate_is_not_an_independent_run(self):
        a=fixture(0)
        second=list(fixture(1))
        second[1]=a[1]
        with self.assertRaises(TraceError):
            compare_sessions([a,tuple(second)])

    def test_duplicate_workflow_id_rejected(self):
        second=list(fixture(1))
        second[0]=fixture(0)[0]
        with self.assertRaises(TraceError):
            compare_sessions([fixture(0),tuple(second)])

    def test_reused_guest_exit_csv_rejected(self):
        second=list(fixture(1))
        other=fixture(0)
        second[2]=other[2]
        second[3]=other[3]
        with self.assertRaises(TraceError):
            compare_sessions([other,tuple(second)])

    def test_guest_plus_before_optical_scene_fails(self):
        second=list(fixture(1))
        first=3900000
        raw=("event,guest_monotonic_ns\n"+"".join(
            f"{e},{v}\n" for e,v in zip(EVENTS,
                (first,first+200,first+400,first+600,first+800)))).encode()
        rec=parse_exit_csv(raw)
        rec["guest_sd_receipt_observed"]=True
        second[2]=rec
        second[3]=raw
        with self.assertRaises(TraceError):
            compare_sessions([fixture(0),tuple(second)])

    def test_stage308_comparison_requires_matching_original_receipt(self):
        a=fixture(0)
        b=list(fixture(1))
        b[4]={"result":"GUEST_OPTICAL_SCENES_PRECEDE_VERIFIED_GUEST_EXIT"}
        with self.assertRaises(TraceError):
            compare_sessions([a,tuple(b)])

    def test_unobserved_guest_receipt_rejected(self):
        b=list(fixture(1))
        b[2]={"result":"NOT_OBSERVED_GUEST_SD_TRANSPORT",
              "guest_sd_receipt_observed":False}
        with self.assertRaises(TraceError):
            compare_sessions([fixture(0),tuple(b)])

    def test_determinism_and_no_audible_claims(self):
        samples=[fixture(0),fixture(1)]
        a=compare_sessions(samples)
        self.assertEqual(a,compare_sessions(samples))
        self.assertTrue(a["host_pcm_and_guest_monotonic_clocks_not_calibrated"])
        self.assertTrue(a["guest_shutdown_is_not_audible_dropout_proof"])
        self.assertFalse(a["original_soundtrack_verified"])


if __name__=="__main__":
    unittest.main()
