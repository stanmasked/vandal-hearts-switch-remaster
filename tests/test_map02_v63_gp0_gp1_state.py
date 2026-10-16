#!/usr/bin/env python3
"""v63 GP0 E1-E6 register semantics and GP1 reset provenance tests."""
from __future__ import annotations
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_map02_v63_gp0_gp1_state import (
    GP1_SCHEMA,GpuState,apply_gp0_state,texture_window_uv,interpret_capture,
    interpret_words,check_gp1_sidecar,audit,main
)
from tools.make_map02_v63_state_fixture import (
    generate,ft4,MODE0,MODE2,WIN0,E1_0,E2_0,E3_0,E4_0,E5_0,E6_0
)
from tools.verify_map02_v60_ps1_dma import DmaError

def changed(raw,word,replacement,n=0):
    p=struct.pack("<I",word)
    matches=[i for i in range(0,len(raw),4) if raw[i:i+4]==p]
    assert len(matches)>n,(hex(word),len(matches))
    b=bytearray(raw)
    struct.pack_into("<I",b,matches[n],replacement)
    return bytes(b)

def rehash(raw,manifest):
    return dict(manifest,sha256=hashlib.sha256(raw).hexdigest())

class GP0GP1StateTests(unittest.TestCase):
    def setUp(self):
        self.ram,self.manifest,self.gp1=generate()

    def test_fixture_and_private_gate(self):
        a=audit(self.ram,self.manifest,self.gp1)
        self.assertEqual(a["status"],"synthetic_gp0_gp1_state_verified")
        self.assertEqual((a["frames"],a["dma_nodes"]),(4,19))
        self.assertEqual(a["gp0_e1_to_e6_register_commands"],13)
        self.assertEqual(a["draws_and_transfers_with_state_snapshots"],10)
        self.assertEqual((a["claimed_gp1_full_resets"],a["claimed_gp1_fifo_resets"]),(1,1))
        self.assertFalse(a["actual_gp1_commands_observed_on_hardware"])
        self.assertFalse(a["HD_replacement_approved"])
        self.assertFalse(a["retail_gp0_provenance_verified"])

    def test_all_registers_first_frame(self):
        f=interpret_capture(self.ram,self.manifest,self.gp1)["frames"][0]
        self.assertEqual([e["opcode"] for e in f["events"] if e["kind"]=="REGISTER"],
                         [0xe1,0xe2,0xe3,0xe4,0xe5,0xe6])
        draw=next(x for x in f["events"] if x["kind"]=="POLYGON")
        st=draw["state"]
        self.assertEqual(st["draw_mode"],{
            "tpage_x":192,"tpage_y":256,"abr":2,
            "texture_format":2,"dithering":1,"draw_to_display":1})
        self.assertEqual(st["texture_window"],{
            "mask_x":1,"mask_y":3,"offset_x":1,"offset_y":2})
        self.assertEqual(st["drawing_area"],{
            "x0":64,"y0":70,"x1":200,"y1":180,"inclusive":True})
        self.assertEqual(st["drawing_offset"],{"x":-24,"y":15})
        self.assertEqual((st["mask_set"],st["mask_check"]),(1,1))

    def test_e2_uv_mask_formula(self):
        s=apply_gp0_state(GpuState(),E2_0)
        self.assertEqual(texture_window_uv(55,77,s),(63,85))
        self.assertEqual(texture_window_uv(255,255,GpuState()),(255,255))

    def test_e2_offset_and_mask_cannot_escape_byte(self):
        s=apply_gp0_state(GpuState(),0xe2000000 | (31<<10))
        self.assertEqual(texture_window_uv(253,170,s),(253,170))
        for u,v in ((-1,0),(0,-1),(256,0),(0,256),(True,9)):
            with self.subTest(u=u,v=v),self.assertRaises(DmaError):
                texture_window_uv(u,v,s)

    def test_signed_offset_boundaries(self):
        for x,y in ((-1024,1023),(1023,-1024),(-1,-1),(0,0)):
            with self.subTest(x=x,y=y):
                w=0xe5000000 | (x&0x7ff) | ((y&0x7ff)<<11)
                from tools.audit_map02_v63_gp0_gp1_state import _register_fields
                state=apply_gp0_state(GpuState(),w)
                self.assertEqual(_register_fields(state)["drawing_offset"],{"x":x,"y":y})

    def test_e3_e4_inclusive_area(self):
        f=interpret_capture(self.ram,self.manifest,self.gp1)["frames"][0]
        a=next(e["state"]["drawing_area"] for e in f["events"] if e["kind"]=="POLYGON")
        self.assertTrue(a["inclusive"])
        self.assertEqual((a["x0"],a["y0"],a["x1"],a["y1"]),(64,70,200,180))

    def test_first_draw_next_frame_carries_all_register_state(self):
        frames=interpret_capture(self.ram,self.manifest,self.gp1)["frames"]
        self.assertEqual(frames[1]["before"],frames[0]["after"])
        draw=next(e for e in frames[1]["events"] if e["kind"]=="POLYGON")
        state=draw["state"]
        self.assertEqual(state["draw_mode"]["abr"],2)
        self.assertEqual(state["drawing_offset"]["x"],-24)
        self.assertEqual(state["mask_check"],1)

    def test_e2_update_preserves_e1_and_mask(self):
        f=interpret_capture(self.ram,self.manifest,self.gp1)["frames"][1]
        rect=next(e for e in f["events"] if e["kind"]=="RECT")
        self.assertEqual(rect["state"]["texture_window"]["mask_x"],31)
        self.assertEqual(rect["state"]["draw_mode"]["abr"],2)
        self.assertEqual((rect["state"]["mask_set"],rect["state"]["mask_check"]),(1,1))

    def test_cpu_upload_looks_like_e6_but_has_no_state_change(self):
        f=interpret_capture(self.ram,self.manifest,self.gp1)["frames"][1]
        self.assertEqual(len([e for e in f["events"] if e["kind"]=="REGISTER"]),1)
        upload=next(e for e in f["events"] if e["kind"]=="VRAM_TRANSFER")
        self.assertEqual((upload["state"]["mask_set"],upload["state"]["mask_check"]),(1,1))

    def test_gp1_00_resets_before_frame_two_draw(self):
        frames=interpret_capture(self.ram,self.manifest,self.gp1)["frames"]
        self.assertEqual(frames[2]["boundary"],0)
        self.assertEqual(frames[2]["before"],GpuState())
        first=next(e for e in frames[2]["events"] if e["kind"]=="POLYGON")
        self.assertEqual(first["state"]["draw_mode"]["abr"],0)
        self.assertEqual((first["state"]["mask_set"],first["state"]["mask_check"]),(0,0))

    def test_gp1_01_fifo_does_not_reset_draw_state(self):
        frames=interpret_capture(self.ram,self.manifest,self.gp1)["frames"]
        self.assertEqual(frames[3]["boundary"],0x01000000)
        self.assertEqual(frames[3]["before"],frames[2]["after"])
        first=next(e for e in frames[3]["events"] if e["kind"]=="POLYGON")
        self.assertEqual(first["state"]["draw_mode"]["abr"],1)
        self.assertEqual((first["state"]["mask_set"],first["state"]["mask_check"]),(1,0))
        polygons=[e for e in frames[3]["events"] if e["kind"]=="POLYGON"]
        self.assertEqual((polygons[1]["state"]["mask_set"],
                          polygons[1]["state"]["mask_check"]),(0,1))

    def test_no_sidecar_does_not_fabricate_gp1_reset(self):
        frames=interpret_capture(self.ram,self.manifest)["frames"]
        self.assertIsNone(frames[2]["boundary"])
        before=next(e for e in frames[2]["events"] if e["kind"]=="POLYGON")
        self.assertEqual(before["state"]["draw_mode"]["abr"],2)
        self.assertEqual((before["state"]["mask_set"],before["state"]["mask_check"]),(1,1))
        self.assertFalse(audit(self.ram,self.manifest)["gp1_sidecar_supplied"])

    def test_vram_fill_does_not_obey_mask(self):
        frames=interpret_capture(self.ram,self.manifest,self.gp1)["frames"]
        fill=next(e for e in frames[0]["events"] if e["kind"]=="FILL_VRAM")
        self.assertFalse(fill["mask_applies"])
        self.assertEqual(len([e for e in frames[0]["events"] if e["kind"]=="REGISTER"]),6)

    def test_unverified_source_stays_unverified_with_sidecar(self):
        m=dict(self.manifest,source_class="user-supplied-unverified")
        r=audit(self.ram,m,self.gp1)
        self.assertEqual(r["status"],"unverified_capture_gp0_gp1_structurally_valid")
        self.assertFalse(r["actual_gp1_commands_observed_on_hardware"])
        self.assertFalse(r["original_retail_MAP02_verified"])

    def test_context_json_duplicate_frame_index_refused(self):
        bad={"schema":GP1_SCHEMA,"events":[
            {"before_frame":2,"word":0},
            {"before_frame":2,"word":0x01000000}]}
        with self.assertRaises(DmaError):
            check_gp1_sidecar(bad,4)

    def test_context_json_unsorted_event_refused(self):
        bad={"schema":GP1_SCHEMA,"events":[
            {"before_frame":3,"word":0x01000000},
            {"before_frame":2,"word":0}]}
        with self.assertRaises(DmaError):
            check_gp1_sidecar(bad,4)

    def test_context_json_out_of_bounds_refused(self):
        for index in (-1,4,True,9):
            with self.subTest(index=index),self.assertRaises(DmaError):
                check_gp1_sidecar({"schema":GP1_SCHEMA,"events":[
                    {"before_frame":index,"word":0}]},4)

    def test_context_json_forbidden_gp1_commands_refused(self):
        for word in (0x02000000,0x03000000,0x00000001,0x01000001,0xe6000003,True,-1):
            with self.subTest(word=word),self.assertRaises(DmaError):
                check_gp1_sidecar({"schema":GP1_SCHEMA,"events":[
                    {"before_frame":1,"word":word}]},4)

    def test_context_json_self_attested_retail_field_refused(self):
        side=dict(self.gp1,retail_gp1_proven=True)
        with self.assertRaises(DmaError):
            check_gp1_sidecar(side,4)

    def test_context_json_unsanctioned_user_path_field_refused(self):
        s={"schema":GP1_SCHEMA,"events":[
            {"before_frame":2,"word":0,"private_disc_id":"bad"}]}
        with self.assertRaises(DmaError):check_gp1_sidecar(s,4)

    def test_invalid_gp0_e1_reserved_bits_refused(self):
        raw=changed(self.ram,E1_0,E1_0|0x800)
        with self.assertRaises(DmaError):
            interpret_capture(raw,rehash(raw,self.manifest),self.gp1)

    def test_invalid_gp0_e2_reserved_bits_refused(self):
        raw=changed(self.ram,E2_0,E2_0|0x100000)
        with self.assertRaises(DmaError):
            interpret_capture(raw,rehash(raw,self.manifest),self.gp1)

    def test_invalid_gp0_e3_reserved_bits_refused(self):
        raw=changed(self.ram,E3_0,E3_0|0x80000)
        with self.assertRaises(DmaError):
            interpret_capture(raw,rehash(raw,self.manifest),self.gp1)

    def test_invalid_gp0_e4_reserved_bits_refused(self):
        raw=changed(self.ram,E4_0,E4_0|0x80000)
        with self.assertRaises(DmaError):
            interpret_capture(raw,rehash(raw,self.manifest),self.gp1)

    def test_invalid_gp0_e5_reserved_bits_refused(self):
        raw=changed(self.ram,E5_0,E5_0|0x400000)
        with self.assertRaises(DmaError):
            interpret_capture(raw,rehash(raw,self.manifest),self.gp1)

    def test_invalid_gp0_e6_reserved_bits_refused(self):
        raw=changed(self.ram,E6_0,E6_0|0x4)
        with self.assertRaises(DmaError):
            interpret_capture(raw,rehash(raw,self.manifest),self.gp1)

    def test_unrelated_command_cannot_be_register(self):
        with self.assertRaises(DmaError):
            apply_gp0_state(GpuState(),0x2c808080)

    def test_truncated_gpu_polygon_refused(self):
        with self.assertRaises(DmaError):
            interpret_words([0x2c808080]+[0]*7,GpuState())

    def test_state_word_inside_texture_coord_is_not_e6(self):
        a,_=interpret_words(ft4()+[0xe6000002],GpuState())
        self.assertEqual([e["kind"] for e in a],["POLYGON","REGISTER"])
        self.assertEqual(a[0]["state"]["mask_set"],0)
        self.assertEqual(a[1]["state"]["mask_check"],1)

    def test_sanitized_report_never_exposes_source_words_or_pixels(self):
        r=audit(self.ram,self.manifest,self.gp1)
        s=json.dumps(r)
        for fragment in ("e6000003","x0","y0","tpage_x","frame_indices",
                         "entry_points","source_file","texture_window"):
            self.assertNotIn(fragment,s)

    def test_cli_writes_sanitized_audit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            rp,mp,gp,out=[root/x for x in ("ram.bin","manifest.json","gp1.json","summary.json")]
            rp.write_bytes(self.ram)
            mp.write_text(json.dumps(self.manifest))
            gp.write_text(json.dumps(self.gp1))
            with patch.object(sys,"argv",["v63","--ram",str(rp),"--manifest",str(mp),
                                         "--gp1",str(gp),"--output",str(out)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            report=json.loads(out.read_text())
            self.assertEqual(report["gp0_e1_to_e6_register_commands"],13)
            self.assertFalse(report["raw_gpu_payload_exported"])
            self.assertNotIn(str(root),out.read_text())

    def test_cli_refuses_unknown_GP1_evidence_and_sanitizes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            rp,mp,gp=[root/x for x in ("secret_ram.bin","manifest.json","gp1.json")]
            rp.write_bytes(self.ram)
            mp.write_text(json.dumps(self.manifest))
            gp.write_text(json.dumps({"schema":GP1_SCHEMA,"events":[
                {"before_frame":1,"word":0x02000000}]}))
            out=StringIO()
            with patch.object(sys,"argv",["v63","--ram",str(rp),"--manifest",str(mp),
                                         "--gp1",str(gp)]),redirect_stdout(out):
                self.assertEqual(main(),1)
            self.assertNotIn(str(root),out.getvalue())
            self.assertEqual(json.loads(out.getvalue())["status"],"refused")

if __name__=="__main__":unittest.main()
