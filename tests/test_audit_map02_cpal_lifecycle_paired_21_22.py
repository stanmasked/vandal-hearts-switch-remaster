"""ROM-free adversarial tests for actual-new-ELF 21/22 lifecycle comparison."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_lifecycle_paired_21_22 import (
    HOST_SHA,NRO_SHA,compare,classify,SCHEMA
)


def trial(h):
    positive=h==22
    return {
        "hint_ms":h,
        "compiled_host_sha256":HOST_SHA,
        "generated_research_nro_sha256":NRO_SHA,
        "actual_raw_png_pcm_cpal_evidence_redecoded":True,
        "cpal_input_window_proven":True,
        "guest_prejoin_stage":"CLEANUP_COMPLETED" if positive else "ENTERED_PLAYBUFFER",
        "prejoin_audout_entries":459 if positive else 1,
        "prejoin_audout_returns":459 if positive else 0,
        "guest_final_optical_result":"GUEST_PRESUBMIT_PCM_PAGES_MATCHED"
            if positive else "GUEST_PRESUBMIT_UNVERIFIED",
        "guest_final_optical_page_count":8 if positive else 0,
        "actual_nonzero_pcm16_samples":510838 if positive else 0,
        "cpal_entries_after_input":2244 if positive else 0,
        "cpal_returns_after_input":2244 if positive else 0,
        "cpal_error_callbacks_after_input":36 if positive else 0,
        "cpal_lifecycle_final_state":3,
        "cpal_lifecycle_final_name":"STREAM_PLAY_RETURNED_OK",
        "audioout_appends_after_input":261 if positive else 0,
        "audioout_releases_after_input":262 if positive else 0,
    }


class NewHostPairTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b=trial(21),trial(22)
    def test_paired_observations_classified_without_causal_claim(self):
        result=compare(self.a,self.b)
        self.assertEqual(result["result"],"ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")
        self.assertEqual(result["schema"],SCHEMA)
        self.assertTrue(result["host_error_callback_invocation_does_not_alone_imply_audio_failure"])
        self.assertTrue(result["one_matched_pair_not_repeated_sampling"])
        self.assertFalse(result["physical_nintendo_switch_dac_proven"])
    def test_22ms_error_counter_can_increase_while_crc_and_pcm_pass(self):
        self.b["cpal_error_callbacks_after_input"]=99
        self.assertEqual(classify(self.b),"GUEST_COMPLETED_CRC_8_PAGES_WITH_VIRTUAL_PCM")
    def test_host_sha_mismatch_rejected(self):
        self.a["compiled_host_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"SHA-256"): compare(self.a,self.b)
    def test_nro_sha_mismatch_rejected(self):
        self.b["generated_research_nro_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"SHA-256"): compare(self.a,self.b)
    def test_missing_reparsed_lifecycle_rejected(self):
        self.a["cpal_input_window_proven"]=False
        with self.assertRaisesRegex(ValueError,"evidence missing"): compare(self.a,self.b)
    def test_negative_error_count_rejected(self):
        self.b["cpal_error_callbacks_after_input"]=-1
        with self.assertRaisesRegex(ValueError,"error callback"): compare(self.a,self.b)
    def test_prejoin_return_not_pending(self):
        self.a["prejoin_audout_returns"]=1
        self.assertEqual(classify(self.a),"OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")
    def test_21ms_virtual_pcm_progress_changes_classification(self):
        self.a["actual_nonzero_pcm16_samples"]=1
        self.assertEqual(classify(self.a),"OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")
    def test_21ms_positive_lifecycle_cpal_callback_changes_classification(self):
        self.a["cpal_entries_after_input"]=1
        self.assertEqual(classify(self.a),"OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")
    def test_22ms_zero_cpal_callbacks_not_success(self):
        self.b["cpal_entries_after_input"]=0
        self.assertEqual(classify(self.b),"OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")
    def test_22ms_final_crc_missing_not_success(self):
        self.b["guest_final_optical_page_count"]=0
        self.assertEqual(classify(self.b),"OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")
    def test_22ms_no_pcm_not_success(self):
        self.b["actual_nonzero_pcm16_samples"]=0
        self.assertEqual(classify(self.b),"OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")
    def test_unexpected_21ms_success_is_reported_mixed_not_21ms_stall(self):
        self.a=dict(trial(22),hint_ms=21)
        self.assertEqual(compare(self.a,self.b)["result"],
                         "TWO_COMPLETE_ARCHIVES_SHOW_DIFFERENT_OR_MIXED_RESULTS")
    def test_wrong_hint_pair_rejected(self):
        self.a["hint_ms"]=22
        with self.assertRaisesRegex(ValueError,"expected requested"): compare(self.a,self.b)

if __name__=="__main__":
    unittest.main()
