#!/usr/bin/env python3
"""v108: deterministic ordinal VBlank store buckets and fail-closed regressions."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v108_vblank_store_buckets import summarize, LABELS, METRICS


def redistribute():
    items=sample()
    # One Unai handler before the first VBlank, the other after the last.
    out=[items[0], *items[2:6], items[1], items[10],
         *items[11:14], *items[6:10]]
    for index,e in enumerate(out,1):
        e["seq"]=index
    return out


class OrdinalBuckets(unittest.TestCase):
    def test_native_stores_and_inputs_conserved_in_one_interval(self):
        report=summarize(encode(sample()))
        self.assertEqual([e["label"] for e in report["buckets"]],list(LABELS))
        self.assertEqual([e["unai_handlers"] for e in report["buckets"]],
                         [0,2,0,0,0])
        middle=report["buckets"][1]
        self.assertEqual(middle["native_store_attempts"],4)
        self.assertEqual(middle["same_value_native_stores"],1)
        self.assertEqual(middle["changed_value_native_stores"],3)
        self.assertEqual(middle["changed_sample_points"],1)
        self.assertEqual([e["gp1_mmio_inputs"] for e in report["buckets"]],
                         [1,1,0,0,0])
        self.assertEqual(report["totals"]["unai_handlers"],2)
        self.assertEqual(set(report["totals"]),set(METRICS))
        self.assertFalse(report["physical_PS1_verified"])
        self.assertFalse(report["HD_replacement_approved"])
        self.assertFalse(report["vblank_cpu_cycle_accurate_gpu_completion"])

    def test_pre_first_and_post_last_buckets_with_separate_native_writes(self):
        report=summarize(encode(redistribute()))
        self.assertEqual([e["unai_handlers"] for e in report["buckets"]],
                         [1,0,0,0,1])
        self.assertEqual([e["native_store_attempts"] for e in report["buckets"]],
                         [4,0,0,0,0])
        self.assertEqual(report["buckets"][4]["sampled_unchanged_handlers"],1)
        self.assertEqual(report["buckets"][0]["sampled_changed_handlers"],1)
        self.assertEqual(report["totals"]["gp1_mmio_inputs"],2)

    def test_gpu_dma2_is_input_only_and_never_an_unai_write(self):
        events=sample()
        events.insert(1,dict(kind="gpu_dma2_start",value=0x1000,
                             seq=0,cycle=50,frame=0))
        for i,e in enumerate(events,1):e["seq"]=i
        proof=summarize(encode(events))
        self.assertEqual(proof["totals"]["gpu_dma2_start_inputs"],1)
        self.assertEqual(proof["totals"]["native_store_attempts"],4)
        self.assertEqual(proof["buckets"][0]["gpu_dma2_start_inputs"],1)

    def test_refuse_nonadjacent_readback_or_store_group(self):
        for offset in (3,4,5):
            events=sample()
            events[offset]["kind"]="gp1_mmio"
            with self.subTest(offset=offset),self.assertRaises(Refused):
                summarize(encode(events))

    def test_refuse_vblank_between_handler_and_native_write_observations(self):
        events=sample()
        item=events.pop(11)
        events.insert(4,item)
        for n,e in enumerate(events,1):e["seq"]=n
        with self.assertRaises(Refused):summarize(encode(events))

    def test_refuse_forged_gpu_timestamp_or_sample_count(self):
        for index,field,value in ((2,"cycle",201),(3,"frame",11),
                                  (3,"value",25),(5,"value",5),
                                  (12,"frame",9)):
            events=sample()
            events[index][field]=value
            with self.subTest(index=index,field=field),self.assertRaises(Refused):
                summarize(encode(events))

    def test_no_opcode_words_coordinates_cycles_or_raw_bytes_in_public_report(self):
        report=summarize(encode(sample()))
        raw=json.dumps(report,sort_keys=True)
        for secret in ("0x600000ff","0xe1000020","gp0_opcode","pixel_address",
                       "cpu_cycle","private_path","sha256"):
            if secret=="cpu_cycle":
                # Explicit negative caveat in grouping is intentional.
                self.assertIn("no_gpu_cpu_cycle_or_frame_inference",raw)
            else:
                self.assertNotIn('"'+secret+'":',raw)
        self.assertEqual(report["scope"],
                         "pinned_pcsx_synthetic_unai_event_append_order")

    def test_pinned_host_workflow_runs_this_audit_without_public_trace(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v108_vblank_store_buckets",flow)
        self.assertIn("v108-vblank-store-summary.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
