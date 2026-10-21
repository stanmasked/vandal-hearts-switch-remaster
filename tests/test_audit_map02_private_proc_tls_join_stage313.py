"""Stage313 synthetic controls; source-only real trial attribution must come from CI."""
import csv
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_private_proc_tls_join_stage313 import parse_join,analyze,HEADER
from capture_map02_private_proc_tls_join_stage313 import (
    raw_alias_view,MM_SIZE,PRIVATE_TID_OFFSET,CPAL_MARK_OFFSET)

def synth():
    tasks=[]
    join=[]
    base=1_000_000_000
    for i in range(62):
        clock=base+i*250_000_000
        for taskid in range(1,11):
            tasks.append({"sample":i,"clock":clock,"alias":taskid,
                          "ticks":100+i if taskid!=4 else 100,
                          "state":"S" if taskid==4 else "R",
                          "wait":"poll" if taskid==4 else "UNKNOWN",
                          "label":"AUDIO_NAMED" if taskid==4 else "UNATTRIBUTED"})
            join.append((i,clock,taskid,1 if taskid==4 else -1,
                         1 if taskid==4 else 0))
    tags=[{"time":base+i*200_000_000,
           "alias":{1:1}}
          for i in range(82)]
    return tasks,join,tags

class Stage313SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.t,self.j,self.tags=synth()
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.p=Path(temp.name)/"join.csv"
        self.write(self.j)
    def write(self,rows,header=HEADER):
        with self.p.open("w",newline="",encoding="ascii") as f:
            writer=csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
    def test_real_join_to_sleeping_pre_input_marked_task(self):
        source,sha=parse_join(self.p,self.t)
        analysis=analyze(source,self.t,5_000_000_000,14_000_000_000,self.tags)
        self.assertEqual(analysis["source_cpal_tagged_pre_input_task_count"],1)
        task=analysis["cpal_tagged_pre_input_native_task_wait_evidence"][0]
        self.assertEqual(task["anonymous_proc_task_alias"],4)
        self.assertEqual(task["anonymous_tls_alias"],1)
        self.assertEqual(task["CPAL_callback_cumulative_before_input"],1)
        self.assertEqual(task["CPAL_callback_tag_growth_inside_observed_window"],0)
        self.assertEqual(task["guest_last_wait_category"],"poll")
        self.assertEqual(task["guest_source_task_CPU_tick_change"],0)
        self.assertEqual(len(sha),64)
    def test_unknown_tids_never_exposed(self):
        buffer=bytearray(MM_SIZE)
        struct.pack_into("<8sQ",buffer,0,b"VH305AL1",3)
        struct.pack_into("<Q",buffer,PRIVATE_TID_OFFSET+8,54321)
        struct.pack_into("<Q",buffer,CPAL_MARK_OFFSET+8,1)
        native,marks=raw_alias_view(buffer)
        self.assertEqual(native[54321],1)
        self.assertEqual(marks[1],1)
        self.assertNotIn("54321",str(self.j))
    def test_reject_wrong_mmap_magic(self):
        buf=bytearray(MM_SIZE)
        with self.assertRaisesRegex(ValueError,"schema"):
            raw_alias_view(buf)
    def test_reject_duplicate_native_tid_alias(self):
        buf=bytearray(MM_SIZE)
        struct.pack_into("<8sQ",buf,0,b"VH305AL1",2)
        struct.pack_into("<Q",buf,PRIVATE_TID_OFFSET,432)
        struct.pack_into("<Q",buf,PRIVATE_TID_OFFSET+8,432)
        with self.assertRaisesRegex(ValueError,"same"):
            raw_alias_view(buf)
    def test_reject_raw_tid_header(self):
        self.write(self.j,["sample","observed_ns","raw_tid",
                           "anonymous_tls_alias","cpal_tag_cumulative"])
        with self.assertRaisesRegex(ValueError,"schema"):
            parse_join(self.p,self.t)
    def test_reject_task_invented_alias(self):
        rows=self.j.copy()
        rows[0]=(rows[0][0],rows[0][1],65000,-1,0)
        self.write(rows)
        with self.assertRaisesRegex(ValueError,"not from"):
            parse_join(self.p,self.t)
    def test_reject_tls_alias_switches_owner(self):
        rows=self.j.copy()
        i=next(i for i,x in enumerate(rows) if x[0]>20 and x[2]==5)
        sample,clock,task,old,marks=rows[i]
        rows[i]=(sample,clock,task,1,1)
        self.write(rows)
        with self.assertRaisesRegex(ValueError,"ownership"):
            parse_join(self.p,self.t)
    def test_reject_callback_marker_regression(self):
        rows=self.j.copy()
        i=next(i for i,x in enumerate(rows) if x[0]>20 and x[2]==4)
        sample,clock,task,old,marks=rows[i]
        rows[i]=(sample,clock,task,old,0)
        self.write(rows)
        with self.assertRaisesRegex(ValueError,"decreased"):
            parse_join(self.p,self.t)
    def test_reject_missing_source_join_row(self):
        self.write(self.j[:-1])
        with self.assertRaisesRegex(ValueError,"fully covered"):
            parse_join(self.p,self.t)
    def test_no_unverified_cpal_thread_from_zero_markers(self):
        rows=[(a,b,c,d,0) for a,b,c,d,mark in self.j]
        self.write(rows)
        source,_=parse_join(self.p,self.t)
        out=analyze(source,self.t,5_000_000_000,14_000_000_000,
                    [{"time":r["time"],"alias":{}} for r in self.tags])
        self.assertEqual(out["source_cpal_tagged_pre_input_task_count"],0)
        self.assertTrue(out["future_callback_not_invoked_cannot_prove_wakeup_expectation"])

if __name__=="__main__":unittest.main()
