#!/usr/bin/env python3
"""Stage360 source-byte and prior receipt mutation tests (synthetic)."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_exit_probe_context_stage360 import parse_source,ExitTimelineError
from audit_nexium_guest_last_buffer_return import SCHEMA as TAIL_SCHEMA, COMPLETE
from audit_nexium_guest_tail_reason_stage351 import SCHEMA as REASON_SCHEMA, VERIFIED
FIELDS=(
    "software_exit_probe_context_only","tail_observed",
    "tail_begin_guest_ns","tail_end_guest_ns","tail_elapsed_ns",
    "normal_submit_attempts_at_tail","last_pre_submit_probe_observed",
    "last_pre_submit_probe_attempt","last_pre_submit_probe_queue_status",
    "last_pre_submit_probe_queue_count","last_pre_submit_probe_age_ns",
    "last_pre_submit_probe_dropped_count","stage351_tail_reason_code"
)
def fixtures(code=4):
    nums=dict(zip(FIELDS,(1,1,200,212,12,25,1,17,1,2,30,0,code)))
    raw=lambda n:b"scope,value\n"+b"".join(
        f"{k},{n[k]}\n".encode() for k in FIELDS)
    a={
        "schema":TAIL_SCHEMA,"result":COMPLETE,
        "original_guest_page_witness_observed":True,
        "tail_bounded_attempt_observed":True,"tail_release_confirmed":code==7,
        "tail_attempt_guest_ns":200,
        "tail_success_return_guest_ns":212 if code==7 else None,
        "hardware_Nintendo_Switch_audio_tested":False
    }
    b={
        "schema":REASON_SCHEMA,"result":VERIFIED,
        "reason_code":code,
        "prior_stage313_and_stage348_original_bytes_reaudited":True,
        "physical_Nintendo_Switch_audio_tested":False
    }
    return nums,raw,a,b
class Stage360Tests(unittest.TestCase):
    def test_last_probe_old_and_not_shutdown_depth(self):
        n,raw,a,b=fixtures()
        x=parse_source(raw(n),a,b)
        self.assertTrue(x["last_pre_submit_probe_observed"])
        self.assertEqual(x["last_pre_submit_probe_age_ns"],30)
        self.assertFalse(x["direct_exit_time_queue_depth_observed"])
        self.assertFalse(x["scheduler_latency_measured"])
    def test_successful_exit_clock_alignment(self):
        n,raw,a,b=fixtures(7)
        self.assertEqual(parse_source(raw(n),a,b)["stage351_tail_reason_code"],7)
    def test_failed_probe_not_interpreted_as_empty(self):
        n,raw,a,b=fixtures()
        n["last_pre_submit_probe_queue_status"]=0
        n["last_pre_submit_probe_queue_count"]=0
        x=parse_source(raw(n),a,b)
        self.assertIsNone(x["last_pre_submit_probe_queue_count"])
        self.assertFalse(x["last_pre_submit_probe_query_succeeded"])
    def test_missing_probe_retains_unknown(self):
        n,raw,a,b=fixtures()
        for key in ("last_pre_submit_probe_observed",
                    "last_pre_submit_probe_attempt",
                    "last_pre_submit_probe_queue_status",
                    "last_pre_submit_probe_queue_count",
                    "last_pre_submit_probe_age_ns"):n[key]=0
        x=parse_source(raw(n),a,b)
        self.assertIsNone(x["last_pre_submit_probe_age_ns"])
    def test_reject_future_probe_age(self):
        n,raw,a,b=fixtures()
        n["last_pre_submit_probe_age_ns"]=201
        with self.assertRaises(ExitTimelineError):parse_source(raw(n),a,b)
    def test_reject_wrong_elapsed(self):
        n,raw,a,b=fixtures()
        n["tail_elapsed_ns"]=11
        with self.assertRaises(ExitTimelineError):parse_source(raw(n),a,b)
    def test_reject_modified_original_tail_clock(self):
        n,raw,a,b=fixtures()
        a["tail_attempt_guest_ns"]=201
        with self.assertRaises(ExitTimelineError):parse_source(raw(n),a,b)
    def test_reject_false_stage351_reason(self):
        n,raw,a,b=fixtures()
        b["reason_code"]=7
        with self.assertRaises(ExitTimelineError):parse_source(raw(n),a,b)
    def test_reject_spurious_present_probe_count(self):
        n,raw,a,b=fixtures()
        n["last_pre_submit_probe_observed"]=0
        with self.assertRaises(ExitTimelineError):parse_source(raw(n),a,b)
    def test_reject_missing_source_rows(self):
        n,raw,a,b=fixtures()
        with self.assertRaises(ExitTimelineError):
            parse_source(raw(n).replace(b"tail_elapsed_ns,12\n",b""),a,b)
    def test_reject_noncanonical_integer(self):
        n,raw,a,b=fixtures()
        with self.assertRaises(ExitTimelineError):
            parse_source(raw(n).replace(b"tail_elapsed_ns,12\n",b"tail_elapsed_ns,012\n"),a,b)
    def test_stage360_guest_export_does_not_redeclare_existing_probe_path(self):
        from re import findall
        original=(Path(__file__).resolve().parents[1]/"source"/"main.c").read_text()
        # Both exporters live in the SAME main() scope. Distinct names
        # are necessary for the real libnx NRO, not just host C helpers.
        self.assertEqual(len(findall(r"\bchar probe_path\[",original)),1)
        self.assertEqual(len(findall(r"\bchar exit_probe_path\[",original)),1)
        stage360=original[original.index("/* Stage360: an independent post-join guest source"):
                          original.index("char scene_path[VH_SCENE_TRACE_EXPORT_PATH_CAP]")]
        self.assertNotIn("char probe_path[",stage360)
        self.assertIn("audio-exit-probe-context-%03u.csv",stage360)

if __name__=="__main__":
    unittest.main()
