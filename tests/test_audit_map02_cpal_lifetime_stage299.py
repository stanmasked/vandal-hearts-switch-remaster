"""Generated-only Stage299 P/L source-binding and false-causality rejection."""
import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_cpal_lifetime_stage299 import analyze,read_p

START=1_000_000_000
STEP=200_000_000
FIRST=2_500_000_000
LAST=3_800_000_000

class RealLifetimeParserSyntheticTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.l=self.root/"l.csv"
        self.p=self.root/"p.csv"
        self.generate()

    def generate(self,mode="positive",repeats=17):
        lines_l=[];lines_p=[]
        for i in range(repeats):
            now=START+i*STEP
            count=(1 if mode=="idle" else i)
            build=START-350_000_000
            build_ok=build+8_000_000
            play_start=build_ok+6_000_000
            play_ok=play_start+8_000_000
            args=[build,build_ok,0,play_start,play_ok,0,0]
            lines_l.append(f"L,{now},3,0,{count},{count},{count*240},{count*240},{count},{count*240},{count}\n")
            lines_p.append(f"P,{now},"+",".join(map(str,args))+f",{count}\n")
        self.l.write_text("".join(lines_l))
        self.p.write_text("".join(lines_p))

    def test_real_p_l_timing_and_success(self):
        r=analyze(self.p,self.l,FIRST,LAST)
        self.assertEqual(r["result"],"REAL_SOURCE_SYNCHRONIZED_CPAL_P_AND_L_REPARSED")
        self.assertEqual(r["host_observed_lifetime_classification"],
                         "HOST_PLAY_SUCCEEDED_NO_RETAINED_DROP_OBSERVED")
        self.assertEqual(r["first_positive_cpal_entry_observation"],
                         "FIRST_POSITIVE_COUNTER_BRACKETED_BY_P_SNAPSHOTS")
        self.assertEqual(r["first_positive_callback_counter_bracket_ns"],
                         [START,START+STEP])
        self.assertFalse(r["backend_alsa_pause_or_drop_event_proven"])

    def test_existing_callback_before_first_p_is_not_timestamped(self):
        self.generate(mode="idle")
        r=analyze(self.p,self.l,FIRST,LAST)
        self.assertEqual(r["first_p_cpal_entry_counter"],1)
        self.assertEqual(r["guest_window_p_cpal_entry_delta"],0)
        self.assertEqual(r["first_positive_cpal_entry_observation"],
                         "INITIAL_P_COUNTER_ALREADY_POSITIVE_NO_FIRST_CALLBACK_TIME")
        self.assertIsNone(r["first_positive_callback_counter_bracket_ns"])

    def test_drop_event_observed_but_not_alsa_pause_proven(self):
        lines=self.p.read_text().splitlines()
        for i,s in enumerate(lines):
            vals=s.split(",")
            if i>=12:vals[8]=str(START+STEP*11)
            lines[i]=",".join(vals)
        self.p.write_text("\n".join(lines)+"\n")
        r=analyze(self.p,self.l,FIRST,LAST)
        self.assertEqual(r["host_observed_lifetime_classification"],
                         "HOST_PLAY_SUCCEEDED_DROP_OBSERVED")
        self.assertFalse(r["backend_alsa_pause_or_drop_event_proven"])

    def test_l_p_same_tick_counter_mismatch_rejected(self):
        self.p.write_text(self.p.read_text().replace("P,1000000000,","P,1000000000,",1).replace(",0\n",",99\n",1))
        with self.assertRaisesRegex(ValueError,"match exact same-tick"):
            analyze(self.p,self.l,FIRST,LAST)

    def test_event_timestamp_changes_rejected(self):
        lines=self.p.read_text().splitlines()
        v=lines[8].split(",")
        v[2]=str(int(v[2])+300)
        lines[8]=",".join(v)
        self.p.write_text("\n".join(lines)+"\n")
        with self.assertRaisesRegex(ValueError,"event timestamp changed"):
            analyze(self.p,self.l,FIRST,LAST)

    def test_play_return_before_play_begin_rejected(self):
        self.p.write_text(self.p.read_text().replace(",664000000,672000000,0,0",",664000000,660000000,0,0"))
        with self.assertRaisesRegex(ValueError,"event ordering"):
            analyze(self.p,self.l,FIRST,LAST)

    def test_invalid_dual_play_outcome_rejected(self):
        lines=self.p.read_text().splitlines()
        for j in range(len(lines)):
            items=lines[j].split(",")
            items[7]=items[6]
            lines[j]=",".join(items)
        self.p.write_text("\n".join(lines)+"\n")
        with self.assertRaisesRegex(ValueError,"Mutually exclusive"):
            analyze(self.p,self.l,FIRST,LAST)

    def test_p_reporter_bad_shape_rejected(self):
        self.p.write_text(self.p.read_text().replace(",0,0\n",",0\n",1))
        with self.assertRaisesRegex(ValueError,"Malformed"):
            read_p(self.p)

    def test_missing_bounded_guest_window_rejected(self):
        with self.assertRaises(ValueError):
            analyze(self.p,self.l,START+200_000_000,LAST)

    def test_counter_decrease_rejected(self):
        self.p.write_text(self.p.read_text().replace(",8\n",",0\n",1))
        with self.assertRaisesRegex(ValueError,"counter decreased"):
            analyze(self.p,self.l,FIRST,LAST)

if __name__=="__main__":
    unittest.main()
