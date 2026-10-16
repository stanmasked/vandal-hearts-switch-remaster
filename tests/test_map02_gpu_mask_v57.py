#!/usr/bin/env python3
"""v57 independent GP0(E6) mask test oracle and adversarial log mutations."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_gpu_mask_v57 import (
    CASES,SPEC_KEYS,hash_image,output_pixel,audit,compare
)

def record(name,worker):
    spec=CASES[name]
    row={"name":name,"workers":worker}
    row.update(dict(zip(SPEC_KEYS,spec)))
    row.update(
        nativehash=hash_image(spec,1),
        hihash=hash_image(spec,2),
        directhash=hash_image(spec,2),
        native_probe=output_pixel(spec,80,80,1),
        hires_probe=output_pixel(spec,161,161,2),
        outside_native=spec[1],
        outside_hires=spec[1],
        pixels=9216,
    )
    return "V57CASE "+" ".join(f"{k}={v}" for k,v in row.items())

def fixture(worker):
    return [record(name,worker) for name in CASES]

def corrupted(name,field,new):
    rows=fixture(2)
    index=next(i for i,r in enumerate(rows) if r.startswith(f"V57CASE name={name} "))
    parts=rows[index].split()
    old=next(x for x in parts if x.startswith(field+"="))
    rows[index]=rows[index].replace(old,f"{field}={new}",1)
    return rows

class MaskOracleTests(unittest.TestCase):
    def test_all_15_full_frame_cases(self):
        rep=audit(fixture(2),2)
        self.assertEqual(rep["status"],"original_gp0_e6_mask_verified",rep["errors"])
        self.assertEqual(rep["real_original_gpu_cases"],15)
        self.assertFalse(rep["GP0_E6_retail_command_integration_proven"])
        self.assertFalse(rep["HD_replacement_approved"])
    def test_three_workers(self):
        out=compare({w:fixture(w) for w in (1,2,4)})
        self.assertEqual(out["status"],"verified",out["errors"])
        self.assertEqual(out["real_original_gpu_scenarios"],45)
        self.assertEqual(out["independent_hd_halfword_comparisons"],15*9216*3)
    def test_destination_bit15_protected(self):
        spec=CASES["masked_preserved"]
        for scale in (1,2):
            self.assertEqual(output_pixel(spec,80*scale,80*scale,scale),0x8010)
    def test_unmasked_overwrite(self):
        self.assertEqual(output_pixel(CASES["default_overwrite"],80,80,1),0x03e0)
        self.assertEqual(output_pixel(CASES["unmasked_allowed"],80,80,1),0x03e0)
    def test_force_bit15(self):
        self.assertEqual(output_pixel(CASES["force_opaque"],80,80,1),0x83e0)
        self.assertEqual(output_pixel(CASES["force_and_check"],160,160,2),0x83e0)
    def test_skip_takes_precedence_over_force(self):
        self.assertEqual(output_pixel(CASES["masked_force_skip"],80,80,1),0x8010)
    def test_transparent_texel_never_writes_mask(self):
        self.assertEqual(output_pixel(CASES["zero_texel_force"],80,80,1),0x0010)
    def test_masked_stp_skips_before_abr(self):
        self.assertEqual(output_pixel(CASES["masked_stp_skip"],80,80,1),0x9210)
    def test_abr_modes_have_distinct_hashes(self):
        self.assertEqual(len({hash_image(CASES["stp_abr"+str(i)],2)
                              for i in range(4)}),4)
    def test_source_stp_clear_stays_opaque(self):
        self.assertEqual(output_pixel(CASES["nonstp_opaque"],80,80,1),0x801f)
    def test_two_drawotag_mask_state_transition(self):
        self.assertEqual(output_pixel(CASES["mask_transition"],80,80,1),0x801f)
    def test_clip_edges_are_half_open(self):
        p=CASES["mask_clip"]
        self.assertEqual(output_pixel(p,74,75,1),p[1])
        self.assertEqual(output_pixel(p,75,74,1),output_pixel(p,80,80,1))
        self.assertEqual(output_pixel(p,85,85,1),p[1])
        self.assertEqual(output_pixel(p,170,171,2),p[1])
    def test_mutated_mask_check_rejected(self):
        self.assertEqual(audit(corrupted("masked_preserved","maskcheck",0),2)["status"],"refused")
    def test_mutated_force_flag_rejected(self):
        self.assertEqual(audit(corrupted("force_opaque","maskset",0),2)["status"],"refused")
    def test_mutated_abr_rejected(self):
        self.assertEqual(audit(corrupted("stp_abr2","abr",1),2)["status"],"refused")
    def test_mutated_texture_rejected(self):
        self.assertEqual(audit(corrupted("stp_abr0","texel",31),2)["status"],"refused")
    def test_mutated_expected_mask_color_rejected(self):
        self.assertEqual(audit(corrupted("force_opaque","native_probe",992),2)["status"],"refused")
    def test_mutated_full_native_hash_rejected(self):
        self.assertEqual(audit(corrupted("mask_transition","nativehash","0000000000000000"),2)["status"],"refused")
    def test_mutated_full_hd_hash_rejected(self):
        self.assertEqual(audit(corrupted("mask_clip","hihash","0000000000000000"),2)["status"],"refused")
    def test_mutated_direct_hash_rejected(self):
        self.assertEqual(audit(corrupted("stp_abr3","directhash","ffffffffffffffff"),2)["status"],"refused")
    def test_mutated_clip_rejected(self):
        self.assertEqual(audit(corrupted("mask_clip","clipx",70),2)["status"],"refused")
    def test_mutated_worker_count_rejected(self):
        self.assertEqual(audit(corrupted("stp_abr1","workers",9),2)["status"],"refused")
    def test_duplicate_and_missing_case_rejected(self):
        self.assertEqual(audit(fixture(2)+fixture(2)[:1],2)["status"],"refused")
        self.assertEqual(audit(fixture(2)[:-1],2)["status"],"refused")
    def test_cross_worker_mutation_rejected(self):
        logs={w:fixture(w) for w in (1,2,4)}
        logs[4]=corrupted("masked_preserved","hires_probe",7)
        self.assertEqual(compare(logs)["status"],"refused")
    def test_bad_field_refused(self):
        row=fixture(2)
        row[0]+=" unknown=1"
        self.assertEqual(audit(row,2)["status"],"refused")

if __name__=="__main__":
    unittest.main()
