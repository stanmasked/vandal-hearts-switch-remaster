"""Stage302 generated-only /proc observer and source-auditor falsification tests."""
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from capture_map02_linux_task_samples_stage302 import parsed_stat,bucket,audio_hint
from audit_map02_linux_task_state_stage302 import read_tasks

HEAD="sample,observed_ns,task_alias,name_hint,linux_state,cpu_ticks,wait_bucket\n"
def sample(n,stamp,alias=1,ticks=0,state="S",wait="futex",label="UNATTRIBUTED"):
    return f"{n},{stamp},{alias},{label},{state},{ticks},{wait}\n"

class Stage302ReadOnlyTaskTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path=Path(t.name)/"process-anonymized.csv"
        self.source=HEAD+"".join(sample(i,1000000000+i*250000000,ticks=i//4)
                                  for i in range(15))
        self.path.write_text(self.source)

    def reparse(self,content):
        self.path.write_text(content)
        return read_tasks(self.path)

    def test_real_shaped_anonymous_proc_samples(self):
        rows,stamps,digest=read_tasks(self.path)
        self.assertEqual(len(rows),15)
        self.assertEqual(len(stamps),15)
        self.assertEqual(len(digest),64)
        self.assertEqual(rows[-1]["ticks"],3)

    def test_proc_stat_parsing_avoids_parenthesized_command_collision(self):
        # stat columns after closing ')' begin at field #3. Validate exact
        # Linux kernel-provided utime/stime/starttime field offsets.
        cols=["S"]+["1"]*24
        cols[11]="400";cols[12]="8";cols[19]="555"
        state,cpu,start=parsed_stat("42 (cpal (alsa) callback) "+" ".join(cols))
        self.assertEqual((state,cpu,start),("S",408,555))

    def test_whitelisted_wait_classification(self):
        self.assertEqual(bucket("futex_wait_queue"),"futex")
        self.assertEqual(bucket("ep_poll"),"ep_poll")
        self.assertEqual(bucket("schedule_hrtimeout"),"schedule")
        self.assertEqual(bucket("unknown_secret_wait_function"),"OTHER")
        self.assertEqual(bucket("0"),"UNKNOWN")

    def test_audio_naming_is_only_weak_hint(self):
        self.assertEqual(audio_hint("cpal_alsa_out"),"AUDIO_NAMED")
        self.assertEqual(audio_hint("alsa-io"),"AUDIO_NAMED")
        self.assertEqual(audio_hint("nexium"),"UNATTRIBUTED")

    def test_reject_raw_linux_tid_alias(self):
        with self.assertRaisesRegex(ValueError,"Invalid bounded"):
            self.reparse(self.source.replace(",1,UNATTRIBUTED",",99999,UNATTRIBUTED",1))

    def test_reject_raw_thread_name(self):
        with self.assertRaisesRegex(ValueError,"leaked actual"):
            self.reparse(self.source.replace("UNATTRIBUTED","cpal_alsa_out",1))

    def test_reject_raw_linux_wchan(self):
        with self.assertRaisesRegex(ValueError,"raw Linux wait"):
            self.reparse(self.source.replace(",futex\n",",__libc_futex_wait\n",1))

    def test_reject_tick_regression(self):
        rows=self.source.splitlines()
        rows[-1]=rows[-1].replace(",3,futex",",0,futex")
        with self.assertRaisesRegex(ValueError,"tick count decreased"):
            self.reparse("\n".join(rows)+"\n")

    def test_reject_missing_sample(self):
        rows=self.source.splitlines()
        rows=[r for r in rows if not r.startswith("7,")]
        with self.assertRaisesRegex(ValueError,"missing/out"):
            self.reparse("\n".join(rows)+"\n")

    def test_reject_timestamp_backwards(self):
        rows=self.source.splitlines()
        rows[9]=rows[9].replace("3000000000","500000000",1)
        with self.assertRaisesRegex(ValueError,"bounded monotonic"):
            self.reparse("\n".join(rows)+"\n")

    def test_reject_duplicate_task_in_sample(self):
        rows=self.source.splitlines()
        rows.insert(4,rows[3])
        with self.assertRaisesRegex(ValueError,"Duplicate task"):
            self.reparse("\n".join(rows)+"\n")

    def test_reject_incomplete_sample_data(self):
        with self.assertRaisesRegex(ValueError,"too few"):
            self.reparse(HEAD+"".join(sample(i,1000000000+i*250000000)
                                      for i in range(6)))

    def test_symlink_refused(self):
        link=self.path.parent/"alias.csv";link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,"unavailable"):
            read_tasks(link)

if __name__=="__main__":
    unittest.main()
