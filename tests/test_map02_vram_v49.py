#!/usr/bin/env python3
"""Fail-closed v49 VRAM source provenance on synthetic packed texture words."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tools.preflight_map02_prs_v45 import load_v24
from tools.verify_map02_vram_v49 import (
    parse,independent_sample,audit,BadSource
)
from tools.instrument_map02_v49 import patch
from test_map02_pixels_v48 import event,emitted,model

HDR=Path(__file__).parent/"fixtures/vh_map02_hd_lookup_v24.h"
DEFAULT=dict(f=1,token=101,gfx=641,route=1,target=0,x=96,y=96,
             u=240,v=192,tpage=5,clut=31978,
             maskx=0,masky=0,offx=0,offy=0,
             tx=380,ty=192,palx=673,paly=499,
             word=0x1111,index=1,palette=31,raw=31)

def rec(d=None):
    p=dict(DEFAULT)
    p.update(d or {})
    return "[v49-terrain-vram] "+" ".join(k+"="+str(v) for k,v in p.items())+"\n"

class TextureSourceMath(unittest.TestCase):
    def test_4bpp_first_nibble_clut(self):
        self.assertEqual(independent_sample(DEFAULT),"indexed4")
    def test_4bpp_second_nibble(self):
        p=dict(DEFAULT,u=241,word=0x1234,index=3,palx=675,palette=0x801f,raw=0x801f)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_4bpp_fourth_nibble(self):
        p=dict(DEFAULT,u=243,word=0x1234,index=1)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_8bpp_byte_selection(self):
        p=dict(DEFAULT,tpage=133,u=241,tx=440,word=0x2713,index=0x27,
               palx=711,palette=0x8001,raw=0x8001)
        self.assertEqual(independent_sample(p),"indexed8")
    def test_8bpp_low_byte(self):
        p=dict(DEFAULT,tpage=133,u=240,tx=440,word=0x2713,index=0x13,
               palx=691,palette=7,raw=7)
        self.assertEqual(independent_sample(p),"indexed8")
    def test_direct_15bpp(self):
        p=dict(DEFAULT,tpage=261,tx=560,index=-1,palx=-1,paly=-1,
               palette=0,word=0x801f,raw=0x801f)
        self.assertEqual(independent_sample(p),"direct15")
    def test_window_mask_x_removes_bit(self):
        p=dict(DEFAULT,u=248,maskx=1,offx=0,tx=380)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_window_offset_x_sets_bit(self):
        p=dict(DEFAULT,u=240,maskx=1,offx=1,tx=382)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_window_mask_y(self):
        p=dict(DEFAULT,v=200,masky=1,offy=0,ty=192)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_window_y_offset(self):
        p=dict(DEFAULT,v=192,masky=1,offy=1,ty=200)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_reject_wrong_texword_address(self):
        with self.assertRaisesRegex(BadSource,"word VRAM address"):
            independent_sample(dict(DEFAULT,tx=381))
    def test_reject_bad_palette_address(self):
        with self.assertRaisesRegex(BadSource,"CLUT pixel"):
            independent_sample(dict(DEFAULT,palx=674))
    def test_reject_modified_texel_index(self):
        with self.assertRaisesRegex(BadSource,"index"):
            independent_sample(dict(DEFAULT,index=2))
    def test_reject_modified_raw_texel(self):
        with self.assertRaisesRegex(BadSource,"raw texel"):
            independent_sample(dict(DEFAULT,raw=0x8001))
    def test_raw_stp_halfword_preserved(self):
        p=dict(DEFAULT,palette=0x801f,raw=0x801f)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_zero_palette_raw_transparent(self):
        p=dict(DEFAULT,palette=0,raw=0)
        self.assertEqual(independent_sample(p),"indexed4")
    def test_reject_direct_palette_manipulation(self):
        p=dict(DEFAULT,tpage=261,tx=560,index=-1,palx=-1,paly=-1,
               palette=1,word=31,raw=31)
        with self.assertRaisesRegex(BadSource,"must not look up"):
            independent_sample(p)
    def test_reject_out_of_bounds_clut_address(self):
        p=dict(DEFAULT,tpage=133,u=240,tx=440,clut=63,word=0xff00,
               index=0,palx=1008,paly=0,palette=31)
        # index0 is valid, another index=255 would read outside VRAM.
        self.assertEqual(independent_sample(p),"indexed8")
        p.update(word=0x00ff,index=255,palx=1263)
        with self.assertRaisesRegex(BadSource,"CLUT address out of bounds"):
            independent_sample(p)
    def test_parser_reject_missing_metadata(self):
        with self.assertRaisesRegex(BadSource,"field set"):
            parse(rec().replace(" maskx=0",""))
    def test_parser_reject_duplicate_metadata(self):
        with self.assertRaisesRegex(BadSource,"duplicate"):
            parse(rec().rstrip()+" raw=2")
    def test_parser_reject_out_of_bounds_source(self):
        with self.assertRaisesRegex(BadSource,"out-of-bounds"):
            parse(rec({"tx":1024}))
    def test_pinned_original_gpu_patch_fail_closed(self):
        with self.assertRaises(ValueError):
            patch("static void dda_span() {}")

class EndToEndSyntheticTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots=load_v24(HDR)
        cls.decoded=model()
    def trace(self):
        logs=event(1,101,8,19)+event(1,102,8,20)
        for token in (101,102):
            for target,x,y,scale in ((0,96,96,1),(1,192,192,2)):
                logs.append(emitted({"token":token,"target":target,"x":x,"y":y,
                                     "scale":scale}))
                logs.append(rec({"token":token,"target":target,"x":x,"y":y}))
        return logs
    def probe(self,logs=None):
        return audit(self.trace() if logs is None else logs,self.decoded,
                     self.slots,source_sha="SYNTHETIC")
    def test_same_gfx_two_token_two_pass_source(self):
        r=self.probe()
        self.assertEqual(r["status"],"vram_clut_source_correlated")
        self.assertEqual(r["source_type_counts"],{"indexed4":4})
        self.assertEqual(r["native_source_samples"],2)
        self.assertEqual(r["hires_source_samples"],2)
        self.assertFalse(r["HD_replacement_approved"])
    def test_modified_sampled_raw_rejected(self):
        lines=self.trace()
        for i,line in enumerate(lines):
            if "[v49-terrain-vram]" in line:
                lines[i]=line.replace(" raw=31"," raw=7")
                break
        self.assertEqual(self.probe(lines)["status"],"refused")
    def test_modified_packed_word_rejected(self):
        lines=self.trace()
        for i,line in enumerate(lines):
            if "[v49-terrain-vram]" in line:
                lines[i]=line.replace("word=4369","word=0")
                break
        self.assertEqual(self.probe(lines)["status"],"refused")
    def test_modified_clut_address_rejected(self):
        lines=self.trace()
        for i,line in enumerate(lines):
            if "[v49-terrain-vram]" in line:
                lines[i]=line.replace("palx=673","palx=674")
                break
        self.assertEqual(self.probe(lines)["status"],"refused")
    def test_missing_source_rejected(self):
        lines=[x for x in self.trace() if not ("[v49-terrain-vram]" in x and "token=102 " in x)]
        with self.assertRaisesRegex(BadSource,"missing or extra"):
            self.probe(lines)
    def test_wrong_ot_token_rejected(self):
        lines=self.trace()
        for i,line in enumerate(lines):
            if "[v49-terrain-vram]" in line:
                lines[i]=line.replace("token=101","token=555")
                break
        with self.assertRaisesRegex(BadSource,"missing or extra"):
            self.probe(lines)

if __name__=="__main__":unittest.main()
