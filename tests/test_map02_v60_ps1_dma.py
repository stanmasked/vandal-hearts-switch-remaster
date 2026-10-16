#!/usr/bin/env python3
"""v60: 26 fail-closed PS1 DMA/GP0 decoder and VHT1 separation tests."""
from __future__ import annotations
import copy
import hashlib
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v60_synthetic_dma import generate,BASE
from tools.verify_map02_v59_trace import FRAMES
from tools.verify_map02_v60_ps1_dma import (
    audit, decode, walk_dma, parse_gp0, compare_formats,
    FORMAT, DmaError,
)

def refreshed(raw,metadata):
    v=dict(metadata)
    v["sha256"]=hashlib.sha256(raw).hexdigest()
    return v

def replace_word(raw,word,replacement,occurrence=0):
    before=struct.pack("<I",word)
    hit=0
    for i in range(0,len(raw),4):
        if raw[i:i+4]==before:
            if hit==occurrence:
                blob=bytearray(raw)
                struct.pack_into("<I",blob,i,replacement)
                return bytes(blob)
            hit+=1
    raise AssertionError(f"word not found: {word:08x} occurrence={occurrence}")

def make_vht_semantics():
    def entry(op,a=b"",b=b""):
        return op+struct.pack("<I",len(a))+a+struct.pack("<I",len(b))+b
    data=bytearray(b"VHT1")
    for name,bg,clip,abr,steps in FRAMES:
        for i,(command,texel,semi) in enumerate(steps):
            dr=bytearray(12)
            dr[7]=6
            struct.pack_into("<I",dr,8,command)
            data+=entry(b"P",struct.pack("<I",6),dr)
            ft4=bytearray(40)
            ft4[7]=2+(0x80 if semi else 0)
            struct.pack_into("<hh",ft4,8,70,70)
            ft4[12]=20+i
            ft4[13]=192
            struct.pack_into("<H",ft4,22,7|(abr<<5)|(2<<7))
            data+=entry(b"P",struct.pack("<I",2),ft4)
        data+=entry(b"Z")
    return bytes(data)

