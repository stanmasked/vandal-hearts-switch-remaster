#!/usr/bin/env python3
"""Independent PS1 GPU pixel/ABR/STP validation; all fixtures synthetic."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.preflight_map02_prs_v45 import WIDTH, HEIGHT, STRIDE, load_v24
from tools.verify_map02_pixels_v48 import (
    parse, verify_pixel, modulate, pack, blend, audit, BadPixelTrace
)
from tools.instrument_map02_v48 import patch_raster

LOOKUP=Path(__file__).resolve().parent/"fixtures/vh_map02_hd_lookup_v24.h"
FIELDS={
 "f":1,"token":101,"gfx":641,"route":1,"target":0,"x":96,"y":96,
 "u":240,"v":192,"raw":31,"draw":1,"front":31,"before":0,
 "after":31,"semi":0,"abr":0,"dither":0,
 "mr":128,"mg":128,"mb":128,"scale":1,
}

def emitted(changes=None):
    d=dict(FIELDS)
    d.update(changes or {})
    return "[v48-terrain-pixel] "+" ".join(f"{k}={v}" for k,v in d.items())+"\n"

def model():
    out=bytearray(WIDTH*HEIGHT*STRIDE)
    for z,x,gfx in ((8,19,641),(8,20,641)):
        off=(z*WIDTH+x)*STRIDE
        struct.pack_into("<h",out,off+176,gfx)
        out[off+302]=1
        out[off+212:off+216]=bytes((0,1,2,3))
    return bytes(out)

def event(f,t,z,x):
    return [
        f"[v47-terrain-face-ot] f={f} token={t} z={z} x={x} face=0 gfx=641 route=1 tpage=5 clut=31978 u=240 v=192\n",
        f"[v39-terrain-ot] f={f} token={t} gfx=641 route=1 tpage=5 clut=31978\n",
        f"[v39-terrain-dda] f={f} token={t} gfx=641 route=1 x=96 y=96 u=240 v=192 raw=31 draw=1 semi=0 abr=0\n",
        f"[v40-terrain-hires] f={f} token={t} gfx=641 route=1 x=192 y=192 u=240 v=192 raw=31 draw=1 semi=0 abr=0 scale=2\n"
    ]

class PixelMath(unittest.TestCase):
    def test_opaque_15_bit_red(self):
        self.assertEqual(verify_pixel(dict(FIELDS)),"opaque")
    def test_transparent_texel_keeps_background(self):
        p=dict(FIELDS,raw=0,draw=0,front=0,before=0x57a3,after=0x57a3)
        self.assertEqual(verify_pixel(p),"transparent_skip")
    def test_transparent_skip_rejects_changed_after(self):
        with self.assertRaisesRegex(BadPixelTrace,"transparent"):
            verify_pixel(dict(FIELDS,raw=0,draw=0,front=0,after=1))
    def test_solid_nonstp_does_not_blend_even_with_abe(self):
        p=dict(FIELDS,semi=1,raw=31,before=0x7fff,after=31)
        self.assertEqual(verify_pixel(p),"opaque")
    def test_stp_blends_all_four_modes(self):
        for mode in range(4):
            with self.subTest(abr=mode):
                p=dict(FIELDS,raw=0x801f,semi=1,abr=mode,before=0x052a,
                       after=blend(31,0x052a,mode))
                self.assertEqual(verify_pixel(p),"stp_blend_"+str(mode))
    def test_stp_opaque_when_abe_is_off(self):
        self.assertEqual(verify_pixel(dict(FIELDS,raw=0x801f,semi=0)),"opaque")
    def test_reject_mismatched_blend_color(self):
        p=dict(FIELDS,raw=0x801f,semi=1,before=0x052a,after=999)
        with self.assertRaisesRegex(BadPixelTrace,"PS1 STP/ABR"):
            verify_pixel(p)
    def test_dither_matrix_all_16_locations(self):
        for y in range(4):
            for x in range(4):
                with self.subTest(x=x,y=y):
                    col=modulate(0x4210,128,128,128,x,y,1)
                    p=dict(FIELDS,x=x,y=y,raw=0x4210,dither=1,front=col,after=col)
                    self.assertEqual(verify_pixel(p),"opaque")
    def test_dither_changes_front_on_boundary(self):
        a=modulate(0x4210,128,128,128,0,0,1)
        b=modulate(0x4210,128,128,128,3,0,1)
        self.assertNotEqual(a,b)
    def test_refuse_bad_dithered_front(self):
        with self.assertRaisesRegex(BadPixelTrace,"dither"):
            verify_pixel(dict(FIELDS,raw=0x4210,dither=1,front=0,after=0))
    def test_modulation_scaling(self):
        p=dict(FIELDS,mr=64,front=15,after=15)
        self.assertEqual(verify_pixel(p),"opaque")
    def test_abrs_not_all_same(self):
        v={blend(0x7fff,0x03e0,x) for x in range(4)}
        self.assertEqual(len(v),4)
    def test_pack_clamps_24bit(self):
        self.assertEqual(pack(999,-1,0),31)
        self.assertEqual(pack(255,255,255),0x7fff)
    def test_source_transparency_disagreement(self):
        with self.assertRaisesRegex(BadPixelTrace,"draw decision"):
            verify_pixel(dict(FIELDS,raw=0,draw=1))
    def test_parser_has_only_whitelisted_fields(self):
        self.assertEqual(parse(emitted())["gfx"],641)
        with self.assertRaisesRegex(BadPixelTrace,"bad pixel fields"):
            parse(emitted().replace(" scale=1",""))
    def test_parser_rejects_duplicate_field(self):
        with self.assertRaisesRegex(BadPixelTrace,"duplicate"):
            parse(emitted().rstrip()+" raw=1")
    def test_parser_rejects_pixel_outside_vram(self):
        with self.assertRaisesRegex(BadPixelTrace,"out-of-range"):
            parse(emitted({"x":1024}))
    def test_parser_rejects_native_scale2(self):
        with self.assertRaisesRegex(BadPixelTrace,"out-of-range"):
            parse(emitted({"scale":2}))

class DecisionAuditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots=load_v24(LOOKUP)
        cls.decoded=model()
    def base(self):
        data=event(1,101,8,19)+event(1,102,8,20)
        for tok in (101,102):
            data.append(emitted({"token":tok}))
            data.append(emitted({"token":tok,"target":1,"scale":2,
                                 "x":192,"y":192}))
        return data
    def audit(self, lines):
        return audit(lines,self.decoded,self.slots,source_sha="SYNTHETIC")
    def test_both_passes_for_identical_gfx_different_ot_tokens(self):
        result=self.audit(self.base())
        self.assertEqual(result["status"],"pixel_decisions_correlated")
        self.assertEqual(result["per_token_pixel_observed_count"],2)
        self.assertEqual(result["native_pixel_observations"],2)
        self.assertEqual(result["hires_pixel_observations"],2)
        self.assertFalse(result["HD_replacement_approved"])
    def test_wrong_after_refused(self):
        v=self.base()
        v[-1]=v[-1].replace("after=31","after=29")
        d=self.audit(v)
        self.assertEqual(d["status"],"refused")
        self.assertIn("pixel output",str(d["errors"]))
    def test_wrong_token_refused(self):
        v=self.base()
        v[-1]=v[-1].replace("token=102","token=104")
        self.assertEqual(self.audit(v)["status"],"refused")
    def test_missing_hires_not_falsely_proven(self):
        v=[line for line in self.base() if "[v48-terrain-pixel]" not in line or "target=0" in line]
        self.assertEqual(self.audit(v)["status"],"insufficient_sparse_evidence")
    def test_malformed_legacy_record_fails(self):
        with self.assertRaisesRegex(BadPixelTrace,"bad pixel fields"):
            parse(emitted().replace(" before=0",""))
    def test_source_patch_rejects_wrong_anchor(self):
        with self.assertRaises(ValueError):
            patch_raster("static void dda_span() {}")
    def test_untagged_sprite_pixel_record_fails(self):
        v=self.base()
        v.append(emitted({"token":555}))
        self.assertEqual(self.audit(v)["status"],"refused")

if __name__=="__main__": unittest.main()
