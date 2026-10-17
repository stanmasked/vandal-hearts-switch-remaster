#!/usr/bin/env python3
"""v112 synthetic native unchanged-sample runs and VBlank edge conservation."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample, encode
from test_map02_v109_gp0_class_vblank_stores import five_classes
from test_map02_v111_sample_store_divergence import (
    extended_polygon_pair, rebind_polygon_sample_to_stores
)
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v109_gp0_class_vblank_stores import summarize as v109
from tools.summarize_map02_v110_class_boundary_checkpoints import summarize as v110
from tools.summarize_map02_v112_unchanged_sample_runs import summarize


def consecutive_writers():
    events=five_classes()
    # Fill/polygon/line each write, while all 24 sampled points stay equal.
    # Rectangle changes a sampled point so v84's mixed fixture remains valid.
    for item in events:
        if item["kind"]=="gp0_unai_handled" and item["value"]>>24 in (0x02,0x40):
            event=events.index(item)
            events[event+1]["value"]=0
    return events


def with_empty_interval_between_writers():
    events=consecutive_writers()
    # Move frame-12 VBlank immediately after frame-11 VBlank.
    # Existing frame/cycle values remain in strictly ascending order.
    mid=next(i for i,r in enumerate(events)
             if r["kind"]=="vblank" and r["frame"]==12)
    edge=events.pop(mid)
    earlier=next(i for i,r in enumerate(events)
                 if r["kind"]=="vblank" and r["frame"]==11)
    events.insert(earlier+1,edge)
    for n,r in enumerate(events,1):
        r["seq"]=n
    return events


class UnchangedSampleRuns(unittest.TestCase):
    def test_three_consecutive_real_store_attempts_straddle_vblank(self):
        report=summarize(encode(consecutive_writers()))
        self.assertEqual(report["qualifying_unai_handlers"],3)
        self.assertEqual(report["qualifying_runs"],1)
        self.assertEqual(report["multi_handler_runs"],1)
        self.assertEqual(report["longest_consecutive_qualifying_handlers"],3)
        self.assertEqual(report["intra_interval_adjacent_qualifying_pairs"],
                         [0,1,0,0,0])
        self.assertEqual(report["adjacent_qualifying_pairs_crossing_vblank"],1)
        self.assertEqual(report["vblank_edges_crossed_by_consecutive_qualifying_pairs"],
                         [0,1,0,0])
        self.assertEqual(report["total_qualifying_native_stores"][
            "native_store_attempts"],8)
        self.assertEqual(report["total_qualifying_native_stores"][
            "same_value_native_stores"],2)
        self.assertEqual(report["total_qualifying_native_stores"][
            "changed_value_native_stores"],6)
        self.assertTrue(report["zero_sample_delta_is_not_whole_VRAM_unchanged"])
        self.assertTrue(report["crossing_vblank_does_not_establish_VRAM_persistence"])
        self.assertFalse(report["original_retail_MAP02_verified"])

    def test_prefix_native_store_snapshots_remain_conserved_across_vblank(self):
        report=summarize(encode(consecutive_writers()))
        snapshots=report["before_vblank_native_store_prefixes"]
        self.assertEqual([x["vblank_ordinal"] for x in snapshots],[1,2,3,4])
        self.assertEqual([
            sum(c["native_store_attempts"]
                for c in x["cumulative_unchanged_sample_stores_by_class"].values())
            for x in snapshots],[0,5,8,8])
        self.assertEqual([
            x["run_of_consecutive_qualifying_handlers_spans_edge"]
            for x in snapshots],[False,True,False,False])

    def test_one_qualifying_pair_can_span_two_empty_vblank_intervals(self):
        report=summarize(encode(with_empty_interval_between_writers()))
        self.assertEqual(report["qualifying_unai_handlers"],3)
        self.assertEqual(report["qualifying_runs"],1)
        self.assertEqual(report["adjacent_qualifying_pairs_crossing_vblank"],1)
        self.assertEqual(report["vblank_edges_crossed_by_consecutive_qualifying_pairs"],
                         [0,1,1,0])
        self.assertEqual(report["intra_interval_adjacent_qualifying_pairs"],
                         [0,1,0,0,0])
        totals=[
            sum(c["native_store_attempts"]
                for c in snap["cumulative_unchanged_sample_stores_by_class"].values())
            for snap in report["before_vblank_native_store_prefixes"]]
        self.assertEqual(totals,[0,5,5,8])
        self.assertTrue(report["crossing_vblank_does_not_establish_VRAM_persistence"])

    def test_intervening_nonqualifying_unai_handler_breaks_run(self):
        rows=consecutive_writers()
        first_polygon=next(i for i,r in enumerate(rows)
                           if r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x20)
        rows[first_polygon+1]["value"]=1
        report=summarize(encode(rows))
        self.assertEqual(report["qualifying_unai_handlers"],2)
        self.assertEqual(report["qualifying_runs"],2)
        self.assertEqual(report["multi_handler_runs"],0)
        self.assertEqual(report["adjacent_qualifying_pairs_crossing_vblank"],0)
        self.assertEqual(report["vblank_edges_crossed_by_consecutive_qualifying_pairs"],
                         [0,0,0,0])

    def test_gp1_event_between_unai_callbacks_not_a_renderer_handler(self):
        rows=consecutive_writers()
        second=next(i for i,r in enumerate(rows)
                    if r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x20)
        rows.insert(second,dict(kind="gp1_mmio",value=0x01000000,frame=0,cycle=120))
        for i,r in enumerate(rows,1):r["seq"]=i
        report=summarize(encode(rows))
        self.assertEqual(report["qualifying_runs"],1)
        self.assertEqual(report["longest_consecutive_qualifying_handlers"],3)
        self.assertEqual(report["observed_unai_handlers"],5)
        self.assertFalse(report["emulated_gpu_completion_cycles_proven"])

    def test_rebinding_same_class_samples_and_native_stores_changes_runs(self):
        rows=extended_polygon_pair()
        moved=rebind_polygon_sample_to_stores(rows)
        self.assertEqual(v109(encode(rows)),v109(encode(moved)))
        self.assertEqual(v110(encode(rows)),v110(encode(moved)))
        first=summarize(encode(rows))
        second=summarize(encode(moved))
        self.assertEqual(first["qualifying_unai_handlers"],1)
        self.assertEqual(second["qualifying_unai_handlers"],0)
        self.assertNotEqual(first["total_qualifying_native_stores"],
                            second["total_qualifying_native_stores"])

    def test_original_v85_fixture_with_no_qualifying_handlers(self):
        result=summarize(encode(sample()))
        self.assertEqual(result["qualifying_unai_handlers"],0)
        self.assertEqual(result["qualifying_runs"],0)
        self.assertEqual(result["longest_consecutive_qualifying_handlers"],0)
        self.assertEqual(result["vblank_edges_crossed_by_consecutive_qualifying_pairs"],
                         [0,0,0,0])

    def test_refuse_split_quartet_and_bad_instrumented_store_counters(self):
        records=consecutive_writers()
        edge=next(i for i,r in enumerate(records)
                  if r["kind"]=="vblank" and r["frame"]==11)
        item=records.pop(edge)
        first=next(i for i,r in enumerate(records) if r["kind"]=="gp0_unai_handled")
        records.insert(first+1,item)
        for i,r in enumerate(records,1):r["seq"]=i
        with self.assertRaises(Refused):summarize(encode(records))
        for mutate in ("same_exceeds_total","sample_exceeds_24","forged_store_cycle"):
            records=consecutive_writers()
            index=next(i for i,r in enumerate(records) if r["kind"]=="gp0_unai_handled")
            if mutate=="same_exceeds_total":records[index+3]["value"]=5
            if mutate=="sample_exceeds_24":records[index+1]["value"]=25
            if mutate=="forged_store_cycle":records[index+2]["cycle"]=99
            with self.subTest(mutate=mutate),self.assertRaises(Refused):
                summarize(encode(records))

    def test_public_aggregate_never_contains_raw_gp0_or_vram_data(self):
        raw=json.dumps(summarize(encode(consecutive_writers())),sort_keys=True)
        for bad in ("0x02000000","0x20000000","0xe1000020",
                    "private_path","gpu_dma_source","raw_vram_value",
                    "timestamp_cpu_cycles"):
            self.assertNotIn(bad,raw)
        self.assertIn("pinned_pcsx_synthetic_unai_zero_sample_delta_native_store_runs",raw)

    def test_full_pinned_emulator_runs_audit_and_only_uploads_public_directory(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v112_unchanged_sample_runs",flow)
        self.assertIn("v112-unchanged-sample-runs.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
