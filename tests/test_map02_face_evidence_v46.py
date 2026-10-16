#!/usr/bin/env python3
"""Strict synthetic regression for local face/GFX/UV/OT/DDA provenance."""
import json
from pathlib import Path
import sys
import struct
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_map02_prs_v45 import synth_models
from tools.preflight_map02_prs_v45 import WIDTH,STRIDE,load_v24
from tools.verify_map02_face_evidence_v46 import compare,_draw_events,V46Invalid
HEADER=Path(__file__).resolve().parents[1]/"tests/fixtures/vh_map02_hd_lookup_v24.h"

def fixture():
    buf=bytearray(synth_models())
    a=(8*WIDTH+20)*STRIDE
    b=(11*WIDTH+11)*STRIDE
    buf[b:b+STRIDE]=buf[a:a+STRIDE]
    buf[a:a+STRIDE]=b"\x00"*STRIDE
    return bytes(buf)

def draw(f,z,x,gfx,slot,clut,v):
    return json.dumps({"z":z,"x":x,"face":0,"stage":"draw","gfx":gfx,
                       "frame":f,"u":240,"v":v,"clut":clut,
                       "tpage":5,"path":"normal"})+"\n"

def ot(f,t,gfx,clut):
    return f"[v39-terrain-ot] f={f} token={t} gfx={gfx} route=1 tpage=5 clut={clut}\n"

def pix(tag,f,t,gfx):
    extra=" scale=2" if tag=="v40-terrain-hires" else ""
    return (f"[{tag}] f={f} token={t} gfx={gfx} route=1 x=64 y=64 u=240 v=192 "
            f"raw=31 draw=1 semi=0 abr=0{extra}\n")

G1=draw(1,8,19,641,241,31978,192)
G2=draw(2,11,11,643,243,31850,208)
O1=ot(1,101,641,31978)
O2=ot(2,101,643,31850)
N1=pix("v39-terrain-dda",1,101,641)
H1=pix("v40-terrain-hires",1,101,641)
N2=pix("v39-terrain-dda",2,101,643)
H2=pix("v40-terrain-hires",2,101,643)

class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.slots=load_v24(HEADER)
    def check(self, graphics=None, gpu=None, model=None):
        a= [G1,G2] if graphics is None else graphics
        b= [O1,N1,H1,O2,N2,H2] if gpu is None else gpu
        return compare(fixture() if model is None else model,a,b,self.slots,
                       {"sha256_input":"test-synthetic","input_provenance":"caller_declared_synthetic"})
    def test_complete_two_faces_and_recycled_ot_token(self):
        d=self.check()
        self.assertEqual(d["status"],"synthetic_joint_evidence_only")
        self.assertEqual(d["joined_face_count"],2)
        self.assertEqual({(x["z"],x["x"],x["gfx"],x["local_slot"])
                          for x in d["joined_faces"]},
                         {(8,19,641,241),(11,11,643,243)})
        self.assertFalse(d["HD_replacement_approved"])
        self.assertFalse(d["retail_map_authenticity_proven"])
    def test_reverse_worker_line_order_accepted(self):
        self.assertEqual(self.check(gpu=[H2,N1,O2,H1,O1,N2])["joined_face_count"],2)
    def test_graphics_mismatch_at_same_coordinates_rejected(self):
        d=self.check(graphics=[G1,G2.replace('"gfx": 643','"gfx": 641')])
        self.assertEqual(d["status"],"refused")
        self.assertIn("PRS GFX",str(d["errors"]))
    def test_swapped_tile_without_mutating_gfx_rejected(self):
        d=self.check(graphics=[G1,G2.replace('"z": 11','"z": 8')])
        self.assertEqual(d["status"],"refused")
    def test_wrong_palette_rejected(self):
        d=self.check(graphics=[G1.replace('"clut": 31978','"clut": 31850'),G2])
        self.assertEqual(d["status"],"refused")
        self.assertIn("UV/tpage/CLUT",str(d["errors"]))
    def test_wrong_uv_rejected(self):
        d=self.check(graphics=[G1.replace('"u": 240','"u": 241'),G2])
        self.assertEqual(d["status"],"refused")
    def test_wrong_tpage_rejected(self):
        d=self.check(graphics=[G1.replace('"tpage": 5','"tpage": 6'),G2])
        self.assertEqual(d["status"],"refused")
    def test_wrong_ot_palette_rejected(self):
        d=self.check(gpu=[O1.replace("clut=31978","clut=31850"),N1,H1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
        self.assertIn("OT tpage/CLUT",str(d["errors"]))
    def test_wrong_frame_rejected(self):
        d=self.check(gpu=[ot(3,101,641,31978),N1,H1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
    def test_mismatched_ot_gfx_rejected(self):
        d=self.check(gpu=[ot(1,101,643,31978),N1,H1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
    def test_orphan_hires_sample_rejected(self):
        d=self.check(gpu=[O1,N1,H1,O2,N2,pix("v40-terrain-hires",3,101,643)])
        self.assertEqual(d["status"],"refused")
    def test_no_hires_sample_rejected(self):
        d=self.check(gpu=[O1,N1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
    def test_unclaimed_terrain_event_rejected(self):
        d=self.check(graphics=[G1],gpu=[O1,N1,H1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
        self.assertIn("unclaimed",str(d["errors"]))
    def test_duplicate_draw_in_frame_rejected(self):
        with self.assertRaisesRegex(V46Invalid,"repeated face"):
            self.check(graphics=[G1,G1,G2])
    def test_duplicate_ot_rejected(self):
        d=self.check(gpu=[O1,O1,N1,H1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
    def test_wrong_map_unobserved_is_not_false_evidence(self):
        d=self.check(graphics=[],gpu=[])
        self.assertEqual(d["status"],"insufficient_evidence")
        self.assertEqual(d["joined_face_count"],0)
    def test_unsupported_v24_local_slot_refused(self):
        b=bytearray(fixture())
        struct.pack_into("<h",b,(8*WIDTH+19)*STRIDE+176,642)
        d=self.check(model=bytes(b))
        self.assertEqual(d["status"],"refused")
    def test_malformed_draw_line_rejected(self):
        with self.assertRaisesRegex(V46Invalid,"unexpected"):
            self.check(graphics=[G1.replace('"face": 0, ','')])
    def test_wrong_draw_json_type_rejected(self):
        with self.assertRaises(V46Invalid):
            self.check(graphics=[G1.replace('"gfx": 641','"gfx": true')])
    def test_ambiguous_two_ot_same_frame_gfx_rejected(self):
        extra=ot(1,102,641,31978)
        d=self.check(gpu=[O1,N1,H1,extra,O2,N2,H2])
        self.assertEqual(d["status"],"refused")
    def test_legacy_unframed_ddas_rejected(self):
        d=self.check(gpu=[O1,N1.replace("f=1 ",""),H1,O2,N2,H2])
        self.assertEqual(d["status"],"refused")

if __name__=="__main__":unittest.main()
