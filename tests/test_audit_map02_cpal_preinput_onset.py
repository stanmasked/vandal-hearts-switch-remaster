"""ROM-free Stage285 bounded CPAL callback timing tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_preinput_onset import onset,aggregate,HOST,NRO

T0=1_000_000_000
INPUT=2_500_000_000
END=4_500_000_000


def rows(mode="quiet"):
    out=[]
    for i in range(20):
        now=T0+200_000_000*i
        if mode=="quiet":
            entered=returned=1
        elif mode=="live":
            entered=returned=1+8*i
        elif mode=="late":
            entered=returned=1 if now<INPUT else 1+(i-7)*4
        elif mode=="never":
            entered=returned=0
        elif mode=="early_then_still":
            entered=returned=1 if i<4 else 2
        else:
            raise ValueError("Unsupported synthetic series")
        out.append({"ns":now,"entered":entered,"returned":returned,
                    "output_frames":entered*512,"appends":0,
                    "releases":0})
    return out


def sample(hint,repeat,state):
    return {
        "hint_ms":hint,"repeat":repeat,
        "original_archive_host_sha256":HOST,
        "original_archive_nro_sha256":NRO,
        "source_png_pcm_and_cpal_reverified":True,
        "classification":state,
    }


class CpalOnsetBoundsTests(unittest.TestCase):
    def test_first_callback_before_reporter_then_quiet_for_one_second(self):
        x=onset(rows("quiet"),INPUT,END)
        self.assertEqual(x["classification"],
                         "CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT")
        self.assertEqual(x["first_sample_entered"],1)
        self.assertEqual(x["cpal_entries_after_guest_input"],0)
        self.assertEqual(x["cpal_returns_after_guest_input"],0)
        self.assertTrue(x["last_observed_preinput_callback_increase_left_censored"])
        self.assertEqual(x["lower_bound_ms_between_last_preinput_increase_and_input"],1500.0)
        self.assertTrue(x["host_callback_timing_is_interval_censored"])

    def test_real_callback_progress_during_guest_input_window(self):
        x=onset(rows("live"),INPUT,END)
        self.assertEqual(x["classification"],
                         "CALLBACKS_CONTINUED_AFTER_GUEST_INPUT")
        self.assertGreater(x["cpal_entries_after_guest_input"],0)
        self.assertGreater(x["cpal_returns_after_guest_input"],0)

    def test_one_late_callback_after_input_prevents_preinput_stop_claim(self):
        x=onset(rows("late"),INPUT,END)
        self.assertEqual(x["classification"],
                         "CALLBACKS_CONTINUED_AFTER_GUEST_INPUT")

    def test_no_callback_ever_must_not_claim_stopped_after_running(self):
        x=onset(rows("never"),INPUT,END)
        self.assertEqual(x["classification"],
                         "NO_CALLBACKS_OBSERVED_IN_INPUT_WINDOW")
        self.assertIsNone(x["last_observed_preinput_callback_increase_upper_ns"])

    def test_preinput_callback_with_short_quiet_window_must_not_claim_one_second(self):
        v=rows("early_then_still")
        input_at=2_050_000_000
        x=onset(v,input_at,END)
        self.assertEqual(x["classification"],
                         "NO_NEW_CALLBACKS_AFTER_INPUT_PREINPUT_ONSET_UNRESOLVED")
        self.assertLess(x["lower_bound_ms_between_last_preinput_increase_and_input"],1000)

    def test_missing_preinput_bound_rejected(self):
        with self.assertRaisesRegex(ValueError,"Missing pre-input"):
            onset(rows("quiet"),T0-100,END)

    def test_missing_final_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"Missing pre-input"):
            onset(rows("quiet"),INPUT,INPUT-1)

    def test_insufficient_snapshots_rejected(self):
        with self.assertRaisesRegex(ValueError,"Missing pre-input"):
            onset(rows("quiet")[:5],INPUT,END)

    def test_six_independent_cases_allow_observed_preinput_conclusion(self):
        records=[sample(h,i,(
            "CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT"
            if h==21 else "CALLBACKS_CONTINUED_AFTER_GUEST_INPUT"))
            for h in (21,22) for i in (1,2,3)]
        report=aggregate(records)
        self.assertTrue(report["observed_21ms_stopped_at_least_1s_before_input_in_all_three"])
        self.assertTrue(report["observed_22ms_callback_progress_after_input_in_all_three"])
        self.assertFalse(report["cpal_audio_backend_cause_proven"])
        self.assertFalse(report["controller_input_caused_stream_stop_proven"])
        self.assertFalse(report["permanent_audout_deadlock_proven"])

    def test_single_21ms_preinput_gap_shorter_yields_false_not_a_fake_success(self):
        records=[sample(h,i,(
            "CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT"
            if h==21 else "CALLBACKS_CONTINUED_AFTER_GUEST_INPUT"))
            for h in (21,22) for i in (1,2,3)]
        records[1]["classification"]="NO_NEW_CALLBACKS_AFTER_INPUT_PREINPUT_ONSET_UNRESOLVED"
        self.assertFalse(aggregate(records)[
            "observed_21ms_stopped_at_least_1s_before_input_in_all_three"])

    def test_single_22ms_stall_does_not_claim_all_live(self):
        records=[sample(h,i,(
            "CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT"
            if h==21 else "CALLBACKS_CONTINUED_AFTER_GUEST_INPUT"))
            for h in (21,22) for i in (1,2,3)]
        records[-1]["classification"]="NO_NEW_CALLBACKS_AFTER_INPUT_PREINPUT_ONSET_UNRESOLVED"
        self.assertFalse(aggregate(records)[
            "observed_22ms_callback_progress_after_input_in_all_three"])

    def test_less_than_six_archives_rejected(self):
        rows=[sample(h,i,"CALLBACKS_CONTINUED_AFTER_GUEST_INPUT")
              for h in (21,22) for i in (1,2,3)]
        with self.assertRaisesRegex(ValueError,"six separately"):
            aggregate(rows[:-1])

    def test_duplicate_hint_repeat_rejected(self):
        rows=[sample(h,i,"CALLBACKS_CONTINUED_AFTER_GUEST_INPUT")
              for h in (21,22) for i in (1,2,3)]
        rows[1]["repeat"]=1
        with self.assertRaisesRegex(ValueError,"six separately"):
            aggregate(rows)

    def test_invalid_compiled_host_sha_rejected(self):
        rows=[sample(h,i,"CALLBACKS_CONTINUED_AFTER_GUEST_INPUT")
              for h in (21,22) for i in (1,2,3)]
        rows[4]["original_archive_host_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"binary source"):
            aggregate(rows)

    def test_unverified_raw_optical_or_pcm_rejected(self):
        rows=[sample(h,i,"CALLBACKS_CONTINUED_AFTER_GUEST_INPUT")
              for h in (21,22) for i in (1,2,3)]
        rows[0]["source_png_pcm_and_cpal_reverified"]=False
        with self.assertRaisesRegex(ValueError,"binary source"):
            aggregate(rows)


if __name__=="__main__":
    unittest.main()
