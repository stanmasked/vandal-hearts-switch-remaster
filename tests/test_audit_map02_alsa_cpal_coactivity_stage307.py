"""Stage307 only synthetic 200ms counter-coactivity falsification, not guest proof."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_cpal_coactivity_stage307 import compare_intervals,MAX_LAG_NS

def p(i,total):
    return {"sample_ns":1_000_000_000+i*200_000_000,
            "cpal_entry_counter":total}
def a(i,alias1=0,alias3=0):
    return {"clock":930_000_000+i*200_000_000,
            "values":{
                (1,"writei"):{"total":alias1},
                (1,"avail_delay"):{"total":alias1,"eio":0,"epipe":0},
                (3,"writei"):{"total":alias3},
                (3,"avail_delay"):{"total":alias3,"eio":0,"epipe":0},
            }}

class Stage307TemporalTests(unittest.TestCase):
    def setUp(self):
        self.c=[p(i,i*3) for i in range(40)]
        self.a=[a(i,i*3,i*100) for i in range(40)]
        self.first=1_050_000_000
        self.last=1_000_000_000+39*200_000_000

    def test_source_aligned_cpal_equals_alsa_candidate(self):
        r=compare_intervals(self.c,self.a,self.first,self.last)
        self.assertEqual(r["compared_consecutive_200ms_sampling_intervals"],39)
        x=next(t for t in r["tls_alias_coactivity"] if t["anonymous_alias"]==1)
        self.assertEqual(x["host_cpal_callback_entry_delta"],117)
        self.assertEqual(x["alsa_writei_return_total_delta"],117)
        self.assertEqual(x["bins_both_cpal_and_alsa_writei_increment"],39)
        self.assertEqual(x["sum_absolute_cpal_vs_alsa_writei_bin_differences"],0)
        self.assertTrue(r["anonymous_tls_alias_is_NOT_cpal_thread_identity"])

    def test_high_rate_alsa_is_not_count_equivalence(self):
        r=compare_intervals(self.c,self.a,self.first,self.last)
        high=next(t for t in r["tls_alias_coactivity"] if t["anonymous_alias"]==3)
        self.assertEqual(high["alsa_writei_return_total_delta"],3900)
        self.assertGreater(high["sum_absolute_cpal_vs_alsa_writei_bin_differences"],0)

    def test_cpal_stalled_with_active_alsa(self):
        c=[p(i,5) for i in range(40)]
        r=compare_intervals(c,self.a,self.first,self.last)
        self.assertEqual(r["host_cpal_guest_interval_entry_delta"],0)
        high=next(t for t in r["tls_alias_coactivity"] if t["anonymous_alias"]==3)
        self.assertEqual(high["bins_alsa_writei_increment_only"],39)

    def test_reject_clock_lag_above_two_hundred_fifty_ms(self):
        bad=[v for i,v in enumerate(self.a)
             if i not in (15,16,17,18)]
        with self.assertRaisesRegex(ValueError,"250ms"):
            compare_intervals(self.c,bad,self.first,self.last)

    def test_reject_invalid_guest_source_window(self):
        with self.assertRaisesRegex(ValueError,"monotonic"):
            compare_intervals(self.c,self.a,self.last,self.first)

    def test_reject_insufficient_guest_intervals(self):
        with self.assertRaisesRegex(ValueError,"Not enough"):
            compare_intervals(self.c,self.a,self.first,1_000_000_000+12*200_000_000)

    def test_reject_cpal_counter_regression(self):
        bad=self.c.copy()
        bad[22]=p(22,0)
        with self.assertRaisesRegex(ValueError,"decreased"):
            compare_intervals(bad,self.a,self.first,self.last)

    def test_reject_alsa_counter_regression(self):
        bad=self.a.copy()
        bad[22]=a(22,0,0)
        with self.assertRaisesRegex(ValueError,"regressed"):
            compare_intervals(self.c,bad,self.first,self.last)

    def test_non_identity_claim_explicit(self):
        result=compare_intervals(self.c,self.a,self.first,self.last)
        self.assertTrue(result["matching_P_and_ALSA_snapshots_not_exact_atomic_same_instant"])
        self.assertTrue(result["source_cumulative_call_total_does_not_prove_buffer_delivery"])

if __name__=="__main__":
    unittest.main()
