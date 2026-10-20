"""Generated-only Stage293 CPAL stdout log inventory tests. No ROM or emulator."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_error_messages_stage293 import (
    scan_host_log,normalize_reason,descriptive_tags,compare_logs,
    HOST_SHA,NRO_SHA,RUNS,SCHEMA,LIMIT_BYTES
)


def pretend(hint,log_lines=0):
    return {
        "requested_pulse_hint_ms":hint,
        "source_run_id":RUNS[hint],
        "exact_compiled_nexium_elf_sha256":HOST_SHA,
        "exact_generated_only_nro_sha256":NRO_SHA,
        "cpal_stream_error_log_line_count_all_times":log_lines,
        "post_input_cpal_error_callback_counter_delta":0 if hint==21 else 36,
        "post_input_cpal_callback_entry_delta":0 if hint==21 else 2244,
    }


class ErrorLogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.file=Path(temp.name)/"nexium-guest-stdout.log"
        self.file.write_text("NeXium started\n",encoding="utf-8")

    def test_real_log_form_multiple_identical_cpal_errors_grouped(self):
        body="NeXium started\n"+(
            "2026-10-21 ERROR cpal stream error: BackendSpecific { err: xrun }\n"*3)
        self.file.write_text(body)
        out=scan_host_log(self.file)
        self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],3)
        self.assertEqual(out["distinct_sanitized_cpal_error_messages"],1)
        self.assertEqual(out["sanitized_error_message_groups"][0]["times_in_entire_stdout"],3)
        self.assertIn("xrun_or_underrun_token",
                      out["sanitized_error_message_groups"][0]["lexical_tokens_not_diagnosis"])
        self.assertIn("backend_token",
                      out["sanitized_error_message_groups"][0]["lexical_tokens_not_diagnosis"])
        self.assertTrue(out["full_run_log_count_cannot_equal_window_delta_by_assumption"])

    def test_log_without_emitted_error_messages_still_valid_inventory(self):
        self.file.write_text("INFO CPAL stream started\nInfo: loaded GUI\n")
        out=scan_host_log(self.file)
        self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],0)
        self.assertEqual(out["sanitized_error_message_groups"],[])

    def test_case_insensitive_ansi_cpal_error_detection(self):
        self.file.write_bytes(b"\x1b[31mERROR CPAL STREAM ERROR: buffer overrun\x1b[0m\n")
        out=scan_host_log(self.file)
        self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],1)
        self.assertIn("buffer_token",out["sanitized_error_message_groups"][0]["lexical_tokens_not_diagnosis"])

    def test_mixed_audio_warnings_not_assumed_cpal_error_callbacks(self):
        self.file.write_text("WARN Audio output disabled: stream.play: device gone\n")
        out=scan_host_log(self.file)
        self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],0)
        self.assertEqual(out["other_audio_warning_line_count_all_times"],1)

    def test_sanitize_host_paths_addresses_and_numeric_tokens(self):
        reason=normalize_reason("ALSA at /home/runner/work/path/file.rs failed at 0xdeadbeef code 12345")
        self.assertNotIn("/home/runner",reason)
        self.assertNotIn("0xdeadbeef",reason)
        self.assertNotIn("12345",reason)
        self.assertIn("ALSA",reason)

    def test_unknown_cp_error_is_not_silently_classified_as_alsa(self):
        self.assertEqual(descriptive_tags("Something mysterious"),["no_predefined_keyword"])

    def test_stdout_digest_is_computed_from_original_bytes(self):
        raw=b"hello\n"
        self.file.write_bytes(raw)
        self.assertEqual(scan_host_log(self.file)["original_stdout_sha256"],
                         hashlib.sha256(raw).hexdigest())

    def test_existing_empty_stdout_is_valid_explicit_no_message_observation(self):
        self.file.write_bytes(b"")
        out=scan_host_log(self.file)
        self.assertTrue(out["original_stdout_is_empty"])
        self.assertEqual(out["cpal_stream_error_log_line_count_all_times"],0)
        self.assertEqual(out["original_stdout_sha256"],hashlib.sha256(b"").hexdigest())

    def test_missing_stdout_fails_closed(self):
        self.file.unlink()
        with self.assertRaisesRegex(ValueError,"missing"):
            scan_host_log(self.file)

    def test_stdout_oversized_fails_closed(self):
        self.file.write_bytes(b"x"*(LIMIT_BYTES+1))
        with self.assertRaisesRegex(ValueError,"large"):
            scan_host_log(self.file)

    def test_symlinked_stdout_refused(self):
        link=self.file.parent/"symlink.log"
        link.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError,"symlink"):
            scan_host_log(link)

    def test_invalid_utf8_replaced_without_fabricating_an_error_reason(self):
        self.file.write_bytes(b"NeXium\xff\xfe\n")
        self.assertEqual(scan_host_log(self.file)["cpal_stream_error_log_line_count_all_times"],0)

    def test_expected_21_22_matched_new_host_pair(self):
        result=compare_logs(pretend(21),pretend(22,36),
                            "ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")
        self.assertEqual(result["schema"],SCHEMA)
        self.assertEqual(result["result"],"REAL_MATCHED_CPAL_HOST_ERROR_LOGS_AND_L_COUNTERS_INVENTORIED")
        self.assertTrue(result["stdout_error_lines_cannot_be_precisely_mapped_to_guest_window"])
        self.assertTrue(result["no_cpal_root_cause_or_permanent_guest_deadlock_proven"])
        self.assertFalse(result["physical_nintendo_switch_dac_proven"])

    def test_host_log_line_count_not_assumed_equal_to_guest_window_error_delta(self):
        r=compare_logs(pretend(21,9),pretend(22,2),
                       "ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")
        self.assertEqual(r["cpal_message_reason_visibility"],
                         "MESSAGE_TEXT_PRESENT_IN_AT_LEAST_ONE_HOST_LOG")

    def test_no_log_text_is_honestly_reported_even_if_counter_positive(self):
        r=compare_logs(pretend(21,0),pretend(22,0),
                       "ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")
        self.assertEqual(r["cpal_message_reason_visibility"],
                         "NO_CPAL_ERROR_MESSAGE_TEXT_EMITTED_TO_CAPTURED_STDOUT")

    def test_different_host_sha_rejected(self):
        r=pretend(22)
        r["exact_compiled_nexium_elf_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"Not identical"):
            compare_logs(pretend(21),r,"ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")

    def test_wrong_original_run_id_rejected(self):
        r=pretend(21);r["source_run_id"]+=1
        with self.assertRaisesRegex(ValueError,"run ID"):
            compare_logs(r,pretend(22),"ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")

    def test_21ms_nonzero_error_delta_not_assumed_old_state(self):
        r=pretend(21);r["post_input_cpal_error_callback_counter_delta"]=1
        with self.assertRaisesRegex(ValueError,"21ms"):
            compare_logs(r,pretend(22),"ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED")

    def test_unverified_prior_pair_cannot_claim_verified_source_log(self):
        with self.assertRaisesRegex(ValueError,"verified one-pair"):
            compare_logs(pretend(21),pretend(22),"UNVERIFIED")

if __name__=="__main__":
    unittest.main()
