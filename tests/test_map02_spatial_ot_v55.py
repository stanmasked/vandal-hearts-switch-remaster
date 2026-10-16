#!/usr/bin/env python3
"""v55 tests strict original DrawOTag regions, sprite vs terrain-like FT4, gaps."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_spatial_ot_v55 import (
    BadSpatial, GAPS, REGIONS, audit, audit_worker, category, coords,
    expected_color, parse
)
from tools.verify_map02_large_ot_v54 import ordered_expected, S_SEQ

TYPES={0:5,1:4,2:2,3:5,4:3,5:5,6:1,7:2}

def fixture(worker):
    lines=[]
    for scene in (0,1):
        for seq,(burst,slot,bucket,filler) in enumerate(ordered_expected(scene)):
            prim=4 if filler else TYPES[S_SEQ[scene][slot]]
            lines.append(f"V54WALK frame={scene} seq={seq} burst={burst} slot={slot} bucket={bucket} filler={filler} type={prim}")
        lines.append(f"V54TRACE frame={scene} count=256 registered=256")
        first_n=0;first_h=0
        for region in range(REGIONS):
            rx,ry=coords(region)
            x,y=rx+8,ry+12
            native=expected_color(scene,region,x,y)
            hd=expected_color(scene,region,x*2+1,y*2)
            if region==0:first_n,first_h=native,hd
            values=dict(scene=scene,workers=worker,region=region,firstburst=region*6,
                        x=x,y=y,hx=x*2+1,hy=y*2,native=native,hires=hd,direct=hd,
                        othash=f"0000000000000{region+1:03x}",
                        directhash=f"0000000000000{region+1:03x}")
            lines.append("V55REGION "+" ".join(f"{k}={v}" for k,v in values.items()))
        for slot,(x,y) in enumerate(GAPS):
            data=dict(scene=scene,workers=worker,slot=slot,
                      x=x,y=y,hx=x*2+1,hy=y*2,native=0,hires=0,direct=0)
            lines.append("V55GAP "+" ".join(f"{k}={v}" for k,v in data.items()))
        d=dict(scene=scene,workers=worker,bursts=24,buckets=4,packets=256,
               native=first_n,hires=first_h,direct=first_h,
               othash="0123456789abcdef",directhash="0123456789abcdef",
               pixels=57600,clut4=31978,clut8=31914,sprite_tpage=166,
               sprite_mask=1,sprite_offset=1,regions=4,width=80,height=180)
        lines.append("V55SUMMARY "+" ".join(f"{k}={v}" for k,v in d.items()))
    return lines

def changed(lines,prefix,old,new):
    data=list(lines)
    hits=[i for i,v in enumerate(data) if v.startswith(prefix)]
    assert len(hits)==1,(prefix,hits)
    row=data[hits[0]]
    assert old in row,(old,row)
    data[hits[0]]=row.replace(old,new,1)
    return data

class SpatialGPU(unittest.TestCase):
    def test_exact_real_OT_fixture(self):
        r=audit_worker(fixture(2),2)
        self.assertEqual(r["status"],"spatial_original_ot_verified")
        self.assertEqual(r["regions_per_scene"],4)
        self.assertEqual(r["sprites_per_scene"],24)
        self.assertEqual(r["textured_quads_per_scene"],48)
        self.assertEqual(r["full_hires_bounding_pixels_per_scene"],57600)
        self.assertFalse(r["HD_replacement_approved"])
    def test_full_cross_worker_parity(self):
        r=audit({w:fixture(w) for w in (1,2,4)})
        self.assertEqual(r["status"],"verified")
        self.assertEqual(r["complete_original_GPU_pixels_compared_per_compiler"],345600)
    def test_order_switch_is_observable_in_every_region(self):
        for reg in range(4):
            x,y=coords(reg)
            self.assertNotEqual(expected_color(0,reg,x+8,y+12),
                                expected_color(1,reg,x+8,y+12))
    def test_four_regions_span_three_worker_band_boundaries(self):
        self.assertEqual([coords(i)[1] for i in range(4)],[48,108,168,204])
    def test_real_sprite_is_distinct_primitive(self):
        self.assertEqual(category(0,4,0),"SPRT")
        self.assertEqual(category(0,2,0),"FT4")
    def test_modify_original_walk_bucket_rejected(self):
        d=changed(fixture(2),"V54WALK frame=0 seq=48 ","bucket=1","bucket=0")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_modify_original_walk_ft4_type_rejected(self):
        d=changed(fixture(2),"V54WALK frame=0 seq=2 ","type=2","type=3")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_sprite_classified_as_ft4_rejected(self):
        d=changed(fixture(2),"V54WALK frame=0 seq=4 ","type=3","type=2")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_wrong_region_coordinate_rejected(self):
        d=changed(fixture(2),"V55REGION scene=0 workers=2 region=2 ","x=88","x=89")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_wrong_region_bucket_source_rejected(self):
        d=changed(fixture(2),"V55REGION scene=0 workers=2 region=3 ","firstburst=18","firstburst=12")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_wrong_STP_layer_color_rejected(self):
        p="V55REGION scene=0 workers=2 region=1 "
        row=next(v for v in fixture(2) if v.startswith(p))
        import re
        n=int(re.search(r" native=(\d+)",row).group(1))
        self.assertEqual(audit_worker(changed(fixture(2),p,f"native={n}",f"native={n^1}"),2)["status"],"refused")
    def test_wrong_HD_pixel_rejected(self):
        p="V55REGION scene=1 workers=2 region=0 "
        import re
        row=next(v for v in fixture(2) if v.startswith(p))
        n=int(re.search(r" hires=(\d+)",row).group(1))
        self.assertEqual(audit_worker(changed(fixture(2),p,f"hires={n}",f"hires={n^1}"),2)["status"],"refused")
    def test_modified_region_hash_rejected(self):
        p="V55REGION scene=1 workers=2 region=3 "
        d=changed(fixture(2),p,"directhash=0000000000000004","directhash=0000000000000005")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_leaking_spatial_gap_rejected(self):
        p="V55GAP scene=1 workers=2 slot=2 "
        d=changed(fixture(2),p,"hires=0","hires=1")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_missing_gap_refused(self):
        d=[x for x in fixture(2) if not x.startswith("V55GAP scene=0 workers=2 slot=3 ")]
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_duplicate_gap_refused(self):
        d=fixture(2)
        d.append(next(x for x in d if x.startswith("V55GAP scene=0 workers=2 slot=3 ")))
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_missing_region_refused(self):
        d=[x for x in fixture(2) if not x.startswith("V55REGION scene=0 workers=2 region=1 ")]
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_duplicate_region_refused(self):
        d=fixture(2)
        d.append(next(x for x in d if x.startswith("V55REGION scene=0 workers=2 region=1 ")))
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_wrong_clut_refused(self):
        d=changed(fixture(2),"V55SUMMARY scene=0 ","clut8=31914","clut8=31978")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_corrupt_whole_surface_refused(self):
        d=changed(fixture(2),"V55SUMMARY scene=0 ","directhash=0123456789abcdef","directhash=0123456789abcdee")
        self.assertEqual(audit_worker(d,2)["status"],"refused")
    def test_mismatched_worker_report_refused(self):
        d=audit({1:fixture(1),2:fixture(2),4:fixture(1)})
        self.assertEqual(d["status"],"refused")
    def test_missing_worker_refused(self):
        self.assertEqual(audit({1:fixture(1),2:fixture(2)})["status"],"refused")
    def test_bad_trace_fields_refused(self):
        with self.assertRaises(BadSpatial):parse("V55REGION nonsense")
    def test_duplicate_trace_key_refused(self):
        row=next(x for x in fixture(2) if x.startswith("V55GAP"))
        with self.assertRaises(BadSpatial):parse(row+" slot=2")

if __name__=="__main__":unittest.main()
