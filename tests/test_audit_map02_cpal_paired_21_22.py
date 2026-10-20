"""Falsify Stage282 strict one-pair conclusion using ROM-free fake receipts."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_paired_21_22 import compare, HOST_SHA, NRO_SHA


def synthetic(hint):
    positive=hint==22
    return {
        "hint_ms":hint,
        "compiled_host_sha256":HOST_SHA,
        "generated_research_nro_sha256":NRO_SHA,
        "actual_raw_png_pcm_cpal_evidence_redecoded":True,
        "guest_prejoin_stage":"CLEANUP_COMPLETED" if positive else "ENTERED_PLAYBUFFER",
        "prejoin_audout_entries":487 if positive else 1,
        "prejoin_audout_returns":487 if positive else 0,
        "guest_final_optical_result":(
            "GUEST_PRESUBMIT_PCM_PAGES_MATCHED" if positive else
            "GUEST_PRESUBMIT_UNVERIFIED"),
        "guest_final_optical_page_count":8 if positive else 0,
        "actual_nonzero_pcm16_samples":541820 if positive else 0,
        "cpal_entries_after_input":2242 if positive else 0,
        "cpal_returns_after_input":2242 if positive else 0,
        "audioout_appends_after_input":277 if positive else 0,
        "audioout_releases_after_input":278 if positive else 0,
    }


class PairedProofTests(unittest.TestCase):
    def setUp(self):
        self.a=synthetic(21)
        self.b=synthetic(22)

    def test_both_actual_evidence_contrasts_produce_bounded_one_pair_result(self):
        r=compare(self.a,self.b)
        self.assertEqual(r["result"],"SINGLE_MATCHED_HOST_NRO_21_22_CONTRAST_VERIFIED")
        self.assertFalse(r["guest_21ms_strict_crc_succeeded"])
        self.assertTrue(r["guest_22ms_strict_8_pages_crc_succeeded"])
        self.assertTrue(r["single_pair_does_not_establish_repeatability"])
        self.assertFalse(r["cpal_root_cause_or_permanent_guest_deadlock_proven"])
        self.assertFalse(r["physical_switch_dac_verified"])

    def test_wrong_guest_nro_sha_rejected(self):
        self.a["generated_research_nro_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"Host/NRO"):
            compare(self.a,self.b)

    def test_wrong_host_sha_rejected(self):
        self.b["compiled_host_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"Host/NRO"):
            compare(self.a,self.b)

    def test_nonredecoded_png_cannot_claim_contrast(self):
        self.b["actual_raw_png_pcm_cpal_evidence_redecoded"]=False
        with self.assertRaisesRegex(ValueError,"Unverified"):
            compare(self.a,self.b)

    def test_21ms_guest_became_audio_success_cannot_claim_old_stall(self):
        self.a["guest_final_optical_result"]="GUEST_PRESUBMIT_PCM_PAGES_MATCHED"
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_21ms_callback_progress_cannot_be_reported_as_stopped(self):
        self.a["cpal_entries_after_input"]=100
        self.a["cpal_returns_after_input"]=100
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_21ms_kernel_audioout_progress_cannot_be_reported_as_stopped(self):
        self.a["audioout_appends_after_input"]=1
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_21ms_nonzero_host_pcm_cannot_claim_silent_sink(self):
        self.a["actual_nonzero_pcm16_samples"]=1
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_21ms_prejoin_completed_cannot_claim_pending_call(self):
        self.a["prejoin_audout_returns"]=1
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_22ms_host_callback_missing_cannot_claim_success(self):
        self.b["cpal_entries_after_input"]=0
        self.b["cpal_returns_after_input"]=0
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_22ms_zero_raw_pcm_cannot_claim_virtual_output(self):
        self.b["actual_nonzero_pcm16_samples"]=0
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_22ms_missing_guest_crc_pages_cannot_claim_success(self):
        self.b["guest_final_optical_page_count"]=0
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_22ms_guest_release_missing_cannot_claim_success(self):
        self.b["audioout_releases_after_input"]=0
        with self.assertRaisesRegex(ValueError,"strict"):
            compare(self.a,self.b)

    def test_wrong_hints_rejected(self):
        self.a["hint_ms"]=22
        with self.assertRaisesRegex(ValueError,"expected 21 vs 22"):
            compare(self.a,self.b)


if __name__=="__main__":
    unittest.main()
