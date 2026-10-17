#!/usr/bin/env python3
"""v115: count-conservation binding of exact native equality to private JSONL."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from test_map02_v109_gp0_class_vblank_stores import five_classes
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v115_identity_runtime import summarize


def log(handlers=2,identical=0,different=0,other=1,
        cross_identical=0,cross_different=0,cross_other=0,vblanks=4):
    return (f"VH115_SAMPLE_IDENTITY_PASS handlers={handlers} vblanks={vblanks} "
            f"identical_count_equal_values={identical} "
            f"identical_count_different_values={different} "
            f"different_count={other} cross_equal_values={cross_identical} "
            f"cross_different_values={cross_different} "
            f"cross_different_count={cross_other}\n")


class NativeIdentitySummary(unittest.TestCase):
    def test_exact_values_only_native_not_exported(self):
        proof=summarize(log(),encode(sample()))
        self.assertEqual(proof["adjacent_unai_pairs"],1)
        self.assertEqual(proof["equal_sample_change_count_pairs"],0)
        self.assertEqual(proof["different_sample_change_count_pairs"],1)
        self.assertTrue(proof[
            "actual_24_post_handler_16bit_values_compared_in_native_process"])
        self.assertFalse(proof["raw_values_or_pixel_hash_exported"])
        self.assertFalse(proof["full_vram_persistence_proven"])
        self.assertFalse(proof["HD_replacement_approved"])

    def test_same_delta_count_does_not_determine_exact_value_identity(self):
        events=five_classes()
        polygon=next(i for i,e in enumerate(events)
                     if e["kind"]=="gp0_unai_handled" and e["value"]>>24==0x20)
        events[polygon+1]["value"]=1
        raw=encode(events)
        identical=summarize(log(handlers=5,identical=1,other=3,cross_other=2),raw)
        different=summarize(log(handlers=5,different=1,other=3,cross_other=2),raw)
        self.assertEqual(identical["equal_sample_change_count_pairs"],1)
        self.assertEqual(different["equal_sample_change_count_pairs"],1)
        self.assertEqual(identical["equal_count_and_identical_sample_values"],1)
        self.assertEqual(different["equal_count_but_different_sample_values"],1)
        self.assertNotEqual(identical,different)

    def test_refuse_forged_identity_count_and_vblank(self):
        for faulty in (
            log(handlers=3),log(identical=1),log(different=1),
            log(other=0),log(cross_identical=1),log(cross_other=1),
            log(vblanks=3),log(other=0xffffffff),
        ):
            with self.subTest(faulty=faulty),self.assertRaises(Refused):
                summarize(faulty,encode(sample()))

    def test_refuse_missing_duplicate_or_incomplete_log_status(self):
        good=log()
        for bad in ("",good+good,good.replace(" cross_different_count=0",""),
                    "VH115_IDENTITY_REFUSED\n"):
            with self.subTest(bad=bad),self.assertRaises(Refused):
                summarize(bad,encode(sample()))

    def test_keep_old_private_event_schema_without_raw_values(self):
        prior=(ROOT/"tools/verify_map02_v82_native_trace.py").read_text()
        self.assertNotIn("vh115",prior)
        source=(ROOT/"tools/map02_v115_sample_identity.c").read_text()
        self.assertNotIn("printf(",source)
        self.assertNotIn("hash",source.lower())
        self.assertIn("state.previous[i]==post[i]",source)

    def test_pinned_workflow_analyzes_native_log_not_only_jsonl_counts(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v115_identity_runtime",flow)
        self.assertIn("VH115_SAMPLE_IDENTITY_PASS",flow)
        self.assertIn("v115-sample-identity-summary.json",flow)
        self.assertIn("proof/private/v104-runtime.log",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
