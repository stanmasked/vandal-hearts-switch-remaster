"""Stage306 synthetic-only fuzz cases. Not actual NeXium/ALSA guest evidence."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_guest_window_stage306 import window_deltas

H="kind,monotonic_ns,anonymous_alias,operation,total,success,eio,epipe,eagain,other_negative\n"

def fixture():
    text=H
    for clock,total,ok,eio,epipe in [
        (1_000_000_000,4,4,0,0),
        (1_100_000_000,7,6,1,0),
        (1_300_000_000,12,10,1,1),
        (1_500_000_000,14,12,1,1),
    ]:
        text+=f"P,{clock},-1,sample,2,0,0,0,0,0\n"
        text+=f"S,{clock},1,avail_delay,{total},{ok},{eio},{epipe},0,0\n"
        text+=f"S,{clock},2,writei,{ok},{ok},0,0,0,0\n"
    return text

class SourceBoundTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.p=Path(tmp.name)/"alsa-source.csv"
        self.p.write_text(fixture())
        self.first=1_050_000_000
        self.last=1_400_000_000

    def runaudit(self,replace):
        self.p.write_text(replace)
        return window_deltas(self.p,self.first,self.last)

    def test_distinct_guest_marker_bounded_frames(self):
        r=window_deltas(self.p,self.first,self.last)
        self.assertEqual(r["source_snapshot_count"],4)
        self.assertEqual(r["pre_input_alsa_snapshot_ns"],1_000_000_000)
        self.assertEqual(r["late_alsa_snapshot_ns"],1_300_000_000)
        self.assertEqual(r["delta_by_exported_symbol"]["avail_delay"]["total"],8)
        self.assertEqual(r["delta_by_exported_symbol"]["avail_delay"]["eio"],1)
        self.assertEqual(r["delta_by_exported_symbol"]["avail_delay"]["epipe"],1)
        self.assertTrue(r["no_exact_individual_alsa_call_timestamp"])

    def test_no_invented_guest_when_only_early_samples(self):
        with self.assertRaisesRegex(ValueError,"markers"):
            window_deltas(self.p,1_700_000_000,2_000_000_000)

    def test_reject_csv_without_source_header(self):
        with self.assertRaisesRegex(ValueError,"header"):
            self.runaudit(fixture().replace("anonymous_alias","linux_tid",1))

    def test_reject_bad_alsa_symbol(self):
        with self.assertRaisesRegex(ValueError,"Unknown"):
            self.runaudit(fixture().replace("avail_delay","invented_system_function",1))

    def test_reject_absurd_tls_alias(self):
        with self.assertRaisesRegex(ValueError,"Unknown"):
            self.runaudit(fixture().replace(",1,avail_delay,",",999,avail_delay,",1))

    def test_reject_duplicate_tls_row(self):
        lines=fixture().splitlines()
        lines.insert(3,lines[2])
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            self.runaudit("\n".join(lines)+"\n")

    def test_reject_return_counts_above_total(self):
        with self.assertRaisesRegex(ValueError,"ALSA return"):
            self.runaudit(fixture().replace(",4,4,0,0,0,0",",4,5,0,0,0,0",1))

    def test_reject_decreasing_alsa_counters(self):
        with self.assertRaisesRegex(ValueError,"regressed"):
            self.runaudit(fixture().replace(",12,10,1,1,0,0",
                                            ",3,1,1,1,0,0",1))

    def test_reject_decreasing_sample_clock(self):
        lines=fixture().splitlines()
        lines=[v.replace("1300000000","1050000000") for v in lines]
        with self.assertRaisesRegex(ValueError,"misordered"):
            self.runaudit("\n".join(lines)+"\n")

    def test_reject_corrupted_sample_marker(self):
        with self.assertRaisesRegex(ValueError,"slot count"):
            self.runaudit(fixture().replace("sample,2,0,0,0,0,0",
                                            "sample,2,1,0,0,0,0",1))

    def test_missing_actual_source_rejected(self):
        self.p.unlink()
        with self.assertRaisesRegex(ValueError,"missing"):
            window_deltas(self.p,self.first,self.last)

    def test_reject_symlink(self):
        self.p.parent.joinpath("orig.csv").write_text(fixture())
        self.p.unlink()
        self.p.symlink_to("orig.csv")
        with self.assertRaisesRegex(ValueError,"missing"):
            window_deltas(self.p,self.first,self.last)

    def test_not_deducing_global_thread_identity(self):
        result=window_deltas(self.p,self.first,self.last)
        self.assertTrue(result["separate_trial_anonymous_aliases_are_not_globally_comparable"])

if __name__=="__main__":unittest.main()
