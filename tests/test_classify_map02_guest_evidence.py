"""ROM-free tests of multi-source MAP02 guest evidence: no false deadlock."""
import importlib.util
import sys
import unittest
from pathlib import Path

src=Path(__file__).resolve().parents[1]/"tools/classify_map02_guest_evidence.py"
spec=importlib.util.spec_from_file_location("vh_conjunction",src)
e=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=e
spec.loader.exec_module(e)

def guest():
    return {"schema":e.OPTICAL,"result":"GUEST_PRESUBMIT_PCM_PAGES_MATCHED",
            "observed_pages":8,"mismatches":0,
            "actual_audout_call_observed":True,
            "pages":[{"index":i,"descriptor_released_returns":1}
                     for i in range(8)]}

def monitor(nonzero):
    return {"schema":e.MONITOR,"valid_pcm16le_stereo":True,
            "stereo_frames":20000,"nonzero_pcm16_samples":nonzero,
            "all_zero_monitor_pcm":not bool(nonzero)}

def raster(before=27722,after=0):
    return {"schema":e.RASTER,
            "before_to_final":{"changed_rgb_pixels":before},
            "final_to_late":{"changed_rgb_pixels":after},
            "audout_call_deadlock_proven":False}

class EvidenceTests(unittest.TestCase):
    def test_real_21ms_shape_is_observation_not_deadlock(self):
        r=e.classify({"schema":e.OPTICAL,"result":"GUEST_PRESUBMIT_UNVERIFIED"},
                     monitor(0),raster())
        self.assertEqual(r["classification"],"OPTICAL_MISSING_ZERO_VIRTUAL_SINK")
        self.assertEqual(r["guest_raster_before_final_changed_pixels"],27722)
        self.assertEqual(r["guest_raster_final_late_changed_pixels"],0)
        self.assertFalse(r["audout_playbuffer_stall_proven"])
        self.assertFalse(r["guest_join_deadlock_proven"])

    def test_valid_guest_and_exact_pages(self):
        sink={"schema":e.SINK,"per_page_matches":[1]*8,
              "result":"NO_EXACT_EIGHT_PAGE_SINK_MATCH"}
        r=e.classify(guest(),monitor(200),raster(492900,0),sink)
        self.assertEqual(r["classification"],
                         "EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK")
        self.assertTrue(r["guest_8page_receipt_valid"])
        self.assertTrue(r["exact_8_individual_sink_page_matches"])
        self.assertFalse(r["physical_switch_dac_samples_proven"])

    def test_nonzero_sink_missing_receipt_does_not_prove_pages(self):
        r=e.classify(None,monitor(100),raster())
        self.assertEqual(r["classification"],"OPTICAL_MISSING_NONZERO_VIRTUAL_SINK")
        self.assertIsNone(r["exact_8_individual_sink_page_matches"])

    def test_valid_optical_all_zero_requires_discrepancy(self):
        r=e.classify(guest(),monitor(0))
        self.assertEqual(r["classification"],
                         "OPTICAL_RECEIPT_BUT_ZERO_MONITOR_CONTRADICTION")

    def test_no_monitor_is_unverified_even_if_optical_exists(self):
        r=e.classify(guest(),None)
        self.assertEqual(r["classification"],"INSUFFICIENT_VIRTUAL_MONITOR_EVIDENCE")

    def test_malformed_optical_cannot_forge_success(self):
        g=guest()
        g["pages"][3]=None
        r=e.classify(g,monitor(123))
        self.assertEqual(r["classification"],"OPTICAL_MISSING_NONZERO_VIRTUAL_SINK")
        self.assertFalse(r["guest_8page_receipt_valid"])

    def test_inconsistent_monitor_cannot_forge_nonzero_output(self):
        wrong=monitor(12)
        wrong["all_zero_monitor_pcm"]=True
        r=e.classify(guest(),wrong)
        self.assertEqual(r["classification"],"INSUFFICIENT_VIRTUAL_MONITOR_EVIDENCE")

    def test_raster_only_input_stays_inconclusive(self):
        r=e.classify(None,None,raster(0,0),pulse={
            "schema":e.PULSE,"unique_target_each_snapshot":True})
        self.assertEqual(r["classification"],"INSUFFICIENT_VIRTUAL_MONITOR_EVIDENCE")
        self.assertTrue(r["unique_48k_stereo_pulse_client"])
        self.assertFalse(r["guest_join_deadlock_proven"])

if __name__=="__main__":
    unittest.main()
