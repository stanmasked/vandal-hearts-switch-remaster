"""ROM-free generated Stage288 CPAL lifecycle and AudioOut reporter cases."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_lifecycle_snapshots import parse,SCHEMA

FIRST=2_000_000_000
FINAL=3_800_000_000
START=1_000_000_000
INTERVAL=200_000_000

def sample(mode="active",n=16):
    rows=[]
    for i in range(n):
        t=START+i*INTERVAL
        state=3 if mode not in ("build_failure","play_failure") else (4 if mode=="build_failure" else 5)
        errors=(1 if i>=6 else 0) if mode=="error" else 0
        calls=2*i if mode in ("active","error") else (1 if mode=="pending" else 0)
        returns=2*i if mode in ("active","error") else 0
        frames=1024*i if mode in ("active","error") else 0
        consumed=768*i if mode in ("active","error") else 0
        appends=i if mode in ("active","error") else 0
        accepted=512*i if mode in ("active","error") else 0
        released=i if mode in ("active","error") else 0
        rows.append(f"L,{t},{state},{errors},{calls},{returns},{frames},{consumed},"
                    f"{appends},{accepted},{released}\n")
    return "".join(rows)


class LifecycleSnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"trace.csv"
        self.path.write_text(sample(),encoding="ascii")
    def setmode(self,mode):
        self.path.write_text(sample(mode),encoding="ascii")
    def test_valid_active_callback_observation(self):
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(r["schema"],SCHEMA)
        self.assertEqual(r["result"],"BOUNDED_LIFECYCLE_ATOMIC_SNAPSHOTS_PARSED")
        self.assertEqual(r["guest_window_observation"],
                         "CPAL_CALLBACK_ENTRIES_OBSERVED_IN_GUEST_WINDOW")
        self.assertEqual(r["guest_window_atomic_counter_deltas"]["cpal_entries"],18)
        self.assertTrue(r["guest_monotonic_window_verified"])
        self.assertFalse(r["permanent_guest_audioout_deadlock_or_cpal_root_cause_proven"])
        self.assertTrue(r["state_3_means_play_call_returned_not_stream_still_running"])
    def test_play_succeeded_but_idle_not_falsely_classified_as_build_failure(self):
        self.setmode("idle")
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(r["guest_window_observation"],
                         "PLAY_ONCE_SUCCEEDED_BUT_NO_NEW_CPAL_ENTRY_IN_GUEST_WINDOW")
        self.assertEqual(r["final_lifecycle_state"],3)
        self.assertIsNone(next(iter(r["observed_lifecycle_transition_intervals"]),None))
    def test_error_callbacks_increase_without_claiming_exact_event_time(self):
        self.setmode("error")
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(r["guest_window_observation"],
                         "CPAL_ERROR_CALLBACK_COUNT_INCREASED_IN_GUEST_WINDOW")
        self.assertEqual(r["guest_window_atomic_counter_deltas"]["error_callbacks"],1)
        self.assertTrue(r["cpal_error_counter_is_not_a_timestamped_error_event"])
    def test_pending_cpal_callback_is_not_permanent_deadlock_proof(self):
        self.setmode("pending")
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(r["guest_window_observation"],
                         "CPAL_CALLBACK_ENTRY_UNRETURNED_AT_LAST_SNAPSHOT")
        self.assertFalse(r["permanent_guest_audioout_deadlock_or_cpal_root_cause_proven"])
    def test_build_failure_state(self):
        self.setmode("build_failure")
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(r["guest_window_observation"],
                         "CPAL_STREAM_BUILD_FAILURE_STATE_OBSERVED")
    def test_play_failure_state(self):
        self.setmode("play_failure")
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(r["guest_window_observation"],
                         "CPAL_STREAM_PLAY_FAILURE_STATE_OBSERVED")
    def test_guest_markers_missing_no_window_claim(self):
        r=parse(self.path)
        self.assertEqual(r["guest_window_observation"],"NO_GUEST_INPUT_MARKERS")
        self.assertIsNone(r["guest_window_atomic_counter_deltas"]["cpal_entries"])
    def test_one_missing_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"Both monotonic"):
            parse(self.path,FIRST,None)
    def test_false_returns_exceed_entries_rejected(self):
        rows=self.path.read_text().splitlines(keepends=True)
        rows[6]=rows[6].replace(",12,12,",",12,13,")
        self.path.write_text("".join(rows))
        with self.assertRaisesRegex(ValueError,"returns exceed"):
            parse(self.path)
    def test_error_counter_cannot_decrease(self):
        self.setmode("error")
        rows=self.path.read_text().splitlines(keepends=True)
        rows[9]=rows[9].replace(",3,1,",",3,0,")
        self.path.write_text("".join(rows))
        with self.assertRaisesRegex(ValueError,"Decreasing"):
            parse(self.path)
    def test_lifecycle_failure_cannot_change_to_played(self):
        self.setmode("build_failure")
        rows=self.path.read_text().splitlines(keepends=True)
        rows[7]=rows[7].replace(",4,0,",",3,0,")
        self.path.write_text("".join(rows))
        with self.assertRaisesRegex(ValueError,"Impossible lifecycle"):
            parse(self.path)
    def test_nonmonotonic_time_rejected(self):
        rows=self.path.read_text().splitlines(keepends=True)
        rows[7]=rows[7].replace(str(START+7*INTERVAL),str(START+6*INTERVAL))
        self.path.write_text("".join(rows))
        with self.assertRaisesRegex(ValueError,"Nonmonotonic"):
            parse(self.path)
    def test_missing_lifecycle_field_rejected(self):
        self.path.write_text(self.path.read_text().replace(",3,0,",",0,",1))
        with self.assertRaisesRegex(ValueError,"wrong tag or column"):
            parse(self.path)
    def test_initial_build_play_transitions_can_happen_between_samples(self):
        rows=self.path.read_text().splitlines(keepends=True)
        rows[0]=rows[0].replace(",3,0,",",1,0,")
        rows[1]=rows[1].replace(",3,0,",",2,0,")
        self.path.write_text("".join(rows))
        r=parse(self.path,FIRST,FINAL)
        self.assertEqual(len(r["observed_lifecycle_transition_intervals"]),2)
    def test_observation_gap_over_two_seconds_rejected(self):
        rows=self.path.read_text().splitlines(keepends=True)
        rows[9]=rows[9].replace(str(START+9*INTERVAL),str(START+9*INTERVAL+2_200_000_000))
        self.path.write_text("".join(rows))
        with self.assertRaisesRegex(ValueError,"heartbeat gap"):
            parse(self.path)
    def test_incomplete_guest_input_window_rejected(self):
        with self.assertRaisesRegex(ValueError,"does not span"):
            parse(self.path,START+100_000_000,FINAL)
    def test_not_enough_reporter_rows_rejected(self):
        self.path.write_text(sample(n=4))
        with self.assertRaisesRegex(ValueError,"8 to 240"):
            parse(self.path)
    def test_oversized_reporter_rejected(self):
        self.path.write_text(sample(n=241))
        with self.assertRaisesRegex(ValueError,"8 to 240"):
            parse(self.path)

if __name__=="__main__":
    unittest.main()
