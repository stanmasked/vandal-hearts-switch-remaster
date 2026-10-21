"""Stage315 synthetic-only poll parameter privacy, monotonicity and source checks."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from capture_map02_poll_arguments_stage315 import POLL_META_FIELDS,POLL_META_HEADER
from audit_map02_poll_arguments_stage315 import parse,summarize,decode_timeout,U64MAX

class PollArgsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.p=Path(temp.name)/"pollparams.csv"
        self.rows=[]
        for i in range(42):
            now=1_000_000_000+i*200_000_000
            self.rows.append(("P",now,-1,2,*([0]*8)))
            self.rows.append(("M",now,1,0,1,1,0,0,0,0,0,0))
            if i>0:
                self.rows.append(("M",now,0,22,3,0,0,i,i,0,0,0))
        self.write()
    def write(self,head=POLL_META_HEADER):
        with self.p.open("w",encoding="ascii",newline="") as f:
            w=csv.writer(f)
            w.writerow(head)
            w.writerows(self.rows)
    def test_stalled_infinite_cpal_poll(self):
        frames,sha=parse(self.p)
        result=summarize(frames,1_050_000_000,9_000_000_000,{1})
        cp=result["source_proven_CPAL_poll_timeout_and_return_class"][0]
        self.assertEqual(cp["last_poll_timeout_class"],"infinite")
        self.assertEqual(cp["last_poll_timeout_ms_or_null"],-1)
        self.assertEqual(cp["last_poll_nfds_capped_65_means_more_than_64"],1)
        self.assertEqual(cp["poll_timeout_infinite_entries_delta"],0)
        self.assertEqual(cp["poll_return_ready_count_delta"],0)
        self.assertEqual(len(sha),64)
    def test_non_cpal_finite_poll_return_ready(self):
        frames,_=parse(self.p)
        r=summarize(frames,1_050_000_000,9_000_000_000,{1})
        other=next(x for x in r["all_anonymous_native_poll_timeout_and_return_classes"]
                   if x["anonymous_native_TLS_alias"]==0)
        self.assertEqual(other["last_poll_timeout_ms_or_null"],21)
        self.assertGreater(other["poll_return_ready_count_delta"],20)
        self.assertFalse(other["belongs_to_pre_input_proven_CPAL_callback_thread"])
    def test_decode_invalid_negative_distinct_from_infinite(self):
        self.assertEqual(decode_timeout(0)["kind"],"infinite")
        self.assertEqual(decode_timeout(U64MAX)["kind"],"invalid_negative")
        self.assertEqual(decode_timeout(1)["timeout_ms"],0)
    def test_reject_raw_fd_header(self):
        self.write(head=("kind","monotonic_ns","native_tid",*POLL_META_FIELDS))
        with self.assertRaisesRegex(ValueError,"schema"):
            parse(self.p)
    def test_reject_invalid_nfds(self):
        i=1
        row=list(self.rows[i]);row[4]=66
        self.rows[i]=tuple(row);self.write()
        with self.assertRaisesRegex(ValueError,"bucket"):
            parse(self.p)
    def test_reject_monotonic_counter_regression(self):
        idx=next(i for i,x in enumerate(self.rows) if x[0]=="M" and x[2]==0 and x[1]>4_000_000_000)
        row=list(self.rows[idx]);row[8]=0
        self.rows[idx]=tuple(row);self.write()
        with self.assertRaisesRegex(ValueError,"decreased"):
            parse(self.p)
    def test_reject_nonmonotonic_P_time(self):
        idx=next(i for i,x in enumerate(self.rows) if x[0]=="P" and x[1]>5_000_000_000)
        row=list(self.rows[idx]);row[1]=1_000_000_000
        self.rows[idx]=tuple(row);self.write()
        with self.assertRaisesRegex(ValueError,"Nonmonotonic"):
            parse(self.p)
    def test_reject_duplicate_thread_sample(self):
        self.rows.insert(2,self.rows[1]);self.write()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            parse(self.p)
    def test_reject_missing_guest_clock(self):
        frames,_=parse(self.p)
        with self.assertRaisesRegex(ValueError,"not spanning"):
            summarize(frames,12_000_000_000,13_000_000_000,{1})
    def test_refuse_symlink_source(self):
        raw=self.p.parent/"raw.csv";self.p.rename(raw);self.p.symlink_to(raw)
        with self.assertRaisesRegex(ValueError,"absent"):
            parse(self.p)
    def test_no_cpal_source_identity_not_assumed(self):
        frames,_=parse(self.p)
        result=summarize(frames,1_050_000_000,9_000_000_000,set())
        self.assertEqual(result["source_proven_CPAL_poll_timeout_and_return_class"],[])
        self.assertGreater(len(result["all_anonymous_native_poll_timeout_and_return_classes"]),0)

if __name__=="__main__":unittest.main()
