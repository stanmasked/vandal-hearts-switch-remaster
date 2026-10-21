"""Stage312 negative controls (synthetic only, never real guest scheduler evidence)."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_proc_task_wait_stage312 import summarize
from audit_map02_linux_task_state_stage302 import read_tasks

def rows():
    result=[]
    for i in range(38):
        now=1_000_000_000+i*250_000_000
        result.append(dict(sample=i,clock=now,alias=1,ticks=10+i,
                           state="S" if i%3 else "R",
                           label="AUDIO_NAMED",wait="futex" if i%3 else "UNKNOWN"))
        result.append(dict(sample=i,clock=now,alias=2,ticks=100+2*i,
                           state="R",label="UNATTRIBUTED",wait="UNKNOWN"))
    return result

class RealProcSamplingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.r=rows()
        self.first=1_050_000_000
        self.last=1_000_000_000+36*250_000_000

    def test_source_guest_cpu_and_wait_state_buckets(self):
        obj=summarize(self.r,self.first,self.last)
        self.assertEqual(obj["source_distinct_anonymous_proc_task_aliases"],2)
        self.assertGreater(obj["source_distinct_proc_sample_instants"],12)
        self.assertEqual(obj["audio_name_hint_aliases"],1)
        self.assertEqual(obj["audio_name_hint_aliases_showing_CPU_tick_growth"],1)
        self.assertEqual(obj["task_aliases_showing_CPU_tick_growth"],2)
        self.assertTrue(obj["independent_proc_task_alias_not_same_as_CPAL_ALSA_TLS_alias"])

    def test_cannot_infer_cpal_from_audio_name_only(self):
        obj=summarize(self.r,self.first,self.last)
        self.assertTrue(obj["task_name_substring_does_not_establish_CPAL_ownership"])
        self.assertTrue(obj["stable_wait_category_not_permanent_deadlock_proof"])

    def test_cpu_counter_regression_rejected(self):
        bad=[x.copy() for x in self.r]
        bad[-2]["ticks"]=0
        with self.assertRaisesRegex(ValueError,"regression"):
            summarize(bad,self.first,self.last)

    def test_guest_window_marker_wrong_order_rejected(self):
        with self.assertRaisesRegex(ValueError,"window"):
            summarize(self.r,self.last,self.first)

    def test_source_insufficient_window_rejected(self):
        with self.assertRaisesRegex(ValueError,"Fewer than 12"):
            summarize(self.r,1_000_000_000,1_150_000_000)

    def test_task_sampler_source_schema_rejects_real_tid_leak(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"tasks.csv"
            p.write_text("sample,observed_ns,task_tid,name_hint,linux_state,cpu_ticks,wait_bucket\n")
            with self.assertRaisesRegex(ValueError,"schema"):
                read_tasks(p)

    def test_source_sampler_symlink_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"tasks.csv"
            p.write_text("sample,observed_ns,task_alias,name_hint,linux_state,cpu_ticks,wait_bucket\n")
            link=Path(t)/"tasks-link.csv"
            link.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"unavailable"):
                read_tasks(link)

    def test_wait_bucket_explicit_but_not_kernel_stack(self):
        obj=summarize(self.r,self.first,self.last)
        self.assertIn("futex",obj["guest_sanitized_wait_bucket_observations"])
        self.assertTrue(all(item["source_only_coarse_sampling_not_kernel_stack"]
                            for item in obj["anonymous_proc_task_details"]))

if __name__=="__main__":unittest.main()
