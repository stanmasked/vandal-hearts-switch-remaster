#!/usr/bin/env python3
"""v56 independent dense DDA seam and clipping BGR555 oracle tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_triangle_seams_v56 import (
    CASES,parse,check,audit,compare,hash_image,output_pixel,BadSeam,KEYS
)

def record(name,worker):
    spec=CASES[name]
    row={"name":name,"workers":worker}
    row.update(dict(zip(KEYS,spec)))
    if not spec[-1]:
        row["nativehash"]=hash_image(spec,1)
        row["hihash"]=hash_image(spec,2)
        row["directhash"]=row["hihash"]
        row["native_probe"]=output_pixel(spec,80,80,1)
        row["hires_probe"]=output_pixel(spec,161,161,2)
    else:
        row.update(nativehash="0123456789abcdef",hihash="abcdef0123456789",
                   directhash="abcdef0123456789",native_probe=0,hires_probe=0)
    row["outside_native"]=spec[1]
    row["outside_hires"]=spec[1]
    row["pixels"]=9216
    return "V56CASE "+" ".join(str(k)+"="+str(v) for k,v in row.items())

def fixture(worker):
    return [record(n,worker) for n in CASES]

def tamper(name,old,new):
    rows=fixture(2)
    i=next(i for i,s in enumerate(rows) if s.startswith("V56CASE name="+name+" "))
    assert old in rows[i],(old,rows[i])
    rows[i]=rows[i].replace(old,new,1)
    return rows

class OriginalFT4CoverageTests(unittest.TestCase):
    def test_eight_dense_rectangles_and_one_skew(self):
        d=audit(fixture(2),2)
        self.assertEqual(d["status"],"original_ft4_coverage_verified")
        self.assertEqual(d["independent_full_image_cases"],8)
        self.assertEqual(d["skew_reference_only_cases"],1)
        self.assertFalse(d["mask_destination_test_implemented_in_original_PC_port"])
        self.assertFalse(d["HD_replacement_approved"])
    def test_all_three_workers(self):
        r=compare({i:fixture(i) for i in (1,2,4)})
        self.assertEqual(r["status"],"verified")
        self.assertEqual(r["real_original_DDA_scenarios"],27)
        self.assertEqual(r["independent_hi_res_halfword_comparisons"],8*9216*3)
    def test_stp_0_1_2_3_blend_changes_full_images(self):
        hashes={hash_image(CASES["stp_abr"+str(i)],2) for i in range(4)}
        self.assertEqual(len(hashes),4)
    def test_zero_texel_does_not_paint(self):
        p=CASES["transparent_zero"]
        self.assertEqual(output_pixel(p,80,80,1),p[1])
        self.assertEqual(output_pixel(p,161,161,2),p[1])
    def test_opaque_no_stp_does_not_blend(self):
        a=CASES["nonstp_opaque"]
        self.assertEqual(output_pixel(a,80,80,1),31)
    def test_dest_mask_bit_is_not_hardware_mask_test(self):
        a=CASES["destination_bit15"]
        self.assertEqual(a[1]&0x8000,0x8000)
        self.assertEqual(output_pixel(a,80,80,1),0x03e0)
        self.assertNotEqual(output_pixel(a,80,80,1),a[1])
    def test_exact_clip_start_and_end(self):
        a=CASES["clipped_edges"]
        self.assertEqual(output_pixel(a,74,75,1),a[1])
        self.assertEqual(output_pixel(a,75,74,1),output_pixel(a,80,80,1))
        self.assertEqual(output_pixel(a,84,85,1),output_pixel(a,80,80,1))
        self.assertEqual(output_pixel(a,85,85,1),a[1])
        self.assertEqual(output_pixel(a,169,171,2),output_pixel(a,160,160,2))
        self.assertEqual(output_pixel(a,170,171,2),a[1])
    def test_shared_diagonal_expected_single_blend(self):
        a=CASES["stp_abr0"]
        self.assertEqual(output_pixel(a,80,80,1),output_pixel(a,79,80,1))
        self.assertEqual(output_pixel(a,160,160,2),output_pixel(a,161,160,2))
    def test_bad_source_texel_refused(self):
        self.assertEqual(audit(tamper("stp_abr0","texel=32799","texel=31"),2)["status"],"refused")
    def test_wrong_abr_refused(self):
        self.assertEqual(audit(tamper("stp_abr0","abr=0","abr=3"),2)["status"],"refused")
    def test_wrong_clipping_rect_refused(self):
        self.assertEqual(audit(tamper("clipped_edges","clipx=75","clipx=70"),2)["status"],"refused")
    def test_wrong_seam_pixel_refused(self):
        v=output_pixel(CASES["stp_abr0"],80,80,1)
        self.assertEqual(audit(tamper("stp_abr0","native_probe="+str(v),"native_probe="+str(v^1)),2)["status"],"refused")
    def test_wrong_real_native_full_image_hash_refused(self):
        v=hash_image(CASES["stp_abr1"],1)
        self.assertEqual(audit(tamper("stp_abr1","nativehash="+v,"nativehash=0000000000000001"),2)["status"],"refused")
    def test_wrong_HD_full_image_hash_refused(self):
        v=hash_image(CASES["stp_abr2"],2)
        self.assertEqual(audit(tamper("stp_abr2","hihash="+v,"hihash=0000000000000001"),2)["status"],"refused")
    def test_wrong_native_opaque_mask_behavior_refused(self):
        v=hash_image(CASES["destination_bit15"],1)
        self.assertEqual(audit(tamper("destination_bit15","nativehash="+v,"nativehash=0000000000000001"),2)["status"],"refused")
    def test_bad_transparency_skip_refused(self):
        v=hash_image(CASES["transparent_zero"],2)
        self.assertEqual(audit(tamper("transparent_zero","hihash="+v,"hihash=0000000000000001"),2)["status"],"refused")
    def test_unchanged_spare_pixel_is_required(self):
        spec=CASES["stp_abr0"]
        self.assertEqual(audit(tamper("stp_abr0","outside_hires="+str(spec[1]),"outside_hires=0"),2)["status"],"refused")
    def test_different_direct_H_DDA_refused(self):
        p=hash_image(CASES["stp_abr3"],2)
        self.assertEqual(audit(tamper("stp_abr3","directhash="+p,"directhash=0000000000000001"),2)["status"],"refused")
    def test_missing_skew_case_refused(self):
        self.assertEqual(audit(fixture(2)[:-1],2)["status"],"refused")
    def test_duplicate_case_refused(self):
        rows=fixture(2)
        self.assertEqual(audit(rows+[rows[0]],2)["status"],"refused")
    def test_worker_mismatch_refused(self):
        self.assertEqual(audit(fixture(2),4)["status"],"refused")
    def test_missing_worker_report_refused(self):
        self.assertEqual(compare({1:fixture(1),2:fixture(2)})["status"],"refused")
    def test_skew_cannot_be_mislabeled_as_full_independent_coverage(self):
        self.assertEqual(check(parse(record("skewed_quad",2))),
                         "original_native_skew_and_exact_direct_deferred_only")
    def test_parser_rejects_unknown_record(self):
        with self.assertRaises(BadSeam):
            parse("V56CASE name=unknown")
    def test_parser_rejects_duplicate_fields(self):
        with self.assertRaises(BadSeam):
            parse(record("stp_abr0",2)+" texel=32799")
    def test_parser_rejects_extra_fields(self):
        with self.assertRaises(BadSeam):
            parse(record("stp_abr0",2)+" magic=5")
if __name__=="__main__":unittest.main()
