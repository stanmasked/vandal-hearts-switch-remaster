#!/usr/bin/env python3
"""v68 direct CPU-GP0 MMIO mixed with DMA2, GP1 and immutable RAM tests."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch
from contextlib import redirect_stdout
from io import StringIO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_map02_v68_mixed_gpu import audit,main,DmaError
from tools.audit_map02_v67_versioned_ram import manifest_for_frames
from tools.ingest_map02_v65_gpu_probe import SCHEMA as PROBE_SCHEMA
from tests.test_map02_v67_versioned_ram import cases

def generate():
    frames,meta,raw,entries=cases()
    records=copy.deepcopy(entries)
    for i in range(4):
        idx=next(n for n,e in enumerate(records)
                 if e["kind"]=="GP0_DMA2" and e["frame"]==i)
        records.insert(idx,{"kind":"GP0_MMIO","frame":i,
                            "word":0xe6000000|(i&3),"tick":0})
    for i,e in enumerate(records[1:]): e["tick"]=i+101
    return frames,meta,records

def serialize(records):
    return ("\n".join(json.dumps(e,sort_keys=True) for e in records)+"\n").encode()

class MixedGP0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames,cls.meta,cls.records=generate()
        cls.log=serialize(cls.records)
    def refusal(self,records=None,frames=None,meta=None):
        with self.assertRaises((DmaError,ValueError,TypeError)):
            audit(self.frames if frames is None else frames,
                  self.meta if meta is None else meta,
                  self.log if records is None else serialize(records))
    def test_four_direct_four_dma_two_gp1(self):
        r=audit(self.frames,self.meta,self.log)
        self.assertEqual(r["status"],"unverified_mixed_gpu_port_consistent")
        self.assertEqual((r["frames"],r["direct_gp0_mmio_words"],r["gp0_dma2_submissions"]),(4,4,4))
        self.assertEqual(r["dma_gp0_words"],80)
        self.assertEqual(r["total_gp0_input_words"],84)
        self.assertEqual((r["gp1_full_reset_events"],r["gp1_fifo_reset_events"]),(1,1))
    def test_e6_registers_combined_with_dma(self):
        r=audit(self.frames,self.meta,self.log)
        self.assertEqual(r["gpu_drawing_register_events"],17)
        self.assertTrue(r["direct_plus_dma_gp0_packets_bounded"])
    def test_retail_provenance_never_claimed(self):
        r=audit(self.frames,self.meta,self.log)
        for k in ("real_game_boot_verified","gpu_plugin_fifo_consumption_verified",
                  "independent_capture_provenance_verified","retail_gp0_provenance_verified",
                  "original_retail_MAP02_verified","HD_replacement_approved",
                  "raw_gpu_payload_exported"):
            self.assertFalse(r[k],k)
    def test_no_direct_event_legacy_supported(self):
        e=[x for x in self.records if x["kind"]!="GP0_MMIO"]
        r=audit(self.frames,self.meta,serialize(e))
        self.assertEqual(r["direct_gp0_mmio_words"],0)
        self.assertEqual(r["dma_gp0_words"],80)
    def test_direct_rect_packet_containing_deceptive_e6(self):
        events=copy.deepcopy(self.records)
        idx=next(i for i,e in enumerate(events) if e["kind"]=="GP0_MMIO")
        events[idx:idx]=[
          {"kind":"GP0_MMIO","frame":0,"word":0x600000ff,"tick":0},
          {"kind":"GP0_MMIO","frame":0,"word":0x00020001,"tick":0},
          {"kind":"GP0_MMIO","frame":0,"word":0xe6000003,"tick":0}
        ]
        for i,e in enumerate(events[1:]):e["tick"]=100+i
        r=audit(self.frames,self.meta,serialize(events))
        self.assertEqual(r["direct_gp0_mmio_words"],7)
        self.assertEqual(r["gpu_drawing_register_events"],17)
        self.assertEqual(r["drawing_or_transfer_packets"],11)
    def test_multiword_direct_gp0_fill_then_dma(self):
        e=copy.deepcopy(self.records)
        idx=next(i for i,x in enumerate(e) if x["kind"]=="GP0_MMIO")
        e[idx:idx]=[{"kind":"GP0_MMIO","frame":0,"word":x,"tick":0}
                    for x in (0x020000ff,0x00000000,0x00040004)]
        for i,x in enumerate(e[1:]):x["tick"]=100+i
        r=audit(self.frames,self.meta,serialize(e))
        self.assertEqual(r["direct_gp0_mmio_words"],7)
    def test_incomplete_direct_gp0_at_gp1_rejected(self):
        e=copy.deepcopy(self.records)
        idx=next(i for i,x in enumerate(e) if x["kind"]=="GP1_WRITE")
        e.insert(idx,{"kind":"GP0_MMIO","frame":2,"word":0x600000ff,"tick":0})
        for i,x in enumerate(e[1:]):x["tick"]=100+i
        self.refusal(records=e)
    def test_dangling_direct_after_last_dma_rejected(self):
        e=copy.deepcopy(self.records)
        e.append({"kind":"GP0_MMIO","frame":4,"word":0xe6000001,"tick":999})
        self.refusal(records=e)
    def test_wrong_direct_frame_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["frame"]=2
        self.refusal(records=e)
    def test_direct_bool_word_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["word"]=True
        self.refusal(records=e)
    def test_direct_negative_word_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["word"]=-1
        self.refusal(records=e)
    def test_direct_out_of_range_word_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["word"]=1<<32
        self.refusal(records=e)
    def test_direct_event_sensitive_extra_field_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["private_disc"]="XXXX"
        self.refusal(records=e)
    def test_direct_reserved_mask_bits_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["word"]=0xe6000007
        self.refusal(records=e)
    def test_direct_unknown_opcode_refused(self):
        e=copy.deepcopy(self.records)
        e[1]["word"]=0xf0000000
        self.refusal(records=e)
    def test_gp1_invalid_opcode_refused(self):
        e=copy.deepcopy(self.records)
        next(x for x in e if x["kind"]=="GP1_WRITE")["word"]=0x02000000
        self.refusal(records=e)
    def test_duplicate_gp1_refused(self):
        e=copy.deepcopy(self.records)
        idx=next(i for i,x in enumerate(e) if x["kind"]=="GP1_WRITE")
        x=copy.deepcopy(e[idx])
        e.insert(idx,x)
        for i,x in enumerate(e[1:]):x["tick"]=100+i
        self.refusal(records=e)
    def test_wrong_dma_head_refused(self):
        e=copy.deepcopy(self.records)
        next(x for x in e if x["kind"]=="GP0_DMA2")["head"]+=4
        self.refusal(records=e)
    def test_wrong_dma_payload_refused(self):
        e=copy.deepcopy(self.records)
        next(x for x in e if x["kind"]=="GP0_DMA2")["words"][0]^=1
        self.refusal(records=e)
    def test_swapped_ram_versions_refused(self):
        f=list(self.frames)
        f[0],f[3]=f[3],f[0]
        self.refusal(frames=f)
    def test_forged_gp1_remains_unverified(self):
        e=copy.deepcopy(self.records)
        next(x for x in e if x["kind"]=="GP1_WRITE")["word"]=0x01000000
        report=audit(self.frames,self.meta,serialize(e))
        self.assertEqual(report["gp1_full_reset_events"],0)
        self.assertFalse(report["gpu_plugin_fifo_consumption_verified"])
    def test_nonmonotonic_clock_refused(self):
        e=copy.deepcopy(self.records)
        e[2]["tick"]=e[1]["tick"]
        self.refusal(records=e)
    def test_missing_frame_refused(self):
        e=[x for x in self.records if x.get("frame")!=3]
        self.refusal(records=e)
    def test_cli_safe_report_without_raw_gp0(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            ram=p/"ram";ram.mkdir()
            for i,v in enumerate(self.frames):
                (ram/f"frame-{i:06d}.ram").write_bytes(v)
            meta=p/"meta.json";meta.write_text(json.dumps(self.meta))
            probe=p/"private.jsonl";probe.write_bytes(self.log)
            report=p/"safe.json"
            with mock_patch.object(sys,"argv",["v68","--snapshot-dir",str(ram),
                 "--manifest",str(meta),"--probe",str(probe),
                 "--output",str(report)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            s=report.read_text()
            self.assertEqual(json.loads(s)["direct_gp0_mmio_words"],4)
            self.assertNotIn("e6000003",s)
            self.assertNotIn(str(p),s)
    def test_cli_refuses_malformed_direct_record(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);ram=p/"ram";ram.mkdir()
            for i,v in enumerate(self.frames):
                (ram/f"frame-{i:06d}.ram").write_bytes(v)
            meta=p/"meta.json";meta.write_text(json.dumps(self.meta))
            probe=p/"private.jsonl";probe.write_bytes(self.log[:-1])
            output=StringIO()
            with mock_patch.object(sys,"argv",["v68","--snapshot-dir",str(ram),
                 "--manifest",str(meta),"--probe",str(probe)]),redirect_stdout(output):
                self.assertEqual(main(),1)
            self.assertEqual(json.loads(output.getvalue())["status"],"refused")

if __name__=="__main__":
    unittest.main()