class HardwareDmaTests(unittest.TestCase):
    def setUp(self):
        self.ram,self.meta=generate()
    def assertReject(self,blob,metadata=None,vht=None):
        with self.assertRaises((DmaError,ValueError)):
            audit(blob,self.meta if metadata is None else metadata,vht)
    def test_synthetic_four_frame_real_hardware_format(self):
        result=audit(self.ram,self.meta)
        self.assertEqual(result["status"],"raw_ps1_dma_structure_only")
        self.assertEqual(result["frames"],4)
        self.assertEqual(result["gp0_e6_words"],11)
        self.assertEqual(result["gp0_ft4_commands"],11)
        self.assertEqual(result["dma_nodes"],4+4+11)
        self.assertFalse(result["retail_gp0_provenance_verified"])
    def test_semantic_crosswalk_to_custom_vht1(self):
        r=audit(self.ram,self.meta,make_vht_semantics())
        self.assertEqual(r["status"],"synthetic_cross_format_semantic_order_verified")
        self.assertFalse(r["HD_replacement_approved"])
    def test_ft4_payload_contains_e6_not_a_command(self):
        d=decode(self.ram,self.meta)
        events=[e for f in d["frames"] for e in f["events"]]
        self.assertEqual(sum(x["type"]=="E6" for x in events),11)
        self.assertEqual(self.ram.count(struct.pack("<I",0xe6000003)),12)
    def test_ft4_semantics_and_mask_state(self):
        d=decode(self.ram,self.meta)
        q=[x for x in d["frames"][0]["events"] if x["type"]=="FT4"]
        self.assertEqual(len(q),2)
        self.assertEqual([x["mask_set"] for x in q],[1,0])
        self.assertEqual([x["mask_check"] for x in q],[0,1])
        self.assertEqual([x["u0"] for x in q],[20,21])
    def test_reject_vht1_as_hardware_blob(self):
        blob=b"VHT1"+self.ram[4:]
        self.assertReject(blob,refreshed(blob,self.meta))
    def test_invalid_sha256(self):
        self.assertReject(self.ram[:-4]+b"ABCD")
    def test_no_manifest_format_claims_vht1(self):
        m=dict(self.meta,format="VHT1")
        self.assertReject(self.ram,m)
    def test_no_self_attested_retail(self):
        m=dict(self.meta,source_class="hardware-captured-verified")
        self.assertReject(self.ram,m)
    def test_unverified_source_still_no_retail_gate(self):
        m=dict(self.meta,source_class="user-supplied-unverified")
        r=audit(self.ram,m)
        self.assertFalse(r["retail_gp0_provenance_verified"])
    def test_no_extra_manifest_keys(self):
        self.assertReject(self.ram,dict(self.meta,retail_proven=True))
    def test_invalid_base(self):
        self.assertReject(self.ram,dict(self.meta,base_address=BASE+1))
    def test_pointer_outside_image(self):
        b=bytearray(self.ram)
        struct.pack_into("<I",b,0,0x0100ff00)
        data=bytes(b)
        self.assertReject(data,refreshed(data,self.meta))
    def test_head_in_middle_of_word(self):
        m=dict(self.meta,entry_points=[BASE+2])
        self.assertReject(self.ram,m)
    def test_cycle_detection(self):
        b=bytearray(self.ram)
        struct.pack_into("<I",b,0,BASE+4) # head links to node1
        # node1 links back to head, count unchanged
        node1off=4
        (header,)=struct.unpack_from("<I",b,node1off)
        struct.pack_into("<I",b,node1off,(header&0xff000000)|BASE)
        data=bytes(b)
        self.assertReject(data,refreshed(data,self.meta))
    def test_truncated_dma_node_payload(self):
        b=bytearray(self.ram)
        struct.pack_into("<I",b,0,0xff000004)
        data=bytes(b)
        self.assertReject(data,refreshed(data,self.meta))
    def test_invalid_reserved_e6_bits(self):
        b=replace_word(self.ram,0xe6000001,0xe6000005)
        self.assertReject(b,refreshed(b,self.meta))
    def test_modified_real_e6_order(self):
        b=replace_word(self.ram,0xe6000001,0xe6000000)
        with self.assertRaises(DmaError):
            compare_formats(decode(b,refreshed(b,self.meta)),make_vht_semantics())
    def test_modified_real_ft4_uv(self):
        b=replace_word(self.ram,0x0000c014,0x0000c013)
        self.assertReject(b,refreshed(b,self.meta),make_vht_semantics())
    def test_modified_ft4_semi(self):
        b=replace_word(self.ram,0x2e808080,0x2c808080)
        self.assertReject(b,refreshed(b,self.meta),make_vht_semantics())
    def test_gp0_unknown_opcode_refused(self):
        with self.assertRaises(DmaError):parse_gp0([0xa0000000,0xe6000001])
    def test_gp0_f4_primitive_length(self):
        self.assertEqual(parse_gp0([0x28001020,1,2,3,4])[0]["type"],"DRAW_28")
    def test_gp0_short_ft4_refused(self):
        with self.assertRaises(DmaError):parse_gp0([0x2c808080]+[0]*7)
    def test_gp0_command_can_cross_dma_node(self):
        # Concatenated payload is parsed after linked-list walking.
        raw=self.ram
        self.assertTrue(any(n["words"]==10 for n in decode(raw,self.meta)["frames"][0]["nodes"]))
        cmd=[0xe6000001,0x2c808080]+[0]*8
        events=parse_gp0(cmd)
        self.assertEqual([e["type"] for e in events],["E6","FT4"])
    def test_missing_frame_in_vht(self):
        with self.assertRaises((DmaError,ValueError)):
            compare_formats(decode(self.ram,self.meta),make_vht_semantics()[:-9])
    def test_bad_vht_semantics(self):
        blob=make_vht_semantics()
        data=blob.replace(struct.pack("<I",0xe6000001),
                          struct.pack("<I",0xe6000002),1)
        self.assertReject(self.ram,self.meta,data)
    def test_only_end_marker_ffffff(self):
        b=bytearray(self.ram)
        # Most significant address bit is NOT accepted as a portable end marker.
        struct.pack_into("<I",b,0,0x01800000)
        raw=bytes(b)
        self.assertReject(raw,refreshed(raw,self.meta))

if __name__=="__main__": unittest.main()
