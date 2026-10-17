#!/usr/bin/env python3
"""Strict private v118 four-handler/VBlank population reconciliation."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from test_map02_v109_gp0_class_vblank_stores import five_classes
from test_map02_v115_identity_runtime import log as v115log
from test_map02_v116_gap_runtime import gap_line
from test_map02_v117_triplet_runtime import triples,EMPTY
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v118_quadruplet_runtime import summarize


def quadruplets(rows):
    return "VH118_QUADRUPLETS_PASS quads="+str(
        sum(sum(row) for row in rows))+" "+" ".join(
        f"g{i}={a},{b},{c},{d}" for i,(a,b,c,d) in enumerate(rows))+"\n"


EMPTY4=[(0,0,0,0)]*5


def two_handler_fixture():
    return (v115log()+
            gap_line([(0,0,1)]+EMPTY[:4])+
            triples(EMPTY))


def five_handler_fixture():
    stream=five_classes()
    polygon=next(i for i,r in enumerate(stream)
                 if r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x20)
    stream[polygon+1]["value"]=1
    prior=(v115log(handlers=5,identical=1,other=3,cross_other=2)+
           gap_line([(1,0,1),(0,0,2)]+EMPTY[:3])+
           triples([(0,0,0),(0,0,2),(0,1,0)]+EMPTY[:2]))
    return prior,encode(stream)


class FourPrivateWitness(unittest.TestCase):
    def test_two_observed_handlers_produce_no_four_handler_windows(self):
        report=summarize(two_handler_fixture()+quadruplets(EMPTY4),encode(sample()))
        self.assertEqual(report["native_four_callback_windows"],0)
        self.assertEqual(report["total_return_to_three_back"],0)
        self.assertTrue(report["quadruplet_gap_counts_verified_against_original_private_trace"])
        self.assertFalse(report["raw_pixel_values_or_hashes_exported"])

    def test_five_handlers_have_two_four_handler_windows_both_crossing_two_vblanks(self):
        prior,events=five_handler_fixture()
        report=summarize(prior+quadruplets(
            [EMPTY4[0],EMPTY4[0],(1,0,0,1),EMPTY4[0],EMPTY4[0]]),events)
        self.assertEqual(report["native_four_callback_windows"],2)
        self.assertEqual(report["bins_by_vblank_edges_oldest_to_newest"][2][
            "same_as_previous"],1)
        self.assertEqual(report["total_different_from_all_three"],1)
        self.assertFalse(report["HD_replacement_approved"])

    def test_return_to_three_back_can_only_be_claimed_in_correct_gap(self):
        prior,events=five_handler_fixture()
        report=summarize(prior+quadruplets(
            [EMPTY4[0],EMPTY4[0],(0,0,1,1),EMPTY4[0],EMPTY4[0]]),events)
        self.assertEqual(report["total_return_to_three_back"],1)
        misplaced=[EMPTY4[0],(0,0,1,0),(0,0,0,1),EMPTY4[0],EMPTY4[0]]
        with self.assertRaises(Refused):
            summarize(prior+quadruplets(misplaced),events)

    def test_wrong_total_duplicate_status_missing_or_overflow_refused(self):
        prior,events=five_handler_fixture()
        valid=quadruplets([EMPTY4[0],EMPTY4[0],(1,0,1,0),
                           EMPTY4[0],EMPTY4[0]])
        examples=[
            prior,prior+valid+valid,
            prior+"VH118_QUADRUPLETS_PASS quads=2 g0=0\n",
            prior+quadruplets(EMPTY4),
            prior+quadruplets([(0,0,4294967296,0)]+EMPTY4[:4]),
        ]
        for idx,case in enumerate(examples):
            with self.subTest(idx=idx),self.assertRaises(Refused):
                summarize(case,events)

    def test_no_raw_gpu_word_pixel_values_or_fingerprint_in_public_output(self):
        report=summarize(two_handler_fixture()+quadruplets(EMPTY4),encode(sample()))
        serial=json.dumps(report,sort_keys=True)
        for secret in ('"pixels":','"pixel_value":','"hash":',
                       "0xe1000020","vram_address","private_jsonl"):
            self.assertNotIn(secret,serial)
        self.assertTrue(report["only_native_process_compares_actual_24_values"])

    def test_original_v117_native_log_still_required(self):
        with self.assertRaises(Refused):
            summarize(v115log()+quadruplets(EMPTY4),encode(sample()))

    def test_pinned_full_emulator_audits_private_runtime_and_journal(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v118_quadruplet_runtime",workflow)
        self.assertIn("v118-quadruplet-summary.json",workflow)
        self.assertIn("proof/private/v104-runtime.log",workflow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",workflow)
        self.assertIn("path: proof/public/",workflow)


if __name__=="__main__":
    unittest.main()
