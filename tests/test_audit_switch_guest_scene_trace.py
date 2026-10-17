#!/usr/bin/env python3
"""Negative/positive tests for actual guest-event witness validation."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"tools"))
from audit_switch_guest_scene_trace import analyze,TraceError

def trace(rows, *, dropped=0):
    header="VH_AUDIO_SCENE_TRACE_BEGIN\nindex,event,serial,scene,monotonic_ns\n"
    body="".join(f"{i},{event},{serial},{scene},{time}\n"
                 for i,(event,serial,scene,time) in enumerate(rows))
    return header+body+f"VH_AUDIO_SCENE_TRACE_END,rows={len(rows)},dropped={dropped}\n"

class TestGuestSceneTrace(unittest.TestCase):
    def setUp(self):
        self.rows=[
            ("ACCEPT",0,1,100),
            ("SUBMIT_CALL",0,1,120),
            ("RELEASE_RETURN",0,1,160),
            ("INPUT",1,2,1000000000),
            ("POST",1,2,1000050000),
            ("ACCEPT",1,2,1000200000),
            ("SUBMIT_CALL",1,2,1000210000),
            ("RELEASE_RETURN",1,2,1010000000),
        ]

    def test_full_guest_internal_phase_timing(self):
        result=analyze(trace(self.rows))
        self.assertEqual(result["result"],"GUEST_INTERNAL_PHASES_OBSERVED")
        self.assertEqual(result["unmatched_serial_zero_events"],3)
        self.assertEqual(len(result["complete_scene_serials"]),1)
        self.assertEqual(result["complete_scene_serials"][0]["observed_input_to_cue_accepted_ms"],0.2)
        self.assertEqual(result["complete_scene_serials"][0]["observed_input_to_page_return_ms"],10)
        self.assertIsNone(result["hardware_input_to_audio_latency_ms"])
        self.assertFalse(result["dac_output_timestamp_confirmed"])

    def test_no_guest_stdout_is_unobserved_not_passed(self):
        self.assertEqual(analyze("NeXium host log with no guest trace")["result"],
                         "GUEST_TRACE_NOT_OBSERVED")

    def test_nonzero_drops_make_partial(self):
        r=analyze(trace(self.rows,dropped=2))
        self.assertEqual(r["result"],"GUEST_TRACE_PARTIAL")
        self.assertEqual(r["dropped"],2)

    def test_bad_order_and_scene_relabel_rejected(self):
        bad=list(self.rows)
        bad[6]=("SUBMIT_CALL",1,2,1000100000)
        with self.assertRaises(TraceError):
            analyze(trace(bad))
        bad=list(self.rows)
        bad[4]=("POST",1,1,1000050000)
        with self.assertRaises(TraceError):
            analyze(trace(bad))

    def test_duplicate_invalid_footer_and_missing_row_rejected(self):
        with self.assertRaises(TraceError):
            analyze(trace(self.rows).replace("VH_AUDIO_SCENE_TRACE_BEGIN",
                                            "VH_AUDIO_SCENE_TRACE_BEGIN\nVH_AUDIO_SCENE_TRACE_BEGIN"))
        with self.assertRaises(TraceError):
            analyze(trace(self.rows).replace("rows=8","rows=9"))
        with self.assertRaises(TraceError):
            analyze(trace(self.rows).replace("4,POST,1","4,OTHER,1"))
        with self.assertRaises(TraceError):
            analyze(trace(self.rows).replace("dropped=0","dropped=-1"))

if __name__=="__main__":
    unittest.main()
