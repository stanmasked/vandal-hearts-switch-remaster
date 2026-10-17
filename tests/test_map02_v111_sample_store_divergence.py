#!/usr/bin/env python3
"""v111 synthetic VRAM sample/store disagreement, by class and VBlank."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]

from test_map02_v85_native_stores import sample, encode
from test_map02_v109_gp0_class_vblank_stores import five_classes
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v109_gp0_class_vblank_stores import summarize as v109
from tools.summarize_map02_v110_class_boundary_checkpoints import summarize as v110
from tools.summarize_map02_v111_sample_store_divergence import (
    summarize, classify_case, CASES, COUNTS,
)


def extended_polygon_pair():
    rows=five_classes()
    # Inject another complete POLYGON handler before the second VBlank.
    second=next(i for i,r in enumerate(rows)
                if r["kind"]=="vblank" and r["frame"]==11)
    extra=[
        dict(kind="gp0_unai_handled",value=0x20000000,cycle=0,frame=0),
        dict(kind="unai_sample_delta",value=1,cycle=0,frame=0),
        dict(kind="unai_store_count",value=0,cycle=0,frame=0),
        dict(kind="unai_same_store_count",value=0,cycle=0,frame=0),
    ]
    rows[second:second]=extra
    for seq,r in enumerate(rows,1):
        r["seq"]=seq
    return rows


def rebind_polygon_sample_to_stores(rows):
    moved=[dict(r) for r in rows]
    polygons=[i for i,r in enumerate(moved)
              if r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x20]
    assert len(polygons)==2
    first,second=polygons
    # Same native totals, sample totals, handler counts and callback order.
    # Only WHICH sample-delta observation accompanies the store changes.
    moved[first+2]["value"]=0
    moved[first+3]["value"]=0
    moved[second+2]["value"]=2
    moved[second+3]["value"]=1
    return moved


class NativeSampleStoreDivergence(unittest.TestCase):
    def test_four_outcomes_classified_without_equating_zero_delta_with_zero_writes(self):
        proof=summarize(encode(five_classes()))
        totals=proof["overall_case_totals"]
        self.assertEqual(tuple(totals),CASES)
        self.assertEqual([totals[c]["handlers"] for c in CASES],[1,1,0,3])
        self.assertEqual(totals[CASES[1]]["native_store_attempts"],2)
        self.assertEqual(totals[CASES[1]]["same_value_native_stores"],1)
        self.assertEqual(totals[CASES[1]]["changed_value_native_stores"],1)
        self.assertEqual(totals[CASES[0]]["native_store_attempts"],0)
        self.assertEqual(proof["totals_by_class_and_case"]["polygon_primitive"][CASES[1]]["handlers"],1)
        self.assertEqual(proof["before_vblank_cumulative_sample_unchanged_stores"][1][
            "sample_unchanged_with_stores_cumulative_by_class"]["polygon_primitive"][
            "native_stores_with_unchanged_samples"],2)
        self.assertTrue(proof["zero_sample_delta_does_not_mean_no_VRAM_writes"])
        self.assertFalse(proof["HD_replacement_approved"])
        self.assertFalse(proof["physical_ps1_vblank_verified"])

    def test_no_covered_pixel_store_may_still_coexist_with_sample_difference(self):
        rows=five_classes()
        line=next(i for i,r in enumerate(rows)
                  if r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x40)
        rows[line+2]["value"]=0
        rows[line+3]["value"]=0
        proof=summarize(encode(rows))
        self.assertEqual(proof["overall_case_totals"][CASES[2]]["handlers"],1)
        self.assertEqual(proof["totals_by_class_and_case"]["line_primitive"][CASES[2]][
            "changed_sample_points"],2)
        self.assertTrue(proof[
            "sample_change_without_instrumented_store_is_not_proof_of_no_write"])

    def test_same_v109_v110_class_histogram_can_hide_different_sample_store_binding(self):
        original=extended_polygon_pair()
        changed=rebind_polygon_sample_to_stores(original)
        baseline=v109(encode(original))
        alter=v109(encode(changed))
        self.assertEqual(baseline["intervals"],alter["intervals"])
        self.assertEqual(baseline["class_totals"],alter["class_totals"])
        before=v110(encode(original))
        after=v110(encode(changed))
        self.assertEqual(before,after)
        initial=summarize(encode(original))
        new=summarize(encode(changed))
        self.assertEqual(initial["overall_case_totals"][CASES[1]]["handlers"],1)
        self.assertEqual(new["overall_case_totals"][CASES[1]]["handlers"],0)
        self.assertEqual(initial["overall_case_totals"][CASES[2]]["handlers"],1)
        self.assertEqual(new["overall_case_totals"][CASES[2]]["handlers"],0)
        self.assertEqual(new["overall_case_totals"][CASES[3]]["handlers"],
                         initial["overall_case_totals"][CASES[3]]["handlers"]+1)
        self.assertNotEqual(initial["per_vblank_class_cases"],
                            new["per_vblank_class_cases"])

    def test_clean_state_command_remains_no_writes_and_old_v85_fixture_supported(self):
        proof=summarize(encode(sample()))
        state=proof["totals_by_class_and_case"]["gpu_state"]
        self.assertEqual(state[CASES[0]]["handlers"],1)
        self.assertEqual(sum(state[c]["native_store_attempts"] for c in CASES),0)
        self.assertEqual(proof["overall_case_totals"][CASES[3]]["handlers"],1)

    def test_four_vblank_prefix_snapshots_match_independent_native_store_counts(self):
        proof=summarize(encode(five_classes()))
        prefix=proof["before_vblank_cumulative_sample_unchanged_stores"]
        self.assertEqual([p["vblank_ordinal"] for p in prefix],[1,2,3,4])
        self.assertEqual([
            sum(c["native_stores_with_unchanged_samples"]
                for c in p["sample_unchanged_with_stores_cumulative_by_class"].values())
            for p in prefix],[0,2,2,2])
        self.assertEqual([
            sum(c["changed_value_stores_with_unchanged_samples"]
                for c in p["sample_unchanged_with_stores_cumulative_by_class"].values())
            for p in prefix],[0,1,1,1])

    def test_refuse_vblank_inside_handler_store_quartet(self):
        events=five_classes()
        edge=next(i for i,r in enumerate(events)
                  if r["kind"]=="vblank" and r["frame"]==11)
        record=events.pop(edge)
        first=next(i for i,r in enumerate(events)
                   if r["kind"]=="gp0_unai_handled")
        events.insert(first+2,record)
        for seq,row in enumerate(events,1):
            row["seq"]=seq
        with self.assertRaises(Refused):
            summarize(encode(events))

    def test_refuse_invalid_store_attempts_forged_samples_and_opcode_gaps(self):
        for field,value in (("value",0xffffffff),("cycle",123)):
            events=five_classes()
            next(r for r in events if r["kind"]=="unai_store_count")[field]=value
            with self.subTest(field=field),self.assertRaises(Refused):
                summarize(encode(events))
        events=five_classes()
        next(r for r in events if r["kind"]=="unai_sample_delta")["value"]=25
        with self.assertRaises(Refused):
            summarize(encode(events))
        events=five_classes()
        next(r for r in events if r["kind"]=="gp0_unai_handled")["value"]=0x44000000
        with self.assertRaises(Refused):
            summarize(encode(events))

    def test_all_cases_conserve_handlers_sample_deltas_and_16bit_stores(self):
        report=summarize(encode(extended_polygon_pair()))
        audit=v109(encode(extended_polygon_pair()))
        self.assertEqual(sum(x["handlers"] for x in report["overall_case_totals"].values()),
                         sum(c["handlers"] for c in audit["class_totals"].values()))
        for metric in COUNTS:
            self.assertEqual(sum(item[metric] for item in report["overall_case_totals"].values()),
                             sum(item[metric] for item in audit["class_totals"].values()))

    def test_privacy_of_public_report(self):
        raw=json.dumps(summarize(encode(five_classes())),sort_keys=True)
        for forbidden in ("0x02000000","0x20000000","0x40000000",
                          "0xe1000020","private_path","VRAM_pixel_value",
                          "source_address","cpu_cycles","mips_instruction"):
            self.assertNotIn(forbidden,raw)
        self.assertIn("pinned_pcsx_synthetic_unai_sampled_VRAM_vs_native_stores",raw)

    def test_pinned_ci_audits_private_trace_and_uploads_aggregate_only(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v111_sample_store_divergence",flow)
        self.assertIn("v111-sample-store-divergence.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
