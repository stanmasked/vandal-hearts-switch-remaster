#!/usr/bin/env python3
"""v51 synthetic-only cross-pass checks. Real C execution is a separate CI gate."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.verify_map02_hires_modes_v51 import audit,split_cases,BadHiresProof
from tools.verify_map02_gpu_modes_v50 import EXPECTED


def rows():
    cases={}
    for name in EXPECTED:
        base={"name":name,"depth":0,"tpage":5,"clut":31978,
              "u":240,"v":192,"maskx":0,"masky":0,"offx":0,"offy":0,
              "tx":380,"ty":192,"word":4369,"index":1,"palx":673,"paly":499,
              "palette":31,"raw":31,"before":16912,"after":31,
              "semi":0,"abr":0,"dither":0,"x":88,"y":88}
        cases[name]=base
    out={"native":deepcopy(cases),"hires":deepcopy(cases),
         "threaded":deepcopy(cases)}
    for p in ("hires","threaded"):
        for item in out[p].values():
            item["x"]=177
            item["y"]=176
    out["native"]["indexed4_dither"]["after"]=30
    return out, {k:{"status":"original_dda_modes_verified"} for k in out}


class CrossPassTests(unittest.TestCase):
    def check(self,records):
        hashes=[f"V51HASH name={name} direct=0123456789abcdef threaded=0123456789abcdef" for name in EXPECTED]
        with patch("tools.verify_map02_hires_modes_v51.split_cases",return_value=records):
            return audit(hashes)
    def test_18_distinct_native_hires_worker_cases(self):
        r=self.check(rows())
        self.assertEqual(r["status"],"original_hires_modes_verified")
        self.assertEqual(r["actual_modes_per_pass"],18)
        self.assertEqual(r["total_original_GPU_mode_executions"],54)
        self.assertEqual(r["direct_hires_vs_deferred_equal_count"],18)
        self.assertFalse(r["HD_replacement_approved"])
    def test_direct_worker_pixel_mismatch_is_rejected(self):
        r=rows()
        r[0]["threaded"]["direct15_stp"]["after"] ^= 1
        self.assertEqual(self.check(r)["status"],"refused")
    def test_wrong_hires_coordinates_rejected(self):
        r=rows()
        r[0]["hires"]["indexed8_hi"]["x"] = 176
        self.assertEqual(self.check(r)["status"],"refused")
    def test_wrong_worker_coordinates_rejected(self):
        r=rows()
        r[0]["threaded"]["indexed8_lo"]["y"] = 177
        self.assertEqual(self.check(r)["status"],"refused")
    def test_wrong_clut_on_hires_rejected(self):
        r=rows()
        r[0]["hires"]["indexed4_opaque"]["clut"] ^= 1
        self.assertEqual(self.check(r)["status"],"refused")
    def test_wrong_input_STP_rejected(self):
        r=rows()
        r[0]["threaded"]["indexed4_abr2"]["raw"] = 0
        self.assertEqual(self.check(r)["status"],"refused")
    def test_wrong_texture_window_rejected(self):
        r=rows()
        r[0]["hires"]["window_mask_xy"]["maskx"] = 1
        self.assertEqual(self.check(r)["status"],"refused")
    def test_same_native_and_hires_dither_is_not_accepted(self):
        r=rows()
        r[0]["hires"]["indexed4_dither"]["after"] = 30
        r[0]["threaded"]["indexed4_dither"]["after"] = 30
        self.assertEqual(self.check(r)["status"],"refused")
    def test_full_hires_region_tampering_rejected(self):
        from tools.verify_map02_hires_modes_v51 import full_region_hashes
        hashes=[f"V51HASH name={name} direct=0123456789abcdef threaded=0123456789abcdef" for name in EXPECTED]
        hashes[0]=hashes[0].replace("threaded=0123456789abcdef","threaded=0123456789abcdee")
        with patch("tools.verify_map02_hires_modes_v51.split_cases",return_value=rows()):
            self.assertEqual(audit(hashes)["status"],"refused")
    def test_missing_region_hash_refused(self):
        from tools.verify_map02_hires_modes_v51 import full_region_hashes
        with self.assertRaises(BadHiresProof):
            full_region_hashes([])
    def test_missing_captured_native_set_fails_closed(self):
        with self.assertRaises(BadHiresProof):
            split_cases([])
    def test_malformed_gpu_mode_line_fails_closed(self):
        with self.assertRaises(BadHiresProof):
            split_cases(["V51HD corrupt"])
    def test_parser_cannot_accept_duplicate_c_mode(self):
        with self.assertRaises(BadHiresProof):
            split_cases(["V50 name=indexed4_opaque\n"]*18)


if __name__=="__main__":
    unittest.main()
