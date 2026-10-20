"""Stage286 synthetic falsification: no game ROM, CPU backend or PCM files."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_host_only_cpal import HOST_SHA,aggregate

RUN_ID=321654
ATTEMPT=1


def record(hint,repeat):
    return {
        "hint_ms":hint,"repeat":repeat,
        "job_run_id":RUN_ID,"job_attempt":ATTEMPT,
        "same_compiled_host_sha256":HOST_SHA,
        "no_guest_nro_or_game_input":True,
        "actual_host_cpal_source_timeline_verified":True,
        "host_only_behavior":(
            "HOST_ONLY_NO_NEW_CPAL_CALLBACKS_IN_OBSERVATION_WINDOW"
            if hint==21 else
            "HOST_ONLY_CPAL_CALLBACKS_ENTERED_AND_RETURNED"),
    }


def set4():
    return [record(h,i) for h in (21,22) for i in (1,2)]


class HostOnlyEvidenceTests(unittest.TestCase):
    def test_exact_host_only_21_22_contrast_classifies_as_repeated(self):
        r=aggregate(set4(),RUN_ID,ATTEMPT)
        self.assertEqual(r["result"],
                         "FOUR_REAL_HOST_ONLY_RUNNERS_REPRODUCED_PULSE_HINT_CPAL_CONTRAST")
        self.assertTrue(r["host_only_requested_hint_contrast_repeated"])
        self.assertFalse(r["specific_pulse_alsa_cpal_causal_root_proven"])
        self.assertFalse(r["guest_audioout_permanent_deadlock_proven"])
        self.assertTrue(r["no_research_nro_or_original_game_rom_used"])

    def test_unexpected_21ms_callback_progress_not_silently_hid(self):
        a=set4()
        a[1]["host_only_behavior"]="HOST_ONLY_CPAL_CALLBACKS_ENTERED_AND_RETURNED"
        x=aggregate(a,RUN_ID,ATTEMPT)
        self.assertFalse(x["host_only_requested_hint_contrast_repeated"])
        self.assertEqual(x["result"],
                         "FOUR_REAL_HOST_ONLY_RUNNERS_SHOW_OTHER_OR_MIXED_CPAL_BEHAVIOR")

    def test_unexpected_22ms_stall_reported_as_mixed_behavior(self):
        a=set4()
        a[-1]["host_only_behavior"]="HOST_ONLY_NO_NEW_CPAL_CALLBACKS_IN_OBSERVATION_WINDOW"
        self.assertFalse(aggregate(a,RUN_ID,ATTEMPT)[
            "host_only_requested_hint_contrast_repeated"])

    def test_missing_fourth_host_runner_rejected(self):
        with self.assertRaisesRegex(ValueError,"four independent"):
            aggregate(set4()[:-1],RUN_ID,ATTEMPT)

    def test_duplicate_host_runner_rejected(self):
        rows=set4()
        rows[1]["repeat"]=1
        with self.assertRaisesRegex(ValueError,"four independent"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_changed_host_sha_rejected(self):
        rows=set4()
        rows[2]["same_compiled_host_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"provenance"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_wrong_run_or_attempt_rejected(self):
        rows=set4()
        rows[0]["job_attempt"]=2
        with self.assertRaisesRegex(ValueError,"provenance"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_forged_raw_timeline_rejected(self):
        rows=set4()
        rows[3]["actual_host_cpal_source_timeline_verified"]=False
        with self.assertRaisesRegex(ValueError,"provenance"):
            aggregate(rows,RUN_ID,ATTEMPT)

    def test_guest_input_or_nro_flag_invalidates_no_rom_claim(self):
        rows=set4()
        rows[1]["no_guest_nro_or_game_input"]=False
        with self.assertRaisesRegex(ValueError,"provenance"):
            aggregate(rows,RUN_ID,ATTEMPT)


if __name__=="__main__":
    unittest.main()
