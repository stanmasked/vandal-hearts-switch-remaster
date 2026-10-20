"""Stage297 synthetic falsification: brackets, boundaries, stale counters, fail-closed."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_timing_stage297 import analyze_one

START=1_000_000_000
STEP=200_000_000
INPUT=2_050_000_000
LAST=3_800_000_000

def write(path,mode):
    rows=[]
    for i in range(16):
        if mode=="pre":
            entries=7 if i>=3 else (2 if i>=2 else 0)
        elif mode=="post":
            entries=8 if i>=8 else (4 if i>=7 else 0)
        elif mode=="boundary":
            entries=2 if i>=6 else 0
        elif mode=="pre_existing":
            entries=12
        else:
            entries=0
        rows.append(
            f"L,{START+STEP*i},3,0,{entries},{entries},"
            f"{entries*128},{entries*128},{entries},{entries*128},{entries}\n"
        )
    path.write_text("".join(rows),encoding="ascii")

class TimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)/"timeline.csv"

    def audit(self,mode):
        write(self.p,mode)
        return analyze_one(self.p,INPUT,LAST)

    def test_no_observed_entries_never_claims_pause(self):
        r=self.audit("idle")
        self.assertEqual(r["stage297_observation"],
          "NO_CPAL_CALLBACK_ENTRY_INCREMENT_SEEN_ANYWHERE_IN_OBSERVED_TRACE")
        m=r["metrics"]["cpal_entries"]
        self.assertIsNone(m["last_positive_increment_bracket_ns"])
        self.assertTrue(m["no_increment_does_not_mean_zero_callbacks_before_first_sample"])
        self.assertFalse(r["permanent_deadlock_or_alsa_root_cause_proven"])

    def test_preinput_last_change_bounded(self):
        r=self.audit("pre")
        self.assertEqual(r["stage297_observation"],
          "LATEST_OBSERVED_CPAL_ENTRY_INCREMENT_UNAMBIGUOUSLY_PRE_INPUT")
        m=r["metrics"]["cpal_entries"]
        self.assertEqual(m["last_positive_increment_bracket_ns"],
                         [START+2*STEP,START+3*STEP])
        self.assertEqual(m["increments_unambiguously_before_input"],7)
        self.assertEqual(m["increments_unambiguously_after_input"],0)

    def test_postinput_ongoing_callbacks_bounded(self):
        m=self.audit("post")["metrics"]["cpal_entries"]
        self.assertEqual(m["increments_unambiguously_after_input"],8)
        self.assertEqual(m["last_positive_increment_relation_to_input"],"AFTER_INPUT")

    def test_marker_boundary_interval_not_assumed_pre_or_post(self):
        m=self.audit("boundary")["metrics"]["cpal_entries"]
        self.assertEqual(m["increments_in_window_straddling_first_input"],2)
        self.assertEqual(m["increments_unambiguously_before_input"],0)
        self.assertEqual(m["increments_unambiguously_after_input"],0)

    def test_initial_nonzero_count_not_ever_active_claim(self):
        m=self.audit("pre_existing")["metrics"]["cpal_entries"]
        self.assertEqual(m["first_sample_counter"],12)
        self.assertEqual(m["observed_increment_total"],0)
        self.assertIsNone(m["last_positive_increment_bracket_ns"])

    def test_guest_markers_must_span_raw_trace(self):
        write(self.p,"pre")
        with self.assertRaisesRegex(ValueError,"does not span"):
            analyze_one(self.p,START+20_000_000,LAST)

    def test_unreturned_callback_exceeds_entries_rejected(self):
        write(self.p,"pre")
        text=self.p.read_text()
        self.p.write_text(text.replace(",0,7,7,",",0,7,8,",1))
        with self.assertRaisesRegex(ValueError,"returns exceed"):
            analyze_one(self.p,INPUT,LAST)

    def test_nonmonotonic_timestamps_rejected(self):
        write(self.p,"post")
        rows=self.p.read_text().splitlines()
        rows[9]=rows[9].replace(str(START+STEP*9),str(START+STEP*8))
        self.p.write_text("\n".join(rows)+"\n")
        with self.assertRaisesRegex(ValueError,"Nonmonotonic"):
            analyze_one(self.p,INPUT,LAST)

if __name__=="__main__":
    unittest.main()
