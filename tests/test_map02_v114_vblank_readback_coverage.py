#!/usr/bin/env python3
"""v114: readback gaps and sampled-delta trends, never full-VRAM persistence."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from test_map02_v108_vblank_store_buckets import redistribute
from test_map02_v109_gp0_class_vblank_stores import five_classes
from test_map02_v111_sample_store_divergence import extended_polygon_pair
from test_map02_v112_unchanged_sample_runs import with_empty_interval_between_writers
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v111_sample_store_divergence import summarize as v111
from tools.summarize_map02_v113_vblank_outcome_transitions import summarize as v113
from tools.summarize_map02_v114_vblank_readback_coverage import summarize, METRICS


def reorder_polygon_readback_counts():
    base=extended_polygon_pair()
    polygons=[i for i,x in enumerate(base)
              if x["kind"]=="gp0_unai_handled" and x["value"]>>24==0x20]
    assert len(polygons)==2
    first,second=polygons
    base[first+1]["value"]=1
    base[second+1]["value"]=2
    # Both polygon callbacks must belong to the SAME v111 outcome class:
    # nonzero sampled delta WITH native 16-bit store attempts. Without
    # this, swapping deltas would legitimately alter older v111 summaries.
    base[second+2]["value"]=2
    base[second+3]["value"]=1
    other=[dict(item) for item in base]
    other[first+1]["value"]=2
    other[second+1]["value"]=1
    return base,other


class V114ReadbackCoverage(unittest.TestCase):
    def test_every_vblank_interval_has_explicit_sample_coverage(self):
        report=summarize(encode(five_classes()))
        self.assertEqual(report["emulator_vblank_edges"],4)
        self.assertEqual([x["observed_readbacks"] for x in report["intervals"]],
                         [0,2,1,2,0])
        self.assertEqual([x["changed_sample_points"] for x in report["intervals"]],
                         [0,1,2,1,0])
        self.assertEqual([x["coverage"] for x in report["intervals"]],[
            "no_observed_unai_readback","mixed_zero_and_nonzero_sample_deltas",
            "only_nonzero_sample_deltas","mixed_zero_and_nonzero_sample_deltas",
            "no_observed_unai_readback"])
        self.assertEqual(report["windows_without_any_observed_unai_readback"],0)
        self.assertEqual(report["longest_consecutive_between_vblank_windows_without_readbacks"],0)
        self.assertEqual([w["observed_readbacks"] for w in
                          report["between_vblank_observation_windows"]],[2,1,2])
        self.assertEqual(set(METRICS),set(report["intervals"][1])-
                         {"interval","coverage","unobserved_whole_vram_state"})
        self.assertTrue(report["no_readback_is_not_proof_of_no_vram_changes"])
        self.assertFalse(report["physical_PS1_vblank_verified"])

    def test_empty_frame_windows_are_blind_not_claimed_unchanged(self):
        report=summarize(encode(sample()))
        self.assertEqual(report["windows_without_any_observed_unai_readback"],2)
        self.assertEqual(report["longest_consecutive_between_vblank_windows_without_readbacks"],2)
        self.assertEqual([w["observation_coverage"] for w in
                          report["between_vblank_observation_windows"]],[
            "mixed_zero_and_nonzero_sample_deltas",
            "no_observed_unai_readback","no_observed_unai_readback"])
        self.assertTrue(all(w["no_readback_does_not_imply_unchanged_vram"]
                            for w in report["between_vblank_observation_windows"]))
        self.assertIsNone(report["nearest_observed_readbacks_around_vblank"][0][
            "prior_observed_changed_sample_points"])

    def test_three_empty_vblank_windows_and_four_crossed_edges(self):
        report=summarize(encode(redistribute()))
        self.assertEqual(report["windows_without_any_observed_unai_readback"],3)
        self.assertEqual(report["longest_consecutive_between_vblank_windows_without_readbacks"],3)
        self.assertEqual([w["observed_readbacks"] for w in
                          report["between_vblank_observation_windows"]],[0,0,0])
        self.assertEqual(report["readback_pair_observed_vblank_edges"],[1,1,1,1])
        self.assertEqual(report["cross_vblank_readback_change_count_trends"],[
            {"vblank_edges_crossed":4,"direction":"decreasing","pairs":1}])
        self.assertEqual([x["native_vblank_edges_between_observed_readbacks"]
                          for x in report["nearest_observed_readbacks_around_vblank"]],
                         [4,4,4,4])

    def test_empty_middle_window_between_native_write_observations(self):
        report=summarize(encode(with_empty_interval_between_writers()))
        self.assertEqual([w["observed_readbacks"] for w in
                          report["between_vblank_observation_windows"]],[2,0,3])
        self.assertEqual(report["windows_without_any_observed_unai_readback"],1)
        self.assertEqual(report["longest_consecutive_between_vblank_windows_without_readbacks"],1)
        self.assertEqual(report["nearest_observed_readbacks_around_vblank"][1][
            "native_vblank_edges_between_observed_readbacks"],2)
        self.assertEqual(report["nearest_observed_readbacks_around_vblank"][2][
            "native_vblank_edges_between_observed_readbacks"],2)

    def test_same_previous_class_and_outcome_counts_but_different_delta_trend(self):
        original,reordered=reorder_polygon_readback_counts()
        self.assertEqual(v111(encode(original)),v111(encode(reordered)))
        self.assertEqual(v113(encode(original)),v113(encode(reordered)))
        first=summarize(encode(original))
        second=summarize(encode(reordered))
        self.assertEqual([b["changed_sample_points"] for b in first["intervals"]],
                         [b["changed_sample_points"] for b in second["intervals"]])
        self.assertNotEqual(first["same_interval_readback_change_count_trends"],
                            second["same_interval_readback_change_count_trends"])
        self.assertNotEqual(first["nearest_observed_readbacks_around_vblank"][1][
            "prior_observed_changed_sample_points"],second[
            "nearest_observed_readbacks_around_vblank"][1][
            "prior_observed_changed_sample_points"])
        self.assertTrue(first["same_delta_count_is_not_proof_of_same_pixel_values"])

    def test_instrumented_writes_and_same_color_do_not_establish_pixel_state(self):
        report=summarize(encode(sample()))
        self.assertEqual(report["intervals"][1]["instrumented_16bit_store_attempts"],4)
        self.assertEqual(report["intervals"][1]["same_value_16bit_stores"],1)
        self.assertEqual(report["intervals"][1]["changed_sample_points"],1)
        self.assertTrue(report["only_24_sample_locations_per_handler"])
        self.assertTrue(all(i["unobserved_whole_vram_state"] for i in report["intervals"]))
        self.assertTrue(report["host_event_order_is_not_ps1_gpu_completion"])
        self.assertFalse(report["HD_replacement_approved"])

    def test_vblank_cannot_interrupt_renderer_readback_quartet(self):
        events=five_classes()
        mid=next(i for i,r in enumerate(events)
                 if r["kind"]=="vblank" and r["frame"]==11)
        edge=events.pop(mid)
        first=next(i for i,r in enumerate(events) if r["kind"]=="gp0_unai_handled")
        events.insert(first+2,edge)
        for idx,r in enumerate(events,1):
            r["seq"]=idx
        with self.assertRaises(Refused):
            summarize(encode(events))

    def test_forged_sample_cycles_counts_and_unsupported_command_refused(self):
        for kind,field,value in (
            ("unai_sample_delta","value",25),
            ("unai_sample_delta","frame",19),
            ("unai_store_count","cycle",200),
            ("unai_same_store_count","value",999),
            ("gp0_unai_handled","value",0x44000000),
        ):
            events=five_classes()
            next(x for x in events if x["kind"]==kind)[field]=value
            with self.subTest(kind=kind,field=field),self.assertRaises(Refused):
                summarize(encode(events))

    def test_aggregate_export_does_not_reveal_opcode_values_or_pixel_arrays(self):
        report=json.dumps(summarize(encode(five_classes())),sort_keys=True)
        for secret in ("0x02000000","0x20000000","0xe1000020",
                       "private_path","pixel_array","frame_buffer",
                       "gpu_dma_address","source_vram_pixel"):
            self.assertNotIn(secret,report)
        self.assertIn("pinned_pcsx_unai_sample_readback_coverage_only",report)

    def test_emulator_pipeline_uses_original_private_trace_public_aggregates(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v114_vblank_readback_coverage",workflow)
        self.assertIn("v114-vblank-readback-coverage.json",workflow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",workflow)
        self.assertIn("path: proof/public/",workflow)


if __name__=="__main__":
    unittest.main()
