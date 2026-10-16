#!/usr/bin/env python3
"""v53 fail-closed original ordering table / GPU state BGR555 oracle regressions."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_actual_ot_v53 import (composition,parse,audit_worker,
                                             compare_threads,BadOT)

def record(scene,workers):
    a={"scene":scene,"workers":workers,"primitive_count":72,
       "native":composition(scene,88,88),
       "hires":composition(scene,177,176),
       "direct":composition(scene,177,176),
       "othash":"1234567890abcdef","directhash":"1234567890abcdef",
       "pixels":10240,"clut4":31978,"clut8":31914,
       "sprite_tpage":166,"sprite_mask":1,"sprite_offset":1}
    return "V53 "+" ".join(f"{k}={v}" for k,v in a.items())
def logs(workers):return [record(0,workers),record(1,workers)]
def replace_one(lines,needle,new):
    lines=lines.copy()
    if needle not in lines[0]:raise AssertionError(needle)
    lines[0]=lines[0].replace(needle,new,1)
    return lines

class OTOracle(unittest.TestCase):
    def test_original_execution_manifest(self):
        self.assertEqual(audit_worker(logs(2),2)["status"],"mixed_real_ot_verified")
    def test_reverse_primitive_order_changes_color(self):
        self.assertNotEqual(composition(0,88,88),composition(1,88,88))
    def test_reference_hires_at_different_resolution(self):
        self.assertEqual(audit_worker(logs(4),4)["status"],"mixed_real_ot_verified")
    def test_complete_worker_matrix(self):
        self.assertEqual(compare_threads({n:logs(n) for n in (1,2,4)})["status"],"verified")
    def test_mismatched_native_pixel(self):
        x=composition(0,88,88)
        self.assertEqual(audit_worker(replace_one(logs(1),"native="+str(x),"native="+str(x^1)),1)["status"],"refused")
    def test_mismatched_hires_pixel(self):
        x=composition(0,177,176)
        self.assertEqual(audit_worker(replace_one(logs(1),"hires="+str(x),"hires="+str(x^1)),1)["status"],"refused")
    def test_different_manual_HD_pixel(self):
        x=composition(0,177,176)
        self.assertEqual(audit_worker(replace_one(logs(1),"direct="+str(x),"direct="+str(x^1)),1)["status"],"refused")
    def test_clut_8bit_mismatch(self):
        self.assertEqual(audit_worker(replace_one(logs(1),"clut8=31914","clut8=31978"),1)["status"],"refused")
    def test_wrong_GP0_window(self):
        self.assertEqual(audit_worker(replace_one(logs(1),"sprite_mask=1","sprite_mask=0"),1)["status"],"refused")
    def test_wrong_GP0_page(self):
        self.assertEqual(audit_worker(replace_one(logs(1),"sprite_tpage=166","sprite_tpage=165"),1)["status"],"refused")
    def test_corrupt_region_hash(self):
        self.assertEqual(audit_worker(replace_one(logs(1),"othash=1234567890abcdef","othash=1234567890abcdee"),1)["status"],"refused")
    def test_missing_second_scene(self):
        self.assertEqual(audit_worker(logs(1)[:1],1)["status"],"refused")
    def test_duplicate_synthetic_scene(self):
        self.assertEqual(audit_worker(logs(1)+[logs(1)[0]],1)["status"],"refused")
    def test_worker_count_spoof(self):
        self.assertEqual(audit_worker(logs(2),1)["status"],"refused")
    def test_actual_worker_hash_divergence(self):
        d={n:logs(n) for n in (1,2,4)}
        d[4]=replace_one(d[4],"othash=1234567890abcdef","othash=1234567890abcdee")
        self.assertEqual(compare_threads(d)["status"],"refused")
    def test_missing_worker_setting(self):
        self.assertEqual(compare_threads({1:logs(1),2:logs(2)})["status"],"refused")
    def test_malformed_log_record(self):
        with self.assertRaises(BadOT):parse("V53 nope")
    def test_invalid_primitive_count(self):
        with self.assertRaises(BadOT):parse(replace_one(logs(2),"primitive_count=72","primitive_count=71")[0])
    def test_extra_field(self):
        with self.assertRaises(BadOT):parse(logs(2)[0]+" junk=1")

if __name__=="__main__":
    unittest.main()
