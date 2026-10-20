"""Generated-only Stage283 six-run acceptance and falsification tests; no ROM."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_six_real_trials import (
    aggregate,describe_behavior,HOST,NRO,SCHEMA,
)

RUN_ID=1234567
ATTEMPT=1
PENDING="GUEST_AUDOUT_PENDING_WITH_NO_POSTINPUT_CPAL_OR_VIRTUAL_PCM"
COMPLETE="GUEST_COMPLETED_8_CRC_PAGES_WITH_REAL_VIRTUAL_PCM"
OTHER="OTHER_FULLY_CAPTURED_GUEST_AUDIO_BEHAVIOR"


def sample(hint,repeat):
    yes=hint==22
    record={
        "hint_ms":hint,"repeat":repeat,
        "run_id":RUN_ID,"run_attempt":ATTEMPT,
        "identical_compiled_host_sha256":HOST,
        "identical_generated_nro_sha256":NRO,
        "raw_guest_images_and_host_csv_and_pcm_redecoded":True,
        "prejoin_stage":"CLEANUP_COMPLETED" if yes else "ENTERED_PLAYBUFFER",
        "prejoin_guest_audout_entries":487 if yes else 1,
        "prejoin_guest_audout_returns":487 if yes else 0,
        "strict_guest_result":(
            "GUEST_PRESUBMIT_PCM_PAGES_MATCHED" if yes else
            "GUEST_PRESUBMIT_UNVERIFIED"),
        "strict_guest_pages":8 if yes else 0,
        "cpal_callback_entries":2242 if yes else 0,
        "cpal_callback_returns":2242 if yes else 0,
        "audioout_appends":277 if yes else 0,
        "audioout_releases":278 if yes else 0,
        "nonzero_virtual_pcm16":541820 if yes else 0,
    }
    record["observed_behavior"]=describe_behavior(record)
    return record


def six():
    return [sample(h,i) for h in (21,22) for i in (1,2,3)]


class SixRealTrialClassificationTests(unittest.TestCase):
    def test_six_compatible_synthetic_trials_classify_repeated_contrast(self):
        r=aggregate(six(),RUN_ID,ATTEMPT)
        self.assertEqual(r["schema"],SCHEMA)
        self.assertEqual(r["result"],
                         "SIX_INDEPENDENT_GUEST_RUNNERS_REPRODUCED_21_22_CONTRAST")
        self.assertTrue(r["repeated_contrast_observed"])
        self.assertFalse(r["permanent_audout_deadlock_or_cpal_root_cause_proven"])
        self.assertFalse(r["physical_nintendo_switch_audio_proven"])

    def test_one_21ms_success_is_not_silently_called_repeated_stall(self):
        rows=six()
        rows[0]=sample(22,1)
        rows[0]["hint_ms"]=21
        rows[0]["observed_behavior"]=describe_behavior(rows[0])
        r=aggregate(rows,RUN_ID,ATTEMPT)
        self.assertEqual(r["result"],
                         "SIX_COMPLETE_GUEST_RUNNERS_SHOW_MIXED_OR_DIFFERENT_BEHAVIOR")
        self.assertFalse(r["repeated_contrast_observed"])

    def test_one_22ms_failure_is_reported_as_mixed_evidence(self):
        rows=six()
        rows[-1]=sample(21,3)
        rows[-1]["hint_ms"]=22
        rows[-1]["observed_behavior"]=describe_behavior(rows[-1])
        self.assertFalse(aggregate(rows,RUN_ID,ATTEMPT)["repeated_contrast_observed"])

    def test_missing_sixth_job_rejected(self):
        with self.assertRaisesRegex(ValueError,"Six distinct"):
            aggregate(six()[:-1],RUN_ID,ATTEMPT)

    def test_duplicate_repeat_cannot_forge_six_independent_guests(self):
        rows=six()
        rows[1]["repeat"]=1
        with self.assertRaisesRegex(ValueError,"repeat distribution"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_binary_sha_change_in_one_matrix_trial_rejected(self):
        rows=six()
        rows[4]["identical_compiled_host_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"source SHA"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_nro_sha_change_rejected(self):
        rows=six()
        rows[0]["identical_generated_nro_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"source SHA"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_run_id_mismatch_rejected(self):
        rows=six()
        rows[3]["run_id"]=RUN_ID+1
        with self.assertRaisesRegex(ValueError,"Run ID"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_raw_evidence_false_rejected(self):
        rows=six()
        rows[4]["raw_guest_images_and_host_csv_and_pcm_redecoded"]=False
        with self.assertRaisesRegex(ValueError,"verification"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_21ms_pending_snapshot_not_claimed_when_guest_returned(self):
        row=sample(21,1)
        row["prejoin_guest_audout_returns"]=1
        self.assertEqual(describe_behavior(row),OTHER)

    def test_21ms_pending_snapshot_not_claimed_after_new_cpal_callback(self):
        row=sample(21,1)
        row["cpal_callback_entries"]=1
        row["cpal_callback_returns"]=1
        self.assertEqual(describe_behavior(row),OTHER)

    def test_21ms_nonzero_virtual_pcm_invalidates_expected_silent_class(self):
        row=sample(21,1)
        row["nonzero_virtual_pcm16"]=1
        self.assertEqual(describe_behavior(row),OTHER)

    def test_22ms_missing_crc_eight_pages_invalidates_success(self):
        row=sample(22,2)
        row["strict_guest_pages"]=7
        self.assertEqual(describe_behavior(row),OTHER)

    def test_22ms_missing_cpal_return_invalidates_success(self):
        row=sample(22,2)
        row["cpal_callback_returns"]=0
        self.assertEqual(describe_behavior(row),OTHER)

    def test_22ms_missing_audioout_appends_invalidates_success(self):
        row=sample(22,2)
        row["audioout_appends"]=0
        self.assertEqual(describe_behavior(row),OTHER)

    def test_22ms_zero_virtual_pcm_invalidates_success(self):
        row=sample(22,2)
        row["nonzero_virtual_pcm16"]=0
        self.assertEqual(describe_behavior(row),OTHER)


if __name__=="__main__":
    unittest.main()
