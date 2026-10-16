#!/usr/bin/env python3
"""v54 source-only exact 256 token walk, bucket, STP and GPU trace tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_large_ot_v54 import (
    BURSTS,COUNT,TOTAL,ordered_expected,color,parse,audit_worker,
    cross_worker,BadLargeOT
)
from tools.verify_map02_actual_ot_v53 import S_SEQ

TYPES={0:5,1:4,2:2,3:5,4:3,5:5,6:1,7:2}

def render_log(threads):
    data=[]
    for scene in (0,1):
        for seq,(burst,slot,bucket,filler) in enumerate(ordered_expected(scene)):
            typ=4 if filler else TYPES[S_SEQ[scene][slot]]
            row=dict(frame=scene,seq=seq,burst=burst,slot=slot,bucket=bucket,
                     filler=filler,type=typ)
            data.append("V54WALK "+" ".join(f"{k}={v}" for k,v in row.items()))
        data.append(f"V54TRACE frame={scene} count={TOTAL} registered={TOTAL}")
        row=dict(scene=scene,workers=threads,bursts=BURSTS,buckets=4,
                 packets=TOTAL,native=color(scene,88,88),hires=color(scene,177,176),
                 direct=color(scene,177,176),
                 othash="1234567890abcdef",directhash="1234567890abcdef",
                 pixels=10240,clut4=31978,clut8=31914,
                 sprite_tpage=166,sprite_mask=1,sprite_offset=1)
        data.append("V54SUMMARY "+" ".join(f"{k}={v}" for k,v in row.items()))
    return data

def edit_first(lines,prefix,old,new):
    lines=list(lines)
    for i,line in enumerate(lines):
        if line.startswith(prefix) and old in line:
            lines[i]=line.replace(old,new,1)
            return lines
    raise AssertionError((prefix,old))

class LargeOT(unittest.TestCase):
    def probe(self,lines=None):
        return audit_worker(render_log(2) if lines is None else lines,2)
    def test_entire_exact_256_packet_token_walk(self):
        r=self.probe()
        self.assertEqual(r["status"],"original_256_ot_verified")
        self.assertEqual(r["packet_count_per_frame"],256)
        self.assertEqual(r["overlapping_semantic_packets_per_frame"],192)
        self.assertEqual(r["scenes"]["0"]["depth_bucket_counts"],
                         {"0":48,"1":48,"2":48,"3":48,"7":64})
    def test_original_two_layer_sequences_are_measurably_different(self):
        self.assertNotEqual(color(0,88,88),color(1,88,88))
    def test_expected_each_bucket_has_six_bursts(self):
        expected=ordered_expected(0)
        self.assertEqual(len(expected),256)
        self.assertEqual(expected[0],(0,0,0,0))
        self.assertEqual(expected[47],(5,7,0,0))
        self.assertEqual(expected[48],(6,0,1,0))
        self.assertEqual(expected[-1],(-1,63,7,1))
    def test_all_three_render_threads_match(self):
        self.assertEqual(cross_worker({n:render_log(n) for n in (1,2,4)})["status"],"verified")
    def test_swapped_OT_slot_refused(self):
        data=edit_first(render_log(2),"V54WALK frame=0 seq=1 ","slot=1","slot=2")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_depth_bucket_refused(self):
        data=edit_first(render_log(2),"V54WALK frame=0 seq=48 ","bucket=1","bucket=2")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_burst_refused(self):
        data=edit_first(render_log(2),"V54WALK frame=0 seq=56 ","burst=7","burst=6")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_OT_token_walk_order_refused(self):
        data=edit_first(render_log(2),"V54WALK frame=0 seq=5 ","seq=5","seq=2")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_primitive_type_refused(self):
        data=edit_first(render_log(2),"V54WALK frame=0 seq=2 ","type=2","type=4")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_missing_draw_call_refused(self):
        data=[x for x in render_log(2) if not x.startswith("V54WALK frame=1 seq=192 ")]
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_extra_sprite_refused(self):
        data=render_log(2)
        data.append(data[0])
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_missing_frame_delimiter_refused(self):
        data=[x for x in render_log(2) if not x.startswith("V54TRACE frame=0 ")]
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_registration_count_refused(self):
        data=edit_first(render_log(2),"V54TRACE frame=0 ","registered=256","registered=255")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_native_pixel_refused(self):
        v=color(0,88,88)
        data=edit_first(render_log(2),"V54SUMMARY scene=0 ","native="+str(v),"native="+str(v^1))
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_HD_pixel_refused(self):
        v=color(0,177,176)
        data=edit_first(render_log(2),"V54SUMMARY scene=0 ","hires="+str(v),"hires="+str(v^1))
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_4bpp_palette_refused(self):
        data=edit_first(render_log(2),"V54SUMMARY scene=0 ","clut4=31978","clut4=31914")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_window_setting_refused(self):
        data=edit_first(render_log(2),"V54SUMMARY scene=0 ","sprite_offset=1","sprite_offset=0")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_corrupted_whole_HD_surface_hash_refused(self):
        data=edit_first(render_log(2),"V54SUMMARY scene=0 ","othash=1234567890abcdef","othash=1234567890abcdee")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_wrong_worker_metadata_refused(self):
        data=edit_first(render_log(2),"V54SUMMARY scene=1 ","workers=2","workers=4")
        self.assertEqual(self.probe(data)["status"],"refused")
    def test_cross_worker_full_region_mismatch_refused(self):
        input={n:render_log(n) for n in (1,2,4)}
        input[4]=edit_first(input[4],"V54SUMMARY scene=1 ","othash=1234567890abcdef","othash=1234567890abcdee")
        self.assertEqual(cross_worker(input)["status"],"refused")
    def test_missing_workers_refused(self):
        self.assertEqual(cross_worker({1:render_log(1),2:render_log(2)})["status"],"refused")
    def test_trace_parser_refuses_bad_fields(self):
        with self.assertRaises(BadLargeOT):parse("V54WALK junk")
    def test_trace_parser_refuses_duplicate_fields(self):
        with self.assertRaises(BadLargeOT):parse(render_log(1)[0]+" seq=0")
    def test_trace_parser_refuses_unknown_fields(self):
        with self.assertRaises(BadLargeOT):parse(render_log(1)[0]+" unknown=1")

if __name__=="__main__":unittest.main()
