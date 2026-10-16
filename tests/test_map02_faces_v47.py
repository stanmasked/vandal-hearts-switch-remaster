#!/usr/bin/env python3
"""V47 per-token face identity regression; all payloads are SYNTHETIC."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.preflight_map02_prs_v45 import WIDTH,HEIGHT,STRIDE,load_v24
from tools.verify_map02_faces_v47 import verify,parse_face_log,InvalidEvidence
from tools.instrument_map02_v47 import patch_graphics,patch_gpu

LOOKUP=Path(__file__).resolve().parent/"fixtures/vh_map02_hd_lookup_v24.h"

def model():
    buf=bytearray(WIDTH*HEIGHT*STRIDE)
    for z,x,gfx in ((8,19,641),(8,20,641),(11,11,643)):
        o=(z*WIDTH+x)*STRIDE
        struct.pack_into("<h",buf,o+176,gfx)
        buf[o+212:o+216]=bytes((0,1,2,3))
        buf[o+302]=1
    return bytes(buf)

def render(f,token,z,x,gfx,clut,v):
    lines=[
        f"[v47-terrain-face-ot] f={f} token={token} z={z} x={x} face=0 gfx={gfx} route=1 tpage=5 clut={clut} u=240 v={v}\n",
        f"[v39-terrain-ot] f={f} token={token} gfx={gfx} route=1 tpage=5 clut={clut}\n",
        f"[v39-terrain-dda] f={f} token={token} gfx={gfx} route=1 x=64 y=64 u=240 v={v} raw=31 draw=1 semi=0 abr=0\n",
        f"[v40-terrain-hires] f={f} token={token} gfx={gfx} route=1 x=64 y=64 u=240 v={v} raw=31 draw=1 semi=0 abr=0 scale=2\n",
    ]
    return lines

def log():
    return render(1,101,8,19,641,31978,192) + render(1,102,8,20,641,31978,192) + render(2,101,11,11,643,31850,208)

class V47EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=model()
        cls.slots=load_v24(LOOKUP)
    def probe(self,lines=None,data=None):
        return verify(self.data if data is None else data,self.slots,log() if lines is None else lines,
                      synthetic=True,source_sha="TEST_ONLY_SYNTHETIC")
    def test_identical_gfx_same_frame_different_tiles_accepted(self):
        r=self.probe()
        self.assertEqual(r["status"],"matched_sampled_faces")
        self.assertEqual(r["matched_face_count"],3)
        self.assertEqual(r["duplicate_gfx_face_pairs"],1)
        self.assertEqual(r["distinct_face_coordinates_count"],3)
        self.assertFalse(r["HD_replacement_approved"])
        self.assertFalse(r["retail_map_authenticity_proven"])
    def test_logs_can_be_out_of_order_for_threads(self):
        s=log()
        self.assertEqual(self.probe([s[7],s[3],s[11]] + s[:3] + s[4:7] + s[8:11])["status"],
                         "matched_sampled_faces")
    def test_recycled_token_new_frame(self):
        r=self.probe()
        self.assertEqual({(x["frame"],x["token"],x["gfx"]) for x in r["rows"]},
                         {(1,101,641),(1,102,641),(2,101,643)})
    def test_swapped_coordinates_between_identical_gfx_are_detected_if_wrong_prs(self):
        s=log()
        changed=s[4].replace("x=20","x=21")
        r=self.probe(s[:4]+[changed]+s[5:])
        self.assertEqual(r["status"],"refused")
        self.assertIn("nonexistent PRS face",str(r["errors"]))
    def test_marker_missing_rejected(self):
        s=log()
        with self.assertRaisesRegex(InvalidEvidence,"missing or extra"):
            self.probe([line for i,line in enumerate(s) if i!=4])
    def test_wrong_v24_clut_refused(self):
        s=log()
        s[0]=s[0].replace("clut=31978","clut=31850")
        self.assertEqual(self.probe(s)["status"],"refused")
    def test_wrong_tpage_refused(self):
        s=log()
        s[0]=s[0].replace("tpage=5","tpage=6")
        self.assertEqual(self.probe(s)["status"],"refused")
    def test_wrong_texture_uv_refused(self):
        s=log()
        s[0]=s[0].replace("u=240","u=239")
        self.assertEqual(self.probe(s)["status"],"refused")
    def test_wrong_prs_gfx_refused(self):
        b=bytearray(self.data)
        struct.pack_into("<h",b,(8*WIDTH+20)*STRIDE+176,643)
        self.assertEqual(self.probe(data=b)["status"],"refused")
    def test_missing_hi_res_is_insufficient(self):
        s=log()
        s.pop(3)
        r=self.probe(s)
        self.assertEqual(r["status"],"insufficient_sparse_evidence")
        self.assertEqual(r["sparsely_unobserved_count"],1)
    def test_wrong_gpu_ot_gfx_fails_v41_preflight(self):
        s=log()
        s[1]=s[1].replace("gfx=641","gfx=643")
        with self.assertRaisesRegex(InvalidEvidence,"original v41"):
            self.probe(s)
    def test_untagged_sprite_does_not_add_a_face(self):
        s=log()+["unrelated GPU sprite with tpage=5 clut=31978 UV=240\n"]
        self.assertEqual(self.probe(s)["matched_face_count"],3)
    def test_wrong_frame_face_ot_marker_rejected(self):
        s=log()
        s[0]=s[0].replace("f=1","f=3")
        with self.assertRaisesRegex(InvalidEvidence,"missing or extra"):
            self.probe(s)
    def test_duplicate_face_marker_rejected(self):
        with self.assertRaisesRegex(InvalidEvidence,"duplicate face marker"):
            self.probe(log()+[log()[0]])
    def test_out_of_range_rejected(self):
        with self.assertRaisesRegex(InvalidEvidence,"out-of-range"):
            parse_face_log(log()[0].replace("face=0","face=18"))
    def test_malformed_marker_rejected(self):
        with self.assertRaisesRegex(InvalidEvidence,"fields differ"):
            parse_face_log(log()[0].replace(" token=101",""))
    def test_unknown_extra_marker_rejected(self):
        with self.assertRaisesRegex(InvalidEvidence,"missing or extra"):
            self.probe(log()+[render(4,102,8,19,641,31978,192)[0]])
    def test_unexpected_face_duplicate_same_frame_allowed_if_separate_token(self):
        s=log()+render(1,103,8,19,641,31978,192)
        r=self.probe(s)
        self.assertEqual(r["matched_face_count"],4)
    def test_missing_producer_v39_tag_fails(self):
        s=log()
        s.pop(1)
        with self.assertRaises(InvalidEvidence):
            self.probe(s)

    def test_second_face_within_one_tile_has_separate_identity(self):
        # One real model can contain multiple source faces with identical GFX.
        b=bytearray(self.data)
        off=(8*WIDTH+20)*STRIDE
        b[off+302]=2
        struct.pack_into("<h",b,off+178,641)
        b[off+216:off+220]=bytes((0,1,2,3))
        extra=render(1,103,8,20,641,31978,192)
        extra[0]=extra[0].replace("face=0","face=1")
        r=self.probe(log()+extra,data=bytes(b))
        self.assertEqual(r["status"],"matched_sampled_faces")
        self.assertEqual(r["matched_face_count"],4)
        self.assertIn((8,20,1),{(x["z"],x["x"],x["face"]) for x in r["rows"]})

class Anchors(unittest.TestCase):
    def test_refuse_uninstrumented_source(self):
        with self.assertRaises(ValueError):
            patch_gpu("void DrawOTag() {}")
        with self.assertRaises(ValueError):
            patch_graphics("void RenderMapTile() {}")

if __name__=="__main__":
    unittest.main()
