"""Stage310 synthetic-only explicit provenance for matching C and ALSA TLS slots."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_real_direct_tls_guests_stage310 import (
    source_window,read_tag,read_alsa_frames)

def frames():
    a=[];t=[]
    for i in range(28):
        tm=1_000_000_000+i*200_000_000
        p={"time":tm,"allocated":2,
           "alias_op":{
            (0,"writei"):{"total":i*10},
            (1,"writei"):{"total":i*5},
            (1,"avail_delay"):{"total":i*5},
           }}
        c={"time":tm,"allocated":2,"alias":{1:i*5} if i else {}}
        a.append(p);t.append(c)
    return a,t

class Stage310SameTLSTests(unittest.TestCase):
    def setUp(self):
        a,t=frames();self.a=a;self.t=t
        self.first=1_050_000_000
        self.last=1_000_000_000+25*200_000_000

    def test_marked_same_thread_alsa_and_callback(self):
        r=source_window(self.a,self.t,self.first,self.last)
        by={x["anonymous_tls_alias"]:x for x in r["matched_native_thread_aliases"]}
        self.assertFalse(by[0]["tagged_cpal_and_alsa_writei_same_native_thread"])
        self.assertTrue(by[1]["tagged_cpal_and_alsa_writei_same_native_thread"])
        self.assertEqual(by[1]["real_tagged_cpal_callback_entry_delta"],125)
        self.assertEqual(by[1]["alsa_export_total_deltas"]["writei"],125)
        self.assertTrue(r["snapshots_share_exact_same_monotonic_observer_ticks"])

    def test_counter_coactivity_without_same_alias_not_attributed(self):
        a,t=frames()
        for row in t:
            row["alias"]={0:v for k,v in row["alias"].items()}
        r=source_window(a,t,self.first,self.last)
        by={x["anonymous_tls_alias"]:x for x in r["matched_native_thread_aliases"]}
        self.assertEqual(by[1]["real_tagged_cpal_callback_entry_delta"],0)
        self.assertTrue(by[0]["tagged_cpal_and_alsa_writei_same_native_thread"])
        self.assertFalse(by[1]["tagged_cpal_and_alsa_writei_same_native_thread"])

    def test_wrong_timestamp_never_matches_direct_source(self):
        t=[dict(row,time=row["time"]+1) for row in self.t]
        with self.assertRaisesRegex(ValueError,"not sampled by same"):
            source_window(self.a,t,self.first,self.last)

    def test_reject_alsa_decrease(self):
        a,t=frames()
        a[25]["alias_op"][(1,"writei")]["total"]=0
        with self.assertRaisesRegex(ValueError,"regressed"):
            source_window(a,t,self.first,self.last)

    def test_reject_cpal_counter_decrease(self):
        a,t=frames()
        t[25]["alias"][1]=1
        with self.assertRaisesRegex(ValueError,"regressed"):
            source_window(a,t,self.first,self.last)

    def test_no_snapshot_near_original_input(self):
        with self.assertRaisesRegex(ValueError,"distant"):
            source_window(self.a,self.t,4_000_000_000,6_000_000_000)

    def test_read_tag_schema_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"alias.csv"
            p.write_text("kind,ts,thread_pid,total\nP,1000,-1,0\n")
            with self.assertRaisesRegex(ValueError,"header"):
                read_tag(p)

    def test_refuse_symlink_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"raw.csv";p.write_text("z"*200)
            q=Path(tmp)/"link";q.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"missing"):
                read_tag(q)

    def test_read_alsa_counters_only_source_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"a.csv";p.write_text("kind,tid,op,count\n")
            with self.assertRaisesRegex(ValueError,"schema"):
                read_alsa_frames(p)

if __name__=="__main__":unittest.main()
