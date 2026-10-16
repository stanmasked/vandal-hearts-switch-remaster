#!/usr/bin/env python3
"""v58 adversarial independent mask command ordering and pixel tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_gp0_ot_v58 import CASES, hash_image, output_pixel, audit,compare

def fixture(workers):
    rows=[]
    for name,spec in CASES.items():
        bg,cx,cy,cw,ch,abr,steps=spec
        for i,(cmd,texel,semi) in enumerate(steps):
            rows.append(f"V58OT name={name} index={2*i} type=mask command={cmd}")
            rows.append(f"V58OT name={name} index={2*i+1} type=quad uv={20+i} semi={semi} abr={abr}")
        row={
            "name":name,"workers":workers,"n":len(steps),"background":bg,
            "clipx":cx,"clipy":cy,"clipw":cw,"cliph":ch,"abr":abr,
            "nativehash":hash_image(spec,1),"hihash":hash_image(spec,2),
            "directhash":hash_image(spec,2),"native_probe":output_pixel(spec,80,80,1),
            "hires_probe":output_pixel(spec,161,161,2),
            "outside_native":bg,"outside_hires":bg,"pixels":9216,
        }
        rows.append("V58CASE "+" ".join(f"{k}={v}" for k,v in row.items()))
    return rows

def change(name,field,value,kind="V58CASE"):
    rows=fixture(2)
    matches=[i for i,s in enumerate(rows) if s.startswith(kind+" name="+name+" ")]
    assert matches,(name,kind)
    i=matches[0]
    old=next(segment for segment in rows[i].split() if segment.startswith(field+"="))
    rows[i]=rows[i].replace(old,f"{field}={value}",1)
    return rows

class MaskOtOrderingTests(unittest.TestCase):
    def test_independent_full_image_9_scenes(self):
        r=audit(fixture(2),2)
        self.assertEqual(r["status"],"ordered_gp0_e6_gpu_verified",r["errors"])
        self.assertEqual(r["real_ordered_ot_scenes"],9)
        self.assertFalse(r["retail_gp0_dma_packet_decoding_proven"])
        self.assertFalse(r["HD_replacement_approved"])
    def test_real_worker_configs_and_counts(self):
        r=compare({w:fixture(w) for w in (1,2,4)})
        self.assertEqual(r["status"],"verified",r["errors"])
        self.assertEqual(r["real_executed_gpu_scenarios"],27)
        self.assertEqual(r["independent_hd_halfwords"],9*9216*3)
    def test_masked_destination_is_preserved(self):
        self.assertEqual(output_pixel(CASES["mark_skip"],80,80,1),0x801f)
    def test_unmasking_allows_new_draw(self):
        self.assertEqual(output_pixel(CASES["reopen"],80,80,1),0x03e0)
    def test_zero_texel_does_not_set_bit15(self):
        self.assertEqual(output_pixel(CASES["zero_texel"],80,80,1),0x03e0)
    def test_invalid_e6_preserves_last_state(self):
        self.assertEqual(output_pixel(CASES["invalid_reserved"],80,80,1),0x83e0)
    def test_abr_variants_distinct(self):
        self.assertEqual(len({hash_image(CASES["abr"+str(n)],1) for n in range(4)}),4)
    def test_half_open_clip(self):
        s=CASES["clip_mask"]
        self.assertEqual(output_pixel(s,74,75,1),0x0010)
        self.assertEqual(output_pixel(s,75,74,1),0x801f)
        self.assertEqual(output_pixel(s,84,85,1),0x801f)
        self.assertEqual(output_pixel(s,85,85,1),0x0010)
    def test_bad_ot_mask_command(self):
        self.assertEqual(audit(change("mark_skip","command",3875536896, "V58OT"),2)["status"],"refused")
    def test_wrong_quad_uv(self):
        self.assertEqual(audit(change("reopen","uv",99,"V58OT"),2)["status"],"refused")
    def test_wrong_quad_stp(self):
        self.assertEqual(audit(change("abr1","semi",0,"V58OT"),2)["status"],"refused")
    def test_missing_ot_primitive(self):
        lines=fixture(2)
        lines.remove(next(l for l in lines if l.startswith("V58OT name=clip_mask index=1")))
        self.assertEqual(audit(lines,2)["status"],"refused")
    def test_swapped_mask_and_quad(self):
        rows=fixture(2)
        i=next(i for i,v in enumerate(rows) if v.startswith("V58OT name=mark_skip "))
        rows[i],rows[i+1]=rows[i+1],rows[i]
        self.assertEqual(audit(rows,2)["status"],"refused")
    def test_wrong_native_probe(self):
        self.assertEqual(audit(change("mark_skip","native_probe",0),2)["status"],"refused")
    def test_wrong_hd_hash(self):
        self.assertEqual(audit(change("abr3","hihash","0000000000000000"),2)["status"],"refused")
    def test_wrong_direct_hash(self):
        self.assertEqual(audit(change("abr2","directhash","ffffffffffffffff"),2)["status"],"refused")
    def test_wrong_clip(self):
        self.assertEqual(audit(change("clip_mask","clipx",70),2)["status"],"refused")
    def test_bad_workers(self):
        self.assertEqual(audit(change("abr0","workers",4),2)["status"],"refused")
    def test_cross_worker_corruption(self):
        cases={w:fixture(w) for w in (1,2,4)}
        cases[4]=[x.replace("nativehash=","nativehash=1") if x.startswith("V58CASE name=reopen") else x for x in cases[4]]
        self.assertEqual(compare(cases)["status"],"refused")
    def test_duplicate_missing_case(self):
        rows=fixture(2)
        self.assertEqual(audit(rows+[rows[0]],2)["status"],"refused")
        self.assertEqual(audit(rows[:-1],2)["status"],"refused")
if __name__=="__main__":
    unittest.main()
