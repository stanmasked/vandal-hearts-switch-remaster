#!/usr/bin/env python3
"""Strict five-handler/VBlank conservation and fabricated native return refusal."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from test_map02_v118_quadruplet_runtime import (
    two_handler_fixture,five_handler_fixture,quadruplets,EMPTY4
)
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v119_quintuplet_runtime import summarize


EMPTY5=[(0,0,0,0,0)]*5


def quintuplets(rows):
    return "VH119_QUINTUPLETS_PASS quints="+str(
        sum(sum(x) for x in rows))+" "+" ".join(
        f"g{i}={a},{b},{c},{d},{e}" for i,(a,b,c,d,e) in enumerate(rows))+"\n"


def existing_five():
    old,raw=five_handler_fixture()
    old+=quadruplets([EMPTY4[0],EMPTY4[0],(1,0,0,1),EMPTY4[0],EMPTY4[0]])
    return old,raw


class PrivateFiveHandlerBinding(unittest.TestCase):
    def test_two_handlers_have_no_five_handler_windows(self):
        original=two_handler_fixture()+quadruplets(EMPTY4)
        report=summarize(original+quintuplets(EMPTY5),encode(sample()))
        self.assertEqual(report["native_five_callback_windows"],0)
        self.assertEqual(report["total_return_to_four_back"],0)
        self.assertTrue(report["native_previous_samples_bounded_to_four_24_value_buffers"])

    def test_five_handlers_reconcile_exact_one_gap_two_quintuplet(self):
        original,raw=existing_five()
        rows=[EMPTY5[0],EMPTY5[0],(0,0,0,1,0),EMPTY5[0],EMPTY5[0]]
        result=summarize(original+quintuplets(rows),raw)
        self.assertEqual(result["native_five_callback_windows"],1)
        self.assertEqual(result["total_return_to_four_back"],1)
        self.assertEqual(result["bins_by_vblank_edges_oldest_to_newest"][2][
            "returned_to_four_back"],1)
        self.assertFalse(result["HD_replacement_approved"])
        self.assertFalse(result["raw_pixel_values_or_hashes_exported"])

    def test_global_total_correct_wrong_vblank_gap_rejected(self):
        original,raw=existing_five()
        wrong=[EMPTY5[0],(0,0,0,1,0),EMPTY5[0],EMPTY5[0],EMPTY5[0]]
        with self.assertRaises(Refused):
            summarize(original+quintuplets(wrong),raw)

    def test_other_outcome_classes_in_valid_gap_are_distinct(self):
        original,raw=existing_five()
        results=[]
        for col in range(5):
            data=list(EMPTY5)
            inside=[0]*5
            inside[col]=1
            data[2]=tuple(inside)
            response=summarize(original+quintuplets(data),raw)
            results.append(response["bins_by_vblank_edges_oldest_to_newest"][2])
        self.assertEqual(len({json.dumps(r,sort_keys=True) for r in results}),5)

    def test_missing_duplicate_incomplete_overflow_and_forged_counts_refused(self):
        original,raw=existing_five()
        correct=quintuplets([EMPTY5[0],EMPTY5[0],(0,0,0,1,0),
                            EMPTY5[0],EMPTY5[0]])
        attempts=[
            original,original+correct+correct,
            original+"VH119_QUINTUPLETS_PASS quints=1 g0=0\n",
            original+quintuplets(EMPTY5),
            original+quintuplets([(0,0,0,4294967296,0)]+EMPTY5[:4])
        ]
        for i,log in enumerate(attempts):
            with self.subTest(index=i),self.assertRaises(Refused):
                summarize(log,raw)

    def test_requires_previous_v118_private_evidence(self):
        with self.assertRaises(Refused):
            summarize(quintuplets(EMPTY5),encode(sample()))

    def test_aggregate_does_not_publish_opcode_pixel_or_fingerprint(self):
        old,raw=existing_five()
        report=summarize(old+quintuplets([
            EMPTY5[0],EMPTY5[0],(0,0,0,1,0),EMPTY5[0],EMPTY5[0]
        ]),raw)
        rendered=json.dumps(report,sort_keys=True)
        for secret in ('"pixels":','"pixel_value":','"hash":',
                       "0xe1000020","vram_address","private_jsonl"):
            self.assertNotIn(secret,rendered)
        self.assertTrue(report["actual_sample_values_compared_inside_native_process_only"])

    def test_full_pinned_emulator_verifies_actual_private_log(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v119_quintuplet_runtime",flow)
        self.assertIn("v119-quintuplet-summary.json",flow)
        self.assertIn("proof/private/v104-runtime.log",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
