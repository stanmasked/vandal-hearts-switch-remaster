#!/usr/bin/env python3
"""v109: synthetic five-class GP0/native Unai-store ordinal regressions."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]

from test_map02_v85_native_stores import sample, encode
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v108_vblank_store_buckets import summarize as v108
from tools.summarize_map02_v109_gp0_class_vblank_stores import (
    summarize, classify, CLASSES,
)


def five_classes():
    records=[("gp1_mmio",0xe1000020,80,0),
             ("vblank",0,100,10)]
    def emit(command,sample_change,stores,same):
        records.extend([
            ("gp0_unai_handled",command,0,0),
            ("unai_sample_delta",sample_change,0,0),
            ("unai_store_count",stores,0,0),
            ("unai_same_store_count",same,0,0)])
    emit(0x02000000,1,3,1)
    emit(0x20000000,0,2,1)
    records.append(("vblank",0,200,11))
    emit(0x40000000,2,3,0)
    records.append(("vblank",0,300,12))
    emit(0x60000000,1,4,2)
    emit(0xe1000020,0,0,0)
    records.extend([("gp1_mmio",0x01000000,310,0),
                    ("vblank",0,400,13)])
    return [dict(kind=kind,seq=i+1,value=value,cycle=cycle,frame=frame)
            for i,(kind,value,cycle,frame) in enumerate(records)]


class OpcodeClasses(unittest.TestCase):
    def test_opcode_dispatch_boundaries_and_unai_gaps(self):
        for word,expected in (
            (0x02000000,"fill_vram"),
            (0x20000000,"polygon_primitive"),
            (0x3f000000,"polygon_primitive"),
            (0x40000000,"line_primitive"),
            (0x43000000,"line_primitive"),
            (0x48000000,"line_primitive"),
            (0x53000000,"line_primitive"),
            (0x58000000,"line_primitive"),
            (0x5f000000,"line_primitive"),
            (0x60000000,"rectangle_sprite_primitive"),
            (0x6b000000,"rectangle_sprite_primitive"),
            (0x70000000,"rectangle_sprite_primitive"),
            (0x7f000000,"rectangle_sprite_primitive"),
            (0xe1000000,"gpu_state"),
            (0xe6000000,"gpu_state"),
        ):
            with self.subTest(word=word):
                self.assertEqual(classify(word),expected)
        for word in (0x01000000,0x44000000,0x47000000,0x54000000,
                     0x57000000,0x6c000000,0x6f000000,0xe7000000):
            with self.subTest(invalid=word),self.assertRaises(Refused):
                classify(word)

    def test_five_classes_account_for_full_native_store_totals(self):
        rows=five_classes()
        report=summarize(encode(rows))
        earlier=v108(encode(rows))
        self.assertEqual(tuple(report["class_totals"]),CLASSES)
        self.assertEqual([b["interval"] for b in report["intervals"]],
                         [b["label"] for b in earlier["buckets"]])
        self.assertEqual([sum(c["handlers"] for c in b["classes"].values())
                          for b in report["intervals"]],[0,2,1,2,0])
        for name in CLASSES:
            self.assertEqual(report["class_totals"][name]["handlers"],1)
        self.assertEqual([report["class_totals"][name]["native_store_attempts"]
                          for name in CLASSES],[3,2,3,4,0])
        self.assertEqual(sum(x["native_store_attempts"]
                             for x in report["class_totals"].values()),
                         earlier["totals"]["native_store_attempts"])
        self.assertEqual(sum(x["same_value_native_stores"]
                             for x in report["class_totals"].values()),
                         earlier["totals"]["same_value_native_stores"])
        self.assertEqual(report["class_totals"]["gpu_state"]["handlers"],1)
        self.assertTrue(report["gpu_state_command_store_attempts_refused"])
        self.assertFalse(report["physical_ps1_raster_timing_verified"])
        self.assertFalse(report["HD_replacement_approved"])

    def test_state_command_cannot_report_instrumented_pixel_write(self):
        items=five_classes()
        index=next(i for i,e in enumerate(items)
                   if e["kind"]=="gp0_unai_handled" and e["value"]>>24==0xe1)
        items[index+2]["value"]=1
        with self.assertRaises(Refused):summarize(encode(items))

    def test_class_boundary_changes_are_detected_by_reconciliation(self):
        data=five_classes()
        # Swapping the first two command types preserves counts but moves
        # native store provenance from fill to polygon, which must be visible.
        fill=next(e for e in data if e["kind"]=="gp0_unai_handled")
        fill["value"]=0x20000000
        proof=summarize(encode(data))
        self.assertEqual(proof["class_totals"]["fill_vram"]["handlers"],0)
        self.assertEqual(proof["class_totals"]["polygon_primitive"]["handlers"],2)

    def test_refuse_missing_samples_or_interleaved_vblank(self):
        for index in (1,2,3):
            items=five_classes()
            first=next(i for i,e in enumerate(items)
                       if e["kind"]=="gp0_unai_handled")
            items[first+index]["kind"]="gp1_mmio"
            with self.subTest(index=index),self.assertRaises(Refused):
                summarize(encode(items))
        items=five_classes()
        first=next(i for i,e in enumerate(items) if e["kind"]=="gp0_unai_handled")
        edge=next(i for i,e in enumerate(items)
                  if e["kind"]=="vblank" and e["frame"]==11)
        item=items.pop(edge)
        items.insert(first+2,item)
        for i,e in enumerate(items,1):e["seq"]=i
        with self.assertRaises(Refused):summarize(encode(items))

    def test_forged_timestamps_and_opcode_gaps_refused(self):
        for opcode in (0x44000000,0x54000000,0x6f000000,0xe7000000):
            with self.subTest(opcode=opcode):
                rows=five_classes()
                next(e for e in rows if e["kind"]=="gp0_unai_handled")["value"]=opcode
                with self.assertRaises(Refused):summarize(encode(rows))
        rows=five_classes()
        next(e for e in rows if e["kind"]=="unai_store_count")["cycle"]=11
        with self.assertRaises(Refused):summarize(encode(rows))

    def test_previous_v85_sample_remains_compatible(self):
        report=summarize(encode(sample()))
        self.assertEqual(report["class_totals"]["rectangle_sprite_primitive"]["handlers"],1)
        self.assertEqual(report["class_totals"]["gpu_state"]["handlers"],1)
        self.assertEqual(report["class_totals"]["gpu_state"]["native_store_attempts"],0)

    def test_public_report_does_not_include_opcode_words_or_private_data(self):
        report=json.dumps(summarize(encode(five_classes())),sort_keys=True)
        for unwanted in ("0x02000000","0x20000000","0xe1000020",
                         "private_path","source_address","vram_pixel",
                         "gp0_opcode","actual_cpu_cycles"):
            self.assertNotIn(unwanted,report)
        self.assertIn("native_callback_append_order_not_emulated_GPU_completion",report)

    def test_full_pinned_emulator_audits_class_totals_in_private(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v109_gp0_class_vblank_stores",workflow)
        self.assertIn("v109-gp0-class-summary.json",workflow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",workflow)
        self.assertIn("path: proof/public/",workflow)


if __name__=="__main__":
    unittest.main()
