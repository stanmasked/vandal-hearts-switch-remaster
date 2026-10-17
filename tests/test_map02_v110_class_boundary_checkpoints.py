#!/usr/bin/env python3
"""v110 native Unai class continuity across real emulator-VBlank event ordinals."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from test_map02_v109_gp0_class_vblank_stores import five_classes
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v109_gp0_class_vblank_stores import summarize as v109
from tools.summarize_map02_v110_class_boundary_checkpoints import summarize


class NativeVBlankBoundaryCheckpoints(unittest.TestCase):
    def test_independent_per_class_cumulative_native_store_checkpoints(self):
        audit=summarize(encode(five_classes()))
        self.assertEqual(audit["vblank_edges"],4)
        snaps=audit["snapshots_before_vblank"]
        self.assertEqual([s["vblank_ordinal"] for s in snaps],[1,2,3,4])
        self.assertEqual([
            sum(c["native_store_attempts"] for c in snap["cumulative_by_class"].values())
            for snap in snaps],[0,5,8,12])
        self.assertEqual([snap["cumulative_by_class"]["polygon_primitive"]["native_store_attempts"]
                          for snap in snaps],[0,2,2,2])
        self.assertEqual([snap["cumulative_by_class"]["line_primitive"]["native_store_attempts"]
                          for snap in snaps],[0,0,3,3])
        self.assertEqual(snaps[0]["last_prior_unai_class"],None)
        self.assertEqual(snaps[0]["first_later_unai_class"],"fill_vram")
        self.assertEqual(snaps[3]["last_prior_unai_class"],"gpu_state")
        self.assertEqual(snaps[3]["first_later_unai_class"],None)
        self.assertEqual(snaps[1]["last_prior_unai_class"],"polygon_primitive")
        self.assertEqual(snaps[1]["first_later_unai_class"],"line_primitive")
        self.assertEqual(snaps[1]["first_later_gap_vblank_edges"],1)
        self.assertFalse(audit["exact_gpu_cpu_timing_verified"])
        self.assertFalse(audit["retail_MAP02_verified"])
        self.assertFalse(audit["HD_replacement_approved"])

    def test_adjacent_class_transitions_are_bucket_scoped(self):
        audit=summarize(encode(five_classes()))
        within=audit["intra_interval_transitions"]
        self.assertEqual([x["adjacent_handler_pairs"] for x in within],[0,1,0,1,0])
        self.assertEqual(within[1]["class_transitions"],[
            {"from_class":"fill_vram","to_class":"polygon_primitive","pairs":1}
        ])
        self.assertEqual(within[3]["class_transitions"],[
            {"from_class":"rectangle_sprite_primitive","to_class":"gpu_state","pairs":1}
        ])
        self.assertEqual(audit["handler_pairs_crossing_one_or_more_vblank_edges"],2)
        self.assertEqual(audit["observed_unai_handlers"],5)

    def test_same_histogram_different_execution_order_has_different_transitions(self):
        initial=five_classes()
        # The two complete first-interval four-record groups are swapped.
        start=next(i for i,r in enumerate(initial) if r["kind"]=="gp0_unai_handled")
        swapped=[dict(r) for r in initial]
        swapped[start:start+8]=swapped[start+4:start+8]+swapped[start:start+4]
        for seq,item in enumerate(swapped,1):item["seq"]=seq
        before=v109(encode(initial))
        after=v109(encode(swapped))
        self.assertEqual(before["class_totals"],after["class_totals"])
        self.assertEqual(before["intervals"],after["intervals"])
        original=summarize(encode(initial))
        changed=summarize(encode(swapped))
        self.assertEqual(original["snapshots_before_vblank"][1]["cumulative_by_class"],
                         changed["snapshots_before_vblank"][1]["cumulative_by_class"])
        self.assertEqual(changed["intra_interval_transitions"][1]["class_transitions"],[
            {"from_class":"polygon_primitive","to_class":"fill_vram","pairs":1}
        ])
        self.assertNotEqual(original["intra_interval_transitions"],
                            changed["intra_interval_transitions"])

    def test_empty_middle_and_late_intervals_keep_snapshot_counters_stable(self):
        proof=summarize(encode(sample()))
        counts=[sum(c["native_store_attempts"] for c in e["cumulative_by_class"].values())
                for e in proof["snapshots_before_vblank"]]
        self.assertEqual(counts,[0,4,4,4])
        self.assertEqual(proof["handler_pairs_crossing_one_or_more_vblank_edges"],0)
        self.assertEqual(proof["intra_interval_transitions"][1]["adjacent_handler_pairs"],1)
        self.assertEqual(proof["snapshots_before_vblank"][2]["first_later_unai_class"],None)

    def test_all_handler_quartets_must_be_wholly_on_one_side_of_vblank(self):
        rows=five_classes()
        at=next(i for i,r in enumerate(rows) if r["kind"]=="vblank" and r["frame"]==11)
        boundary=rows.pop(at)
        first=next(i for i,r in enumerate(rows) if r["kind"]=="gp0_unai_handled")
        rows.insert(first+2,boundary)
        for seq,item in enumerate(rows,1):item["seq"]=seq
        with self.assertRaises(Refused):
            summarize(encode(rows))

    def test_forged_native_counts_and_unsupported_commands_refused(self):
        for field,value in (("value",0xffffffff),("cycle",123)):
            rows=five_classes()
            r=next(item for item in rows if item["kind"]=="unai_store_count")
            r[field]=value
            with self.subTest(field=field),self.assertRaises(Refused):
                summarize(encode(rows))
        rows=five_classes()
        next(r for r in rows if r["kind"]=="gp0_unai_handled")["value"]=0x44000000
        with self.assertRaises(Refused):
            summarize(encode(rows))

    def test_private_opcodes_and_cycle_values_never_exposed_in_summary(self):
        result=json.dumps(summarize(encode(five_classes())),sort_keys=True)
        for secret in ("0x20000000","0xe1000020","vram_pixel",
                       "source_address","frame_number","cycle_number",
                       "private_path","gpu_dma_source"):
            self.assertNotIn(secret,result)
        self.assertIn("host_callback_append_order_only",result)

    def test_pinned_gcc_clang_workflow_writes_only_public_aggregate(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v110_class_boundary_checkpoints",flow)
        self.assertIn("v110-boundary-class-summary.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
