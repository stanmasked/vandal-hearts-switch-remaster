"""Stage314 tests: synthetic libc wait source, never claimed as NeXium proof."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_libc_wait_stage314 import read_libc,summarize
from capture_map02_libc_wait_stage314 import LIBC_WAIT_HEADER,LIBC_WAIT_NAMES

class Stage314SyntheticTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.f=Path(temp.name)/"wait-anon.csv"
        self.clock=lambda i: 1_000_000_000+i*200_000_000
        self.rows=self.data()
        self.write()
    def data(self):
        rows=[]
        for i in range(45):
            ts=self.clock(i)
            rows.append(("P",ts,-1,"sample",2,0,0))
            rows.append(("B",ts,1,"poll",1,0,0))
            if i:
                rows.append(("B",ts,0,"ppoll",i,i,0))
        return rows
    def write(self,header=LIBC_WAIT_HEADER):
        with self.f.open("w",encoding="ascii",newline="") as f:
            writer=csv.writer(f);writer.writerow(header)
            writer.writerows(self.rows)
    def test_real_exact_sample_intervals_source_counters(self):
        frames,sha=read_libc(self.f)
        r=summarize(frames,self.clock(1)+50_000_000,self.clock(40),{1})
        cp=next(x for x in r["cpal_same_native_thread_libc_waits"]
                if x["intercepted_libc_export"]=="poll")
        self.assertEqual(cp["entry_count_delta"],0)
        self.assertEqual(cp["return_count_delta"],0)
        self.assertEqual(cp["pending_calls_at_guest_last_observation"],1)
        self.assertEqual(r["CPAL_thread_outstanding_libc_calls_at_last_sample"],1)
        self.assertTrue(r["no_periodic_poll_sample_can_establish_exact_kernel_block_duration"])
        self.assertEqual(len(sha),64)
    def test_active_other_thread_is_not_cpal_attribution(self):
        frames,_=read_libc(self.f)
        r=summarize(frames,self.clock(1)+50_000_000,self.clock(40),{1})
        background=next(x for x in r["all_anonymous_TLS_libc_waits"]
                        if x["anonymous_native_TLS_alias"]==0
                        and x["intercepted_libc_export"]=="ppoll")
        self.assertFalse(background["belongs_to_pre_input_CPAL_callback_thread"])
        self.assertEqual(background["entry_count_delta"],39)
    def test_returned_cpal_poll_counter(self):
        self.rows=[("B",ts,alias,fn,
                    4+i if fn=="poll" else count,
                    4+i if fn=="poll" else ret,neg)
                   if kind=="B" else ("P",ts,alias,fn,count,ret,neg)
                   for i,(kind,ts,alias,fn,count,ret,neg) in enumerate(self.rows)]
        self.write()
        frames,_=read_libc(self.f)
        self.assertTrue(frames)
    def test_reject_source_leaking_kernel_tid_column(self):
        self.write(header=("kind","monotonic_ns","native_tid","function",
                           "entered","returned","negative_returned"))
        with self.assertRaisesRegex(ValueError,"columns"):
            read_libc(self.f)
    def test_reject_decreasing_counter(self):
        self.rows[8]=("B",self.clock(3),1,"poll",0,0,0)
        self.write()
        with self.assertRaisesRegex(ValueError,"(decreased|outside)"):
            read_libc(self.f)
    def test_reject_unknown_export(self):
        self.rows[1]=("B",self.clock(0),1,"syscall",1,0,0)
        self.write()
        with self.assertRaisesRegex(ValueError,"outside"):
            read_libc(self.f)
    def test_reject_duplicate_phase_in_sample(self):
        self.rows.insert(3,("B",self.clock(1),1,"poll",1,0,0))
        self.write()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            read_libc(self.f)
    def test_reject_stale_guest_end_marker(self):
        frames,_=read_libc(self.f)
        with self.assertRaisesRegex(ValueError,"(Too few|too far)"):
            summarize(frames,11_000_000_000,12_000_000_000,{1})
    def test_reject_symlinked_counter_csv(self):
        original=self.f.parent/"truth.csv"
        self.f.rename(original);self.f.symlink_to(original)
        with self.assertRaisesRegex(ValueError,"absent"):
            read_libc(self.f)
    def test_callback_absence_does_not_mean_no_poll_source(self):
        frames,_=read_libc(self.f)
        result=summarize(frames,self.clock(1)+50_000_000,self.clock(40),set())
        self.assertEqual(result["CPAL_thread_libc_export_entries_observed"],0)
        self.assertGreater(len(result["all_anonymous_TLS_libc_waits"]),0)
    def test_all_supported_exports_in_schema(self):
        self.assertEqual(tuple(LIBC_WAIT_NAMES),
                         ("poll","ppoll","epoll_wait","epoll_pwait"))

if __name__=="__main__":unittest.main()
