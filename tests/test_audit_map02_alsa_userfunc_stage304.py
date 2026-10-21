"""Stage304 generated-only tests, never presented as true NeXium ALSA traces."""
import tempfile
from pathlib import Path
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_userfunc_stage304 import raw

START=10_000_000_000
STEP=200_000_000

class Stage304ALSAInterposeParserTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.p=Path(t.name)/"synthetic.csv"
        self.make()

    def make(self,negative=False):
        lines=[]
        for i in range(15):
            clk=START+i*STEP
            lines.append(f"H,{clk},1,0,1\n")
            if negative:
                neg=i//4
                first=START+3*STEP
                last=START+i*STEP if neg else 0
                first=first if neg else 0
            else:
                neg=0
                first=0
                last=0
            calls=i+neg
            success=i
            lines.append(f"T,{clk},1,{calls},{success},{neg},0,0,0,{first},{last}\n")
        self.p.write_text("".join(lines))

    def test_true_shape_heartbeat_and_one_anonymized_slot(self):
        h,s,sha=raw(self.p)
        self.assertEqual(len(h),15)
        self.assertEqual(len(s),15)
        self.assertEqual(len(sha),64)
        self.assertEqual(s[h[-1]["clock"]][1]["calls"],14)
        self.assertEqual(h[-1]["symbol_found"],True)

    def test_per_thread_eio_and_first_last_negative_stamp(self):
        self.make(negative=True)
        h,s,_=raw(self.p)
        self.assertGreater(s[h[-1]["clock"]][1]["eio"],0)
        self.assertGreater(s[h[-1]["clock"]][1]["first_negative_ns"],0)

    def test_heartbeat_valid_when_no_alsa_calls_observed(self):
        self.p.write_text("".join(f"H,{START+i*STEP},0,0,0\n" for i in range(15)))
        h,s,_=raw(self.p)
        self.assertEqual(len(h),15)
        self.assertEqual(len(s),0)

    def test_reject_duplicate_thread_slot_in_sample(self):
        x=self.p.read_text().splitlines()
        x.insert(2,x[1])
        self.p.write_text("\n".join(x)+"\n")
        with self.assertRaisesRegex(ValueError,"Duplicate ALSA"):
            raw(self.p)

    def test_reject_altered_heartbeat_and_slot_clocks(self):
        x=self.p.read_text().splitlines()
        x[1]=x[1].replace(str(START),str(START+1))
        self.p.write_text("\n".join(x)+"\n")
        with self.assertRaisesRegex(ValueError,"clock/alias mismatched"):
            raw(self.p)

    def test_reject_nonmonotonic_calls(self):
        x=self.p.read_text().splitlines()
        x[-1]=x[-1].replace(",14,14,",",0,14,")
        self.p.write_text("\n".join(x)+"\n")
        with self.assertRaisesRegex(ValueError,"totals exceed"):
            raw(self.p)

    def test_reject_unknown_pid_or_raw_thread_name(self):
        x=self.p.read_text().replace("H,","PID,",1)
        self.p.write_text(x)
        with self.assertRaisesRegex(ValueError,"Unexpected preloader"):
            raw(self.p)

    def test_reject_huge_slot_alias(self):
        x=self.p.read_text().replace("T,10000000000,1,","T,10000000000,9999,",1)
        self.p.write_text(x)
        with self.assertRaisesRegex(ValueError,"clock/alias mismatched"):
            raw(self.p)

    def test_reject_missing_negative_timestamp_pair(self):
        self.make(negative=True)
        x=self.p.read_text()
        marker=f",{START+3*STEP},{START+4*STEP}"
        # first negative in rows >= i=4; last stamp reset in one row.
        x=x.replace(f",{START+3*STEP},{START+4*STEP}\n",
                    f",{START+3*STEP},0\n",1)
        self.p.write_text(x)
        with self.assertRaisesRegex(ValueError,"Unpaired"):
            raw(self.p)

    def test_reject_symlink_trace(self):
        link=self.p.parent/"link.csv";link.symlink_to(self.p)
        with self.assertRaisesRegex(ValueError,"Missing original"):
            raw(link)

if __name__=="__main__":
    unittest.main()
