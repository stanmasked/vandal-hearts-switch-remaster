"""Generated-only checks for Stage294 new source path and guest classification."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_filelogger_guest_stage294 import (
    classify,SCHEMA,HOST_SHA,NRO_SHA,real_audit
)
from audit_map02_cpal_error_messages_stage293 import scan_host_log


def mk(positive):
    return (
        {"stage_name":"CLEANUP_COMPLETED" if positive else "ENTERED_PLAYBUFFER",
         "audout_playbuffer_call_entries":459 if positive else 1,
         "audout_playbuffer_call_returns":459 if positive else 0},
        {"result":"GUEST_PRESUBMIT_PCM_PAGES_MATCHED" if positive else
            "GUEST_PRESUBMIT_UNVERIFIED", "observed_pages":8 if positive else 0},
        {"guest_window_atomic_counter_deltas":{
            "cpal_entries":2244 if positive else 0,
            "cpal_returns":2244 if positive else 0,
            "audioout_appends":261 if positive else 0}},
        510838 if positive else 0,
    )


class Stage294Tests(unittest.TestCase):
    def test_bounded_guest_pending_classified_without_permanent_lock_claim(self):
        self.assertEqual(classify(*mk(False)),
                         "GUEST_AUDOUT_RETURN_PENDING_IN_FINITE_PREJOIN")
    def test_completed_real_optical_crc_and_pcm_classified(self):
        self.assertEqual(classify(*mk(True)),
                         "EIGHT_PAGE_GUEST_CRC_AND_VIRTUAL_PCM_COMPLETED")
    def test_guest_21ms_actual_nonzero_pcm_must_change_class(self):
        p,f,c,_=mk(False)
        self.assertEqual(classify(p,f,c,1),
                         "OTHER_VERIFIED_OR_MIXED_AUDIO_OBSERVATION")
    def test_successful_callback_without_pcm_does_not_claim_guest_audio(self):
        p,f,c,_=mk(True)
        self.assertEqual(classify(p,f,c,0),
                         "OTHER_VERIFIED_OR_MIXED_AUDIO_OBSERVATION")
    def test_invalid_guest_final_crc_page_count_no_success(self):
        p,f,c,n=mk(True);f["observed_pages"]=7
        self.assertEqual(classify(p,f,c,n),
                         "OTHER_VERIFIED_OR_MIXED_AUDIO_OBSERVATION")
    def test_unreturned_callback_not_falsely_counted_success(self):
        p,f,c,n=mk(True);c["guest_window_atomic_counter_deltas"]["cpal_returns"]=0
        self.assertEqual(classify(p,f,c,n),
                         "OTHER_VERIFIED_OR_MIXED_AUDIO_OBSERVATION")
    def test_missing_log_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises((OSError,ValueError)):
                real_audit(Path(d)/"absent",Path(d)/"logs",21,123)
    def test_real_gui_logger_cp_error_reason_is_detectable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"nexium-20261021-030400.log"
            p.write_text(
                "03:04:00.002 ERROR nexium_runner::audio cpal stream error: BackendSpecific { err: xrun }\n",
                encoding="utf8")
            out=scan_host_log(p)
            self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],1)
            self.assertIn("xrun_or_underrun_token",
                          out["sanitized_error_message_groups"][0]["lexical_tokens_not_diagnosis"])
    def test_stdout_missing_error_text_does_not_erase_positive_cpal_counter(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"nexium-20261021-030400.log"
            p.write_text("03:04:00 INFO NeXium starts\n")
            out=scan_host_log(p)
            self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],0)
    def test_source_constants_are_full_distinct_sha256(self):
        self.assertEqual(len(HOST_SHA),64)
        self.assertEqual(len(NRO_SHA),64)
        self.assertNotEqual(HOST_SHA,NRO_SHA)
        self.assertTrue(SCHEMA.endswith("/v1"))

if __name__=="__main__":
    unittest.main()
