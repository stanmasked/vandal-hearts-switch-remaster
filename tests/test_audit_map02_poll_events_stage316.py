"""Stage316 ordinal event source synthetic negatives. NOT NeXium evidence."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_poll_events_stage316 import read_source,summarize
from capture_map02_poll_events_stage316 import POLL_EVENT_FIELDS,POLL_EVENT_HEADER

class OrdinalPollEventTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.path=Path(t.name)/"sanitized.csv"
        self.records=[]
        for i in range(45):
            tm=1_000_000_000+i*200_000_000
            self.records.append(("P",tm,-1,2,*([0]*8)))
            # one pre-input read+write ordinal request; no return later
            self.records.append(("M",tm,1,1,0,0,1,0,0,0,0,0))
            if i:
                self.records.append(("M",tm,0,i,0,i,0,i,0,i,0,0))
        self.write()
    def write(self,header=POLL_EVENT_HEADER):
        with self.path.open("w",encoding="ascii",newline="") as f:
            c=csv.writer(f);c.writerow(header);c.writerows(self.records)
    def test_source_late_guest_stalled_cpal_zero_event_delta(self):
        frames,sha=read_source(self.path)
        r=summarize(frames,1_050_000_000,9_000_000_000,{1})
        c=r["cpal_proven_native_thread_poll_event_categories"]
        self.assertEqual(len(c),1)
        self.assertEqual(c[0]["ordinal0_requested_POLLIN_guest_delta"],0)
        self.assertEqual(c[0]["ordinal1_requested_POLLOUT_guest_delta"],0)
        self.assertEqual(c[0]["ordinal0_returned_POLLIN_guest_delta"],0)
        self.assertTrue(c[0]["two_ordinal_positions_are_not_linux_fd_numbers"])
        self.assertEqual(len(sha),64)
    def test_active_other_thread_not_misattributed_to_CPAL(self):
        f,_=read_source(self.path);r=summarize(f,1_050_000_000,9_000_000_000,{1})
        other=next(x for x in r["all_anonymous_tls_poll_event_categories"]
                  if x["anonymous_same_process_native_TLS_alias"]==0)
        self.assertFalse(other["source_proven_preinput_CPAL_callback_thread"])
        self.assertGreater(other["ordinal0_returned_POLLIN_guest_delta"],25)
    def test_no_positive_cpal_marker_means_no_claim(self):
        f,_=read_source(self.path);r=summarize(f,1_050_000_000,9_000_000_000,set())
        self.assertEqual(r["cpal_proven_native_thread_poll_event_categories"],[])
    def test_raw_fd_header_fails_closed(self):
        self.write(("kind","monotonic_ns","native_fd",*POLL_EVENT_FIELDS))
        with self.assertRaisesRegex(ValueError,"source changed"):
            read_source(self.path)
    def test_noninteger_counter_rejected(self):
        row=list(self.records[1]);row[5]="POLLIN"
        self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"nonnumeric"):read_source(self.path)
    def test_decreasing_cumulative_counter_rejected(self):
        k=next(i for i,r in enumerate(self.records) if r[0]=="M"
               and r[2]==0 and r[1]>5_000_000_000)
        v=list(self.records[k]);v[3]=0;self.records[k]=v;self.write()
        with self.assertRaisesRegex(ValueError,"decreased"):read_source(self.path)
    def test_forged_tls_alias_refused(self):
        row=list(self.records[1]);row[2]=64;self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"metadata alias"):read_source(self.path)
    def test_duplicate_alias_same_sample_refused(self):
        self.records.insert(2,self.records[1]);self.write()
        with self.assertRaisesRegex(ValueError,"Duplicated"):read_source(self.path)
    def test_nonmonotonic_sample_time_rejected(self):
        k=next(i for i,r in enumerate(self.records) if r[0]=="P" and r[1]>4_000_000_000)
        row=list(self.records[k]);row[1]=1_000_000_000
        self.records[k]=row;self.write()
        with self.assertRaisesRegex(ValueError,"regression"):read_source(self.path)
    def test_stale_guest_timestamps_rejected(self):
        f,_=read_source(self.path)
        with self.assertRaisesRegex(ValueError,"do not bracket"):
            summarize(f,12_000_000_000,13_000_000_000,{1})
    def test_symlink_source_refused(self):
        orig=self.path.parent/"original.csv";self.path.rename(orig)
        self.path.symlink_to(orig)
        with self.assertRaisesRegex(ValueError,"unavailable"):read_source(self.path)

if __name__=="__main__":unittest.main()
