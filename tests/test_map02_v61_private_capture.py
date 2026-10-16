#!/usr/bin/env python3
"""v61 local-private GPU capture safety and state-persistence adversarial tests."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
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
from tools.make_map02_v60_synthetic_dma import generate,polygon
from tools.verify_map02_v60_ps1_dma import decode,parse_gp0,DmaError
from tools.audit_map02_v61_private_capture import (
    CONTEXT_SCHEMA,check_context,local_bytes,local_json,
    audit_private,main
)

def evidence():
    raw,manifest=generate()
    return raw,manifest

def context(frame_count=4):
    return {
        "schema":CONTEXT_SCHEMA,
        "method":"emulator-debugger",
        "scope":"MAP02",
        "frame_indices":list(range(frame_count)),
        "reset_status":"no-reset-observed"
    }

def changed(data,needle,replacement,occurrence=0):
    old=struct.pack("<I",needle)
    hit=0
    for i in range(0,len(data),4):
        if data[i:i+4]==old:
            if hit==occurrence:
                result=bytearray(data)
                struct.pack_into("<I",result,i,replacement)
                return bytes(result)
            hit+=1
    raise AssertionError("mutation anchor missing")

def corrected_manifest(data,m):
    return dict(m,sha256=hashlib.sha256(data).hexdigest())

class PrivateCaptureTests(unittest.TestCase):
    def setUp(self):
        self.ram,self.manifest=evidence()

    def test_synthetic_closed_provenance(self):
        r=audit_private(self.ram,self.manifest)
        self.assertEqual(r["status"],"synthetic_private_preflight_only")
        self.assertEqual((r["frames"],r["dma_nodes"],r["gp0_e6_commands"]), (4,19,11))
        self.assertFalse(r["retail_gp0_provenance_verified"])
        self.assertFalse(r["original_retail_MAP02_verified"])
        self.assertFalse(r["HD_replacement_approved"])
        self.assertFalse(r["raw_gpu_payload_exported"])

    def test_claimed_user_owned_capture_still_unverified(self):
        m=dict(self.manifest,source_class="user-supplied-unverified")
        r=audit_private(self.ram,m,context())
        self.assertEqual(r["status"],"unverified_private_capture_structurally_valid")
        self.assertTrue(r["game_scope_claimed_MAP02"])
        self.assertFalse(r["retail_gp0_provenance_verified"])
        self.assertTrue(r["inter_frame_gpu_reset_unverified"])

    def test_summary_contains_no_raw_gpu_words_or_coordinates(self):
        r=audit_private(self.ram,self.manifest,context())
        data=json.dumps(r)
        for leak in ("e6000001","0xe6000001","x0","y0","u0","v0",
                     "entry_points","base_address","frame_indices","emulator-debugger"):
            self.assertNotIn(leak,data)
        self.assertEqual(r["e6_state_transition_events"],11)

    def test_optional_comparison_same_bytes_not_independent(self):
        r=audit_private(self.ram,self.manifest,comparison=(self.ram,self.manifest))
        self.assertTrue(r["comparison_performed"])
        self.assertTrue(r["comparison_semantic_order_equal"])
        self.assertTrue(r["comparison_identical_RAM_bytes"])
        self.assertFalse(r["independent_capture_proven"])

    def test_optional_comparison_different_bytes_same_semantics(self):
        # Unvisited RAM gap at the end after linked-list data; hashed input changes,
        # executed command meaning does not.
        data=self.ram+b"\x00\x00\x00\x00"
        m=corrected_manifest(data,self.manifest)
        r=audit_private(self.ram,self.manifest,comparison=(data,m))
        self.assertTrue(r["comparison_performed"])
        self.assertFalse(r["comparison_identical_RAM_bytes"])
        self.assertFalse(r["independent_capture_proven"])

    def test_modified_mask_command_refused_on_semantic_comparison(self):
        raw=changed(self.ram,0xe6000001,0xe6000000)
        with self.assertRaises(DmaError):
            audit_private(self.ram,self.manifest,comparison=(raw,corrected_manifest(raw,self.manifest)))

    def test_modified_quad_uv_refused_on_semantic_comparison(self):
        raw=changed(self.ram,0x0000c014,0x0000c013)
        with self.assertRaises(DmaError):
            audit_private(self.ram,self.manifest,comparison=(raw,corrected_manifest(raw,self.manifest)))

    def test_truncated_source_refused(self):
        with self.assertRaises(DmaError):
            audit_private(self.ram[:-4],self.manifest)

    def test_capture_context_requires_explicit_fields(self):
        c=context(); del c["scope"]
        with self.assertRaises(DmaError):
            audit_private(self.ram,self.manifest,c)

    def test_context_rejects_injected_private_notes(self):
        c=context();c["user_email"]="someone@example.com"
        with self.assertRaises(DmaError):
            check_context(c,4)

    def test_context_rejects_self_attested_authenticity(self):
        c=context();c["retail_provenance_verified"]=True
        with self.assertRaises(DmaError):
            check_context(c,4)

    def test_context_rejects_unordered_frames(self):
        c=context();c["frame_indices"]=[0,2,1,3]
        with self.assertRaises(DmaError):
            check_context(c,4)

    def test_context_rejects_bool_frame_indices(self):
        c=context();c["frame_indices"]=[False,1,2,3]
        with self.assertRaises(DmaError):
            check_context(c,4)

    def test_context_rejects_bad_reset_assertion(self):
        c=context();c["reset_status"]="reset-confirmed-by-magic"
        with self.assertRaises(DmaError):
            check_context(c,4)

    def test_context_refuses_extra_session_tokens(self):
        c=context();c["private_disc_id"]="ABC123"
        with self.assertRaises(DmaError):
            check_context(c,4)

    def test_e6_state_persists_within_consecutive_dma_frames(self):
        # Frame 0 finishes with GP0(E6)=2. Frame 1 has E6=1 before its
        # first FT4. Replace that first frame-1 E6 with GP0(E1) instead:
        # no E6 reset is present, so the first FT4 must see maskCheck=1.
        new=changed(self.ram,0xe6000001,0xe1000000,occurrence=1)
        d=decode(new,corrected_manifest(new,self.manifest))
        first_ft4=next(e for e in d["frames"][1]["events"] if e["type"]=="FT4")
        self.assertEqual((first_ft4["mask_set"],first_ft4["mask_check"]),(0,1))

    def test_gp0_parser_returns_checked_end_state(self):
        words=[0xe6000003]+polygon(0,0,0x001f,0)
        ev,end=parse_gp0(words,return_state=True)
        self.assertEqual(end,(1,1))
        self.assertEqual((ev[-1]["mask_set"],ev[-1]["mask_check"]),(1,1))
        self.assertEqual(parse_gp0(polygon(0,0,0x001f,0),
                                  initial_mask=end)[0]["mask_check"],1)

    def test_initial_gpu_state_must_be_boolean_int(self):
        with self.assertRaises(DmaError):
            parse_gp0([0xe6000000],initial_mask=(True,False))

    def test_duplicate_json_key_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"m.json"
            p.write_text('{"sha256":"one","sha256":"two"}')
            with self.assertRaises(DmaError):
                local_json(p,8192)

    def test_symlink_capture_input_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            src=root/"ram.bin";src.write_bytes(self.ram)
            link=root/"ram-link.bin";link.symlink_to(src)
            with self.assertRaises(DmaError):local_bytes(link,4*1024*1024)

    def test_directory_as_capture_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(DmaError):local_bytes(Path(temp),4*1024*1024)

    def test_oversized_input_refused_before_read(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"oversize.bin"
            with p.open("wb") as f: f.truncate(4*1024*1024+1)
            with self.assertRaises(DmaError):local_bytes(p,4*1024*1024)

    def test_local_cli_writes_sanitized_report_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ram=root/"PRIVATE_RAM.bin"
            manifest=root/"meta.json"
            ctx=root/"context.json"
            output=root/"safe_report.json"
            ram.write_bytes(self.ram)
            manifest.write_text(json.dumps(self.manifest))
            ctx.write_text(json.dumps(context()))
            argv=["audit","--ram",str(ram),"--manifest",str(manifest),
                  "--context",str(ctx),"--output",str(output)]
            stdout=StringIO()
            with patch.object(sys,"argv",argv),redirect_stdout(stdout):
                code=main()
            self.assertEqual(code,0)
            rep=json.loads(output.read_text())
            self.assertEqual(rep["status"],"synthetic_private_preflight_only")
            self.assertNotIn(str(root),stdout.getvalue())
            self.assertNotIn("e6000001",output.read_text())

    def test_local_cli_rejects_overwriting_capture_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ram=root/"raw.bin";ram.write_bytes(self.ram)
            manifest=root/"meta.json";manifest.write_text(json.dumps(self.manifest))
            stderr=StringIO()
            with patch.object(sys,"argv",["audit","--ram",str(ram),
                                        "--manifest",str(manifest),
                                        "--output",str(ram)]),redirect_stderr(stderr),redirect_stdout(StringIO()):
                self.assertEqual(main(),2)
            self.assertEqual(ram.read_bytes(),self.ram)

    def test_local_cli_refuses_symlink_report_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ram=root/"raw.bin";ram.write_bytes(self.ram)
            manifest=root/"meta.json";manifest.write_text(json.dumps(self.manifest))
            safe=root/"safe.json";safe.write_text("original")
            link=root/"out.json";link.symlink_to(safe)
            with patch.object(sys,"argv",["audit","--ram",str(ram),
                                          "--manifest",str(manifest),
                                          "--output",str(link)]),redirect_stderr(StringIO()),redirect_stdout(StringIO()):
                self.assertEqual(main(),2)
            self.assertEqual(safe.read_text(),"original")

    def test_local_cli_sanitizes_corrupted_sha_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ram=root/"secret.bin";ram.write_bytes(self.ram)
            meta=root/"manifest.json"
            meta.write_text(json.dumps(dict(self.manifest,sha256="0"*64)))
            out=StringIO()
            with patch.object(sys,"argv",["audit","--ram",str(ram),
                                          "--manifest",str(meta)]),redirect_stdout(out):
                self.assertEqual(main(),1)
            self.assertNotIn(str(root),out.getvalue())
            self.assertNotIn("e6000001",out.getvalue())
            self.assertEqual(json.loads(out.getvalue())["status"],"refused")

if __name__=="__main__":unittest.main()
