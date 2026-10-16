#!/usr/bin/env python3
"""v50 independent oracle safety unit tests (no real-game files)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_gpu_modes_v50 import parse,reference,audit,V50Bad

NORMAL=("V50 name=indexed4_opaque depth=0 tpage=5 clut=31978 u=240 v=192 "
        "maskx=0 masky=0 offx=0 offy=0 tx=380 ty=192 "
        "word=4369 index=1 palx=673 paly=499 palette=31 "
        "raw=31 before=16912 after=31 semi=0 abr=0 dither=0 x=88 y=88")
def mutate(line,old,new):
    if old not in line:raise AssertionError("test anchor")
    return line.replace(old,new,1)

class NativeGpuOracleTests(unittest.TestCase):
    def test_valid_source_and_opaque_output(self):
        self.assertEqual(reference(parse(NORMAL)),("indexed4","opaque"))
    def test_missing_case_refused(self):
        self.assertEqual(audit([NORMAL])["status"],"refused")
    def test_wrong_post_pixel_refused(self):
        with self.assertRaisesRegex(V50Bad,"wrote"):
            reference(parse(mutate(NORMAL,"after=31","after=30")))
    def test_wrong_texword_refused(self):
        with self.assertRaisesRegex(V50Bad,"source"):
            reference(parse(mutate(NORMAL,"word=4369","word=0")))
    def test_wrong_clut_color_refused(self):
        with self.assertRaisesRegex(V50Bad,"source"):
            reference(parse(mutate(NORMAL,"palette=31","palette=0")))
    def test_wrong_texture_page_refused(self):
        with self.assertRaisesRegex(V50Bad,"source"):
            reference(parse(mutate(NORMAL,"tpage=5","tpage=4")))
    def test_wrong_window_offset_refused(self):
        with self.assertRaisesRegex(V50Bad,"source"):
            reference(parse(mutate(NORMAL,"offx=0","offx=1").replace("maskx=0","maskx=1")))
    def test_wrong_clut_address_refused(self):
        with self.assertRaisesRegex(V50Bad,"source"):
            reference(parse(mutate(NORMAL,"palx=673","palx=674")))
    def test_reject_duplicate_field(self):
        with self.assertRaisesRegex(V50Bad,"duplicate"):
            parse(NORMAL+" raw=31")
    def test_reject_missing_metadata(self):
        with self.assertRaisesRegex(V50Bad,"missing/extra"):
            parse(NORMAL.replace(" paly=499",""))
    def test_reject_bad_primitive_transparency_flag(self):
        with self.assertRaisesRegex(V50Bad,"invalid"):
            parse(mutate(NORMAL,"semi=0","semi=2"))
    def test_parser_does_not_accept_extra_native_case(self):
        with self.assertRaisesRegex(V50Bad,"unexpected"):
            parse(mutate(NORMAL,"name=indexed4_opaque","name=made_up"))
    def test_duplicate_cases_in_report_refused(self):
        r=audit([NORMAL,NORMAL])
        self.assertEqual(r["status"],"refused")
        self.assertIn("repeated",str(r["errors"]))
    def test_actual_green_8bit_halfword(self):
        line=(NORMAL.replace("name=indexed4_opaque","name=indexed8_lo")
               .replace("depth=0 tpage=5","depth=1 tpage=133")
               .replace("tx=380","tx=440")
               .replace("word=4369 index=1 palx=673","word=8481 index=33 palx=705")
               .replace("palette=31","palette=992").replace("raw=31","raw=992")
               .replace("after=31","after=992"))
        self.assertEqual(reference(parse(line)),("indexed8","opaque"))
    def test_transparent_skip_preserves_background(self):
        line=mutate(NORMAL,"name=indexed4_opaque","name=indexed4_zero")
        line=line.replace("palette=31","palette=0").replace("raw=31","raw=0").replace("after=31","after=16912")
        self.assertEqual(reference(parse(line)),("indexed4","transparent_skip"))

if __name__=="__main__":
    unittest.main()
