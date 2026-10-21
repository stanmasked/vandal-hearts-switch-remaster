"""Synthetic-only negative controls for Stage311, not actual guest ALSA evidence."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_inflight_stage311 import parse,guest_window
from capture_map02_alsa_inflight_stage311 import PHASE_HEADER,PHASE_OPS

def rows():
    head=",".join(PHASE_HEADER)+"\n"
    lines=[head]
    for n in range(35):
        ns=1000000000+n*200000000
        lines.append(f"P,{ns},-1,sample,2,0,0\n")
        lines.append(f"B,{ns},0,wait,{10+n},{9+n},0\n")
        lines.append(f"B,{ns},1,avail_update,{n+1},{n+1},0\n")
    return "".join(lines)

class Stage311Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"bounded.csv"
        self.path.write_text(rows())

    def test_read_source_inflight_per_alias(self):
        samples,digest=parse(self.path)
        self.assertEqual(len(samples),35)
        r=guest_window(samples,1100000000,7000000000,{0})
        wait=next(x for x in r["per_tls_alias_and_function"]
                  if x["anonymous_tls_alias"]==0 and x["exported_alsa_function"]=="wait")
        self.assertEqual(wait["source_window_begun_delta"],30)
        self.assertEqual(wait["source_window_returned_delta"],30)
        self.assertEqual(wait["maximum_sampled_unreturned_calls"],1)
        self.assertTrue(wait["has_cpal_marker_in_same_tls_guest_window"])
        self.assertTrue(r["sampled_in_flight_never_equates_to_permanent_thread_deadlock"])
        self.assertEqual(len(digest),64)

    def test_non_cpal_alias_explicit(self):
        samples,_=parse(self.path)
        result=guest_window(samples,1100000000,7000000000,{0})
        alt=next(x for x in result["per_tls_alias_and_function"]
                 if x["anonymous_tls_alias"]==1)
        self.assertFalse(alt["has_cpal_marker_in_same_tls_guest_window"])

    def test_reject_schema_with_tid(self):
        self.path.write_text(rows().replace("anonymous_tls_alias","native_tid",1))
        with self.assertRaisesRegex(ValueError,"schema"):
            parse(self.path)

    def test_reject_nonmonotonic_begin(self):
        self.path.write_text(rows().replace(
            "B,1400000000,0,wait,12,11,0",
            "B,1400000000,0,wait,2,11,0",1))
        with self.assertRaisesRegex(ValueError,"decreased"):
            parse(self.path)

    def test_reject_mismatched_sample_marker(self):
        self.path.write_text(rows().replace(",-1,sample,2,0,0",",-1,sample,2,1,0",1))
        with self.assertRaisesRegex(ValueError,"P sample"):
            parse(self.path)

    def test_reject_unknown_alsa_function(self):
        self.path.write_text(rows().replace(",0,wait,",",0,unknown_wait,",1))
        with self.assertRaisesRegex(ValueError,"not covered"):
            parse(self.path)

    def test_invalid_alias_rejected(self):
        self.path.write_text(rows().replace(",0,wait,",",55,wait,",1))
        with self.assertRaisesRegex(ValueError,"not covered"):
            parse(self.path)

    def test_raw_private_link_refused(self):
        destination=self.path.parent/"original.csv"
        self.path.rename(destination)
        self.path.symlink_to(destination)
        with self.assertRaisesRegex(ValueError,"missing"):
            parse(self.path)

    def test_unbounded_guest_markers_refused(self):
        source,_=parse(self.path)
        with self.assertRaisesRegex(ValueError,"cover"):
            guest_window(source,9000000000,10000000000,{0})

    def test_13_alsa_symbols_unique(self):
        self.assertEqual(len(PHASE_OPS),13)
        self.assertEqual(len(set(PHASE_OPS)),13)
        self.assertIn("poll_descriptors",PHASE_OPS)

if __name__=="__main__":
    unittest.main()
