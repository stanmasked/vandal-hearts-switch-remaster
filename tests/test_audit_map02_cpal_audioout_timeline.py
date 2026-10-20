"""Generated-only CPAL reporter evidence tests; no ROM/audio/guest runner."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_audioout_timeline import parse

START=1_000_000_000
FIRST_INPUT=2_000_000_000
FINAL=3_800_000_000
STEP=200_000_000


def timeline(mode="success",n=16):
    lines=[]
    for i in range(n):
        t=START+i*STEP
        if mode=="success":
            entries=returns=3*i
            frames=512*i
            consumed=384*i
            appended=2*i
            pushed=256*i
            released=i
        elif mode=="unreturned":
            entries,returns=1,0
            frames=consumed=0
            appended=1
            pushed=released=0
        elif mode=="idle":
            entries=returns=1
            frames=512
            consumed=384
            appended=1
            pushed=256
            released=1
        else:
            raise ValueError("unknown synthetic mode")
        lines.append(f"T,{t},{entries},{returns},{frames},{consumed},"
                     f"{appended},{pushed},{released}\n")
    return "".join(lines)


class SyntheticCpalTimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"cpal.csv"
        self.path.write_text(timeline(),encoding="ascii")

    def test_realistic_positive_counter_series_with_exact_game_window(self):
        report=parse(self.path,FIRST_INPUT,FINAL)
        self.assertEqual(report["schema"],"vh-map02-nexium-cpal-audioout-timeline/v1")
        self.assertTrue(report["guest_input_and_final_markers_verified"])
        self.assertEqual(report["sample_count"],16)
        self.assertEqual(report["maximum_sample_gap_ms"],200.0)
        self.assertEqual(report["guest_window_counter_deltas"]["cpal_entries"],27)
        self.assertEqual(report["guest_window_counter_deltas"]["cpal_returns"],27)
        self.assertEqual(report["guest_window_counter_deltas"]["cpal_output_frames"],4608)
        self.assertEqual(report["guest_window_cpal_status"],
                         "CPAL_ENTERED_AND_ALL_ENTRIES_RETURNED_AT_LAST_SNAPSHOT")
        self.assertFalse(report["guest_audioout_deadlock_proven"])
        self.assertFalse(report["physical_switch_dac_output_proven"])
        self.assertFalse(report["trace_bound_to_source_binary_sha256_by_this_parser"])
        self.assertTrue(report["host_reporter_changes_nexium_scheduling"])

    def test_unreturned_callback_before_input_is_not_called_infinite_deadlock(self):
        self.path.write_text(timeline("unreturned"))
        x=parse(self.path,FIRST_INPUT,FINAL)
        self.assertEqual(x["guest_window_counter_deltas"]["cpal_entries"],0)
        self.assertEqual(x["last_sample_unreturned_cpal_entries"],1)
        self.assertEqual(x["guest_window_cpal_status"],
                         "CALLBACK_ENTRY_UNRETURNED_AS_OF_LAST_SNAPSHOT")
        self.assertFalse(x["guest_audioout_deadlock_proven"])

    def test_completed_but_idle_stream_reports_no_new_callback_entries(self):
        self.path.write_text(timeline("idle"))
        x=parse(self.path,FIRST_INPUT,FINAL)
        self.assertEqual(x["guest_window_cpal_status"],
                         "NO_NEW_CPAL_ENTRIES_AFTER_GUEST_INPUT")

    def test_missing_guest_markers_explicitly_omits_window_claim(self):
        x=parse(self.path)
        self.assertEqual(x["guest_window_cpal_status"],"NO_GUEST_INPUT_MARKERS")
        self.assertIsNone(x["guest_window_counter_deltas"]["cpal_entries"])
        self.assertFalse(x["guest_input_and_final_markers_verified"])

    def test_one_missing_guest_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"Both guest-clock markers"):
            parse(self.path,FIRST_INPUT,None)

    def test_missing_initial_pre_input_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError,"bracket"):
            parse(self.path,1_200_000_000,FINAL)

    def test_missing_final_snapshot_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError,"bracket"):
            parse(self.path,FIRST_INPUT,7_000_000_000)

    def test_duplicate_or_reverse_time_rejected(self):
        raw=self.path.read_text().splitlines(keepends=True)
        raw[7]=raw[7].replace(str(START+7*STEP),str(START+6*STEP))
        self.path.write_text("".join(raw))
        with self.assertRaisesRegex(ValueError,"Nonmonotonic"):
            parse(self.path)

    def test_oversized_silent_gap_rejected(self):
        raw=self.path.read_text().splitlines(keepends=True)
        raw[8]=raw[8].replace(str(START+8*STEP),str(START+8*STEP+2_100_000_000))
        self.path.write_text("".join(raw))
        with self.assertRaisesRegex(ValueError,"heartbeat gap"):
            parse(self.path)

    def test_returns_exceed_callback_entries_rejected(self):
        raw=self.path.read_text().splitlines(keepends=True)
        raw[5]=raw[5].replace(",15,15,",",15,16,")
        self.path.write_text("".join(raw))
        with self.assertRaisesRegex(ValueError,"returns exceed entries"):
            parse(self.path)

    def test_cumulative_cpal_return_counter_cannot_go_backwards(self):
        raw=self.path.read_text().splitlines(keepends=True)
        raw[9]=raw[9].replace(",27,27,",",27,26,")
        self.path.write_text("".join(raw))
        with self.assertRaisesRegex(ValueError,"Decreasing cumulative"):
            parse(self.path)

    def test_audioout_buffer_release_counter_cannot_go_backwards(self):
        raw=self.path.read_text().splitlines(keepends=True)
        raw[8]=raw[8].rsplit(",",1)[0]+",0\n"
        self.path.write_text("".join(raw))
        with self.assertRaisesRegex(ValueError,"Decreasing cumulative"):
            parse(self.path)

    def test_guest_counters_do_not_accept_negative_values(self):
        raw=self.path.read_text().splitlines(keepends=True)
        raw[7]=raw[7].replace(",7\n",",-1\n")
        self.path.write_text("".join(raw))
        with self.assertRaisesRegex(ValueError,"Negative or impossible"):
            parse(self.path)

    def test_unbounded_reporter_sample_count_rejected(self):
        self.path.write_text(timeline(n=241))
        with self.assertRaisesRegex(ValueError,"unbounded"):
            parse(self.path)

    def test_non_ascii_or_wrong_schema_rejected(self):
        self.path.write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError,"Non-ASCII"):
            parse(self.path)
        self.path.write_text("S,1,2,3,4,5,6,7,8\n"*9)
        with self.assertRaisesRegex(ValueError,"Malformed NeXium"):
            parse(self.path)

    def test_success_does_not_claim_real_dac_or_original_nightly_provenance(self):
        x=parse(self.path,FIRST_INPUT,FINAL)
        self.assertFalse(x["original_nexium_nightly_binary_equivalence_proven"])
        self.assertFalse(x["raw_game_audio_data_logged"])
        self.assertTrue(x["samples_are_snapshots_not_real_time_callback_duration"])


if __name__=="__main__":
    unittest.main()
