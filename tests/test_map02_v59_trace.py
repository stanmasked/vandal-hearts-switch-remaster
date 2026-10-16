#!/usr/bin/env python3
"""v59 synthetic trace binary validator and replay-hash negative mutations."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_v59_trace import FRAMES,parse_vht,audit_trace,verify,BadTrace

def record(op,a=b"",b=b""):
    return op+struct.pack("<I",len(a))+a+struct.pack("<I",len(b))+b

def packet(type_,blob):
    return record(b"P",struct.pack("<I",type_),blob)

def synthetic():
    out=bytearray(b"VHT1")
    for _,bg,clip,abr,steps in FRAMES:
        out+=record(b"L",struct.pack("<hhhh",64,64,48,48),
                    struct.pack("<H",bg)*(48*48))
        out+=record(b"L",struct.pack("<hhhh",468,192,4,1),
                    struct.pack("<4H",*([s[1] for s in steps]+[0]*(4-len(steps)))))
        env=bytearray(96)
        struct.pack_into("<hhhh",env,0,*clip)
        out+=record(b"E",b"",env)
        mode=bytearray(12)
        mode[7]=5
        out+=packet(5,mode)
        for i,(cmd,tex,semi) in enumerate(steps):
            m=bytearray(12)
            m[7]=6
            struct.pack_into("<I",m,8,cmd)
            out+=packet(6,m)
            q=bytearray(40)
            q[7]=2 | (0x80 if semi else 0)
            struct.pack_into("<hh",q,8,70,70)
            q[12]=20+i
            q[13]=192
            struct.pack_into("<H",q,22,7 | (abr<<5) | (2<<7))
            out+=packet(2,q)
        filler=bytearray(16)
        filler[7]=4
        for i in range(64):out+=packet(4,filler)
        out+=record(b"Z")
    return bytes(out)

def record_log(phase):
    return "\n".join(f"V59FRAME phase={phase} frame={i} nativehash={i+1:016x} hihash={i+11:016x}"
                     for i in range(4))+"\n"

def replay_log():
    return record_log("replay")+"REPLAY frames=4 combined=0000000000001234\n"

class TraceRoundTripTests(unittest.TestCase):
    def test_four_ordered_vht1_frames(self):
        result=audit_trace(synthetic())
        self.assertEqual(result["status"],"synthetic_vht1_ot_verified")
        self.assertEqual(result["frames"],4)
        self.assertEqual(result["gpu_mask_packets"],11)
        self.assertFalse(result["HD_replacement_approved"])
    def test_independent_native_hd_hash_compare(self):
        report=verify(synthetic(),record_log("record"),
                      {1:replay_log(),2:replay_log(),4:replay_log()})
        self.assertEqual(report["status"],"original_vht1_e6_roundtrip_verified")
        self.assertEqual(report["independent_full_frame_hd_hash_equalities"],12)
        self.assertFalse(report["genuine_retail_gpu_packets_proven"])
    def test_bad_magic(self):
        with self.assertRaises(BadTrace):audit_trace(b"NOPE"+synthetic()[4:])
    def test_truncated_header(self):
        with self.assertRaises(BadTrace):audit_trace(synthetic()+b"P\x04")
    def test_truncated_payload(self):
        with self.assertRaises(BadTrace):audit_trace(synthetic()[:-1])
    def test_extra_trace_tail(self):
        with self.assertRaises(BadTrace):audit_trace(synthetic()+record(b"Z"))
    def test_incorrect_mask_command(self):
        payload=synthetic().replace(struct.pack("<I",0xe6000001),
                                    struct.pack("<I",0xe6000000),1)
        with self.assertRaises(BadTrace):audit_trace(payload)
    def test_incorrect_source_word(self):
        orig=synthetic()
        tex=struct.pack("<4H",0x001f,0x03e0,0,0)
        self.assertIn(tex,orig)
        with self.assertRaises(BadTrace):
            audit_trace(orig.replace(tex,struct.pack("<4H",0x001e,0x03e0,0,0),1))
    def test_modified_clip(self):
        s=synthetic()
        seq=struct.pack("<hhhh",75,74,10,12)
        self.assertIn(seq,s)
        with self.assertRaises(BadTrace):
            audit_trace(s.replace(seq,struct.pack("<hhhh",70,74,10,12),1))
    def test_wrong_record_native_hash(self):
        log=record_log("record").replace("nativehash=0000000000000001",
                                         "nativehash=0000000000000000",1)
        with self.assertRaises(BadTrace):
            verify(synthetic(),log,{1:replay_log(),2:replay_log(),4:replay_log()})
    def test_wrong_replay_hd_hash(self):
        logs={w:replay_log() for w in (1,2,4)}
        logs[4]=logs[4].replace("hihash=000000000000000b",
                                 "hihash=0000000000000000",1)
        with self.assertRaises(BadTrace):
            verify(synthetic(),record_log("record"),logs)
    def test_different_combined_replay_signature(self):
        logs={w:replay_log() for w in (1,2,4)}
        logs[2]=logs[2].replace("combined=0000000000001234",
                                 "combined=0000000000001235",1)
        with self.assertRaises(BadTrace):
            verify(synthetic(),record_log("record"),logs)
    def test_no_second_worker(self):
        with self.assertRaises(BadTrace):
            verify(synthetic(),record_log("record"),{1:replay_log(),4:replay_log()})
    def test_truncated_recorded_log(self):
        with self.assertRaises(BadTrace):
            verify(synthetic(),"\n".join(record_log("record").splitlines()[:3]),
                   {1:replay_log(),2:replay_log(),4:replay_log()})
    def test_missing_original_replay_summary(self):
        with self.assertRaises(BadTrace):
            verify(synthetic(),record_log("record"),
                   {1:record_log("replay"),2:replay_log(),4:replay_log()})
    def test_not_a_primitive(self):
        raw=bytearray(synthetic())
        # First command after two uploads+environment must be P.
        records=parse_vht(bytes(raw))
        self.assertGreater(len(records),4)
        self.assertEqual(records[3][0],b"P")
        # Keep binary parser strict on unexpected record kind.
        with self.assertRaises(BadTrace):
            audit_trace(bytes(raw).replace(b"P"+struct.pack("<I",4),
                                           b"Q"+struct.pack("<I",4),1))
if __name__=="__main__":unittest.main()
