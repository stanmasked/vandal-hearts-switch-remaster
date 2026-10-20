"""Pure synthetic guard tests; zero original ROM or PCM assets."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"tools/validate_presubmit_sink_eight_pages.py"
spec=importlib.util.spec_from_file_location("eight_guard",p)
guard=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=guard
spec.loader.exec_module(guard)

def fixture():
    gaps=[467,979,467,466,467,467,467]
    frames=[557,557,557,558,557,557,557,558]
    starts=[3456]
    for i,gap in enumerate(gaps):
        starts.append(starts[-1]+frames[i]+gap)
    a={"schema":"vh-map02-presubmit-sink-audit/v1",
       "per_page_matches":[1]*8,
       "unique_page_frame_offsets":starts,
       "all_eight_pages_found_once":True,
       "unique_page_order_preserved":True,
       "inter_page_gap_frames":gaps,
       "inter_page_gap_nonzero_pcm_bytes":[0]*7,
       "all_nonnegative_inter_page_gaps_digital_silence":True,
       "capture_frames":200000}
    b={"schema":"vh-map02-latency-monitor-health/v1",
       "all_zero_monitor_pcm":False,"nonzero_pcm16_samples":50000,
       "valid_pcm16le_stereo":True,"stereo_frames":200000}
    return a,b

class EightPageTests(unittest.TestCase):
    def test_seven_zero_filled_gaps_are_allowed(self):
        sink,health=fixture()
        result=guard.assess(sink,health)
        self.assertEqual(result["unique_verified_page_count"],8)
        self.assertFalse(result["contiguous_eight_page_stream_proven"])
        self.assertFalse(result["actual_switch_speaker_dac_proven"])

    def test_single_missing_page_fails_even_with_valid_guest_receipt(self):
        sink,health=fixture()
        for index in (2,6):
            bad=copy.deepcopy(sink)
            bad["per_page_matches"][index]=0
            with self.assertRaisesRegex(ValueError,"uniquely"):
                guard.assess(bad,health)

    def test_duplicate_and_reordered_page_fail(self):
        sink,health=fixture()
        sink["per_page_matches"][0]=2
        with self.assertRaisesRegex(ValueError,"uniquely"):
            guard.assess(sink,health)
        sink,health=fixture()
        sink["unique_page_frame_offsets"][0]=99999
        with self.assertRaisesRegex(ValueError,"order"):
            guard.assess(sink,health)

    def test_nonzero_pcm_in_gap_fails(self):
        sink,health=fixture()
        sink["inter_page_gap_nonzero_pcm_bytes"][3]=1
        with self.assertRaisesRegex(ValueError,"nonzero"):
            guard.assess(sink,health)

    def test_silent_or_truncated_monitor_fails(self):
        sink,health=fixture()
        health["all_zero_monitor_pcm"]=True
        health["nonzero_pcm16_samples"]=0
        with self.assertRaisesRegex(ValueError,"silent"):
            guard.assess(sink,health)
        sink,health=fixture()
        health["stereo_frames"]-=1
        with self.assertRaisesRegex(ValueError,"counts disagree"):
            guard.assess(sink,health)

    def test_negative_gap_rejected(self):
        sink,health=fixture()
        sink["inter_page_gap_frames"][0]=-1
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            guard.assess(sink,health)

if __name__=="__main__":
    unittest.main()
