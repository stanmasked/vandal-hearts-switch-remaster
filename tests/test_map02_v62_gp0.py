#!/usr/bin/env python3
"""v62 structural GP0 opcode framing, payload/terminator adversarial corpus."""
from __future__ import annotations
import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.decode_map02_v62_gp0 import parse_gp0_v62
from tools.make_map02_v62_gp0_fixtures import generate,scenarios,xy,uv
from tools.verify_map02_v60_ps1_dma import parse_gp0,decode,walk_dma,audit,DmaError

E6=0xe6000003

def ft4():
    return [0x2c808080,xy(10,10),uv(20,192),
            xy(20,10),uv(20,192,7),
            xy(10,20),uv(20,192),
            xy(20,20),uv(20,192)]

class V62GP0PacketTests(unittest.TestCase):
    def setUp(self):
        self.ram,self.manifest=generate()

    def test_fixture_has_four_valid_hardware_format_frames(self):
        r=audit(self.ram,self.manifest)
        self.assertEqual(r["status"],"raw_ps1_dma_structure_only")
        self.assertEqual(r["frames"],4)
        self.assertEqual(r["gp0_e6_words"],3)
        self.assertEqual(r["gp0_ft4_commands"],0)
        self.assertFalse(r["retail_gp0_provenance_verified"])

    def test_deceptive_e6_words_not_counted(self):
        self.assertGreater(self.ram.count(struct.pack("<I",0xe6000001)),2)
        self.assertEqual(decode(self.ram,self.manifest)["mask_commands"],3)

    def test_cross_dma_node_gouraud_quad(self):
        f=decode(self.ram,self.manifest)["frames"][0]
        self.assertEqual([e["type"] for e in f["events"]],
                         ["E1","POLYGON","POLYGON","E6"])
        self.assertEqual(f["nodes"][3]["words"],5)
        self.assertEqual(f["nodes"][4]["words"],7)
        self.assertEqual(f["events"][2]["opcode"],0x3c)
        self.assertEqual(f["events"][2]["vertices"],4)
        self.assertTrue(f["events"][2]["textured"])
        self.assertTrue(f["events"][2]["gouraud"])

    def test_gouraud_flat_triangle_exact_six(self):
        words=scenarios()[0][2]
        self.assertEqual(len(words),6)
        self.assertEqual(parse_gp0(words)[0]["opcode"],0x30)

    def test_four_line_families(self):
        q=decode(self.ram,self.manifest)["frames"][1]["events"]
        self.assertEqual([e["type"] for e in q],
                         ["LINE","LINE","POLYLINE","POLYLINE"])
        self.assertEqual([e["gouraud"] for e in q],[False,True,False,True])

    def test_polyline_alternate_termination(self):
        for terminator in (0x50005000,0x55555555,0x5fffffff):
            with self.subTest(terminator=terminator):
                r=parse_gp0([0x480000ff,xy(1,1),xy(2,2),xy(3,3),terminator,
                             0xe6000003])
                self.assertEqual([x["type"] for x in r],["POLYLINE","E6"])
                self.assertEqual(r[-1]["set"],1)
                self.assertEqual(r[-1]["check"],1)

    def test_polyline_fake_e6_vertex(self):
        x=parse_gp0([0x480000ff,xy(1,1),xy(2,2),0xe6000001,
                     0x55555555,0xe6000000])
        self.assertEqual([e["type"] for e in x],["POLYLINE","E6"])
        self.assertEqual(x[1]["word"],0xe6000000)

    def test_shaded_polyline_fake_e6_color(self):
        words=[0x580000ff,xy(1,1),0xe6000001,xy(2,2),
               0xe6000003,xy(3,3),0x50005000,0xe6000002]
        events=parse_gp0(words)
        self.assertEqual([e["type"] for e in events],["POLYLINE","E6"])
        self.assertEqual(events[1]["word"],0xe6000002)

    def test_rect_size_families(self):
        events=decode(self.ram,self.manifest)["frames"][2]["events"]
        rect=[e for e in events if e["type"]=="RECT"]
        self.assertEqual(len(rect),8)
        self.assertEqual([e["opcode"] for e in rect],
                         [0x60,0x64,0x68,0x6c,0x70,0x74,0x78,0x7c])
        self.assertEqual([e["size_code"] for e in rect],
                         [0,0,1,1,2,2,3,3])
        self.assertEqual([e["textured"] for e in rect],
                         [False,True,False,True,False,True,False,True])

    def test_rect_clut_looking_like_e6_is_payload(self):
        words=[0x64000000,xy(10,10),uv(2,4,0xe600),xy(8,8),0xe6000001]
        r=parse_gp0(words)
        self.assertEqual([e["type"] for e in r],["RECT","E6"])

    def test_transfer_payload_e6_is_not_command(self):
        r=decode(self.ram,self.manifest)["frames"][3]["events"]
        self.assertEqual([e["type"] for e in r],
                         ["FILL_VRAM","TRANSFER","TRANSFER","TRANSFER","E6"])
        self.assertEqual(r[2]["opcode"],0xa0)
        self.assertEqual(r[2]["payload_words"],3)
        self.assertEqual(r[-1]["word"],0xe6000000)

    def test_transfer_odd_halfword_padding(self):
        arr=[0xa0000000,xy(10,10),xy(3,1),0xe6000001,
             0xe6000003,0xe6000002]
        r=parse_gp0(arr)
        self.assertEqual([e["type"] for e in r],["TRANSFER","E6"])
        self.assertEqual(r[0]["payload_words"],2)

    def test_state_continues_across_frames(self):
        decoded=decode(self.ram,self.manifest)
        self.assertEqual([f["mask_state_at_end"] for f in decoded["frames"]],
                         [(1,0),(1,0),(0,1),(0,0)])
        self.assertTrue(all(e["mask_set"]==1 for e in decoded["frames"][1]["events"]))
        self.assertTrue(all(e["mask_check"]==1 for e in decoded["frames"][3]["events"][:-1]
                            if "mask_check" in e))

    def test_exact_gp0_polygon_counts(self):
        for opcode in range(0x20,0x40):
            n=4 if opcode&8 else 3
            length=1+n+n*bool(opcode&4)+(n-1)*bool(opcode&16)
            with self.subTest(opcode=opcode):
                words=[opcode<<24]+[0]*(length-1)+[0xe6000001]
                r=parse_gp0(words)
                self.assertEqual(r[-1]["type"],"E6")
                self.assertEqual(len(r),2)

    def test_exact_gp0_rectangle_counts(self):
        for opcode in range(0x60,0x80):
            count=2+bool(opcode&4)+((opcode&0x18)==0)
            with self.subTest(opcode=opcode):
                words=[opcode<<24]+[0]*(count-1)+[0xe6000001]
                r=parse_gp0(words)
                self.assertEqual([e["type"] for e in r],["RECT","E6"])

    def test_flat_and_gouraud_line_counts(self):
        for op,count in ((0x40,3),(0x42,3),(0x50,4),(0x52,4)):
            with self.subTest(op=op):
                r=parse_gp0([op<<24]+[0xe6000003]*(count-1)+[0xe6000000])
                self.assertEqual([e["type"] for e in r],["LINE","E6"])

    def test_unterminated_flat_polyline_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0x48000001,xy(1,1),xy(2,2),0xe6000003])

    def test_unterminated_gouraud_polyline_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0x58000001,xy(1,1),0x123456,xy(2,2),
                       0xe6000001,xy(3,3)])

    def test_dangling_gouraud_color_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0x58000001,xy(1,1),0x123456,xy(2,2),0xe6000001])

    def test_empty_polyline_before_terminator_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0x48000001,xy(1,1),xy(2,2)])

    def test_truncated_gouraud_quad_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0x3c808080]+[0]*10)

    def test_truncated_rectangle_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0x64000000,xy(1,1),uv(2,4)])

    def test_truncated_cpu_upload_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0xa0000000,xy(0,0),xy(2,4)]+[0xe6000003]*3)

    def test_implausibly_large_upload_refused(self):
        with self.assertRaises(DmaError):
            parse_gp0([0xa0000000,xy(0,0),0])

    def test_unknown_gp0_opcode_refused(self):
        for word in (0xe0000000,0xf0000000,0x03000000):
            with self.subTest(word=word),self.assertRaises(DmaError):
                parse_gp0([word,0xe6000001])

    def test_bad_gp0_initial_state_refused(self):
        for x in ((False,0),(0,2),[0,0],(0,),"unknown"):
            with self.subTest(x=x),self.assertRaises(DmaError):
                parse_gp0([0xe6000000],initial_mask=x)

    def test_legacy_ft4_and_old_event_name_preserved(self):
        self.assertEqual(parse_gp0([0x28000000]+[0]*4)[0]["type"],"DRAW_28")
        p=parse_gp0(ft4())[0]
        self.assertEqual(p["type"],"FT4")
        self.assertEqual((p["x0"],p["y0"],p["u0"],p["v0"]),
                         (10,10,20,192))

    def test_original_v60_manifest_stays_synthetic(self):
        from tools.make_map02_v60_synthetic_dma import generate as old
        data,manifest=old()
        result=audit(data,manifest)
        self.assertEqual(result["gp0_e6_words"],11)
        self.assertFalse(result["HD_replacement_approved"])
        self.assertFalse(result["retail_gp0_provenance_verified"])

if __name__=="__main__":
    unittest.main()
