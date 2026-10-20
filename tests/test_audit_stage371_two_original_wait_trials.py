#!/usr/bin/env python3
"""Stage371 source-scope negative controls (synthetic, NOT authentic NeXium)."""
import copy
import json
import struct
import zlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_stage371_two_original_wait_trials as a
from test_audit_nexium_stage368_wait_descriptor import make_sources

RUN=39395120000
SHA="a"*40

def png_chunk(kind:bytes,data:bytes)->bytes:
    return (struct.pack(">I",len(data))+kind+data+
            struct.pack(">I",zlib.crc32(kind+data)))

def make_synthetic_png()->bytes:
    # Structurally valid blank PNG, NOT a genuine optical NeXium capture.
    scanline=b"\x00"+b"\x00"*(1280*3)
    return (b"\x89PNG\r\n\x1a\n"+
            png_chunk(b"IHDR",struct.pack(">IIBBBBB",1280,720,8,2,0,0,0))+
            png_chunk(b"IDAT",zlib.compress(scanline*720))+
            png_chunk(b"IEND",b""))

def layout(temp:Path,code_a=7,code_b=7):
    a_root=temp/"outputs"/"a"
    b_root=temp/"outputs"/"b"
    for tag,path,code in (("a",a_root,code_a),("b",b_root,code_b)):
        path.mkdir(parents=True)
        original=temp/f"vh-nexium-stage266-{RUN}-{tag}"
        sd=original/a.RUN_GUEST_PATH
        params=(code,0xEA01,0,0,0) if code==4 else (code,0,1,1,1)
        make_sources(sd,*params)
        (path/"guest-sd-root.txt").write_text(str(original)+"\n")
        (path/"scene-optical-trace.png").write_bytes(make_synthetic_png())
    preflight={"result":a.EXPECTED_NRO,"git_sha":SHA,
               "run_id":RUN,"run_attempt":1,"nro_sha256":"b"*64,
               "nro_bytes":100000,"hardware_status":"HARDWARE NOT TESTED"}
    return a_root,b_root,preflight

class Stage371Tests(unittest.TestCase):
    def setUp(self):
        self.holder=tempfile.TemporaryDirectory()
        self.addCleanup(self.holder.cleanup)
        self.temp=Path(self.holder.name)
        self.one,self.two,self.preflight=layout(self.temp)
    def verify(self,**kw):
        args=dict(run_id=RUN,git_sha=SHA,attempt=1,
                  runner_temp=self.temp,preflight=self.preflight,
                  trial_a=self.one,trial_b=self.two)
        args.update(kw)
        return a.audit(**args)
    def test_two_sources_one_nro_and_explicit_noncausal_scope(self):
        report=self.verify()
        self.assertEqual(report["result"],a.VERDICT)
        self.assertEqual(len(report["captures"]),2)
        self.assertEqual([c["original_service_result"] for c in report["captures"]],[0,0])
        self.assertNotEqual(report["captures"][0]["source_guest_sd_root"],
                            report["captures"][1]["source_guest_sd_root"])
        self.assertFalse(report["old_0xEA01_root_cause_proven"])
        self.assertFalse(report["physical_nintendo_switch_audio_tested"])
        self.assertTrue(report["two_dwell_observations_are_not_a_controlled_causal_pair"])
    def test_synthetic_timeout_must_not_infer_old_cause(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            one,two,nro=layout(root,code_a=4,code_b=7)
            report=a.audit(RUN,SHA,1,root,nro,one,two)
            self.assertEqual(report["captures"][0]["original_service_result"],0xEA01)
            self.assertEqual(report["captures"][0]["reported_return_count"],0)
            self.assertFalse(report["old_0xEA01_root_cause_proven"])
    def test_old_or_same_guest_sd_root_rejected(self):
        guest=self.two/"guest-sd-root.txt"
        orig=guest.read_text()
        guest.write_text((self.one/"guest-sd-root.txt").read_text())
        with self.assertRaises(ValueError):self.verify()
        guest.write_text(orig)
        with self.assertRaises(ValueError):self.verify(trial_b=self.one)
    def test_wrong_nro_source_run_attempt_rejected(self):
        for key,value in (("run_id",RUN+1),("git_sha","f"*40),
                          ("run_attempt",2),("nro_sha256","bad"),
                          ("hardware_status","TESTED")):
            with self.subTest(key=key):
                x=copy.deepcopy(self.preflight);x[key]=value
                with self.assertRaises(ValueError):self.verify(preflight=x)
    def test_missing_forged_or_duplicated_guest_source_rejected(self):
        sd=self.temp/f"vh-nexium-stage266-{RUN}-b"/a.RUN_GUEST_PATH
        path=sd/"audio-exit-wait-descriptor-000.csv"
        previous=path.read_bytes()
        path.write_bytes(previous.replace(b"released_count_reported,1",
                                          b"released_count_reported,0"))
        with self.assertRaises(ValueError):self.verify()
        path.write_bytes(previous)
        extra=sd/"audio-exit-wait-descriptor-001.csv"
        extra.write_bytes(previous)
        with self.assertRaises(ValueError):self.verify()
        extra.unlink()
        for name in ("audio-exit-tail-reason-000.csv",
                     "audio-exit-tail-wait-result-000.csv"):
            with self.subTest(name=name):
                extra=sd/name.replace("-000.csv","-001.csv")
                extra.write_bytes((sd/name).read_bytes())
                with self.assertRaises(ValueError):self.verify()
                extra.unlink()
        nested=sd/"nested-copy"
        nested.mkdir()
        for name in ("audio-exit-tail-reason-000.csv",
                     "audio-exit-tail-wait-result-000.csv",
                     "audio-exit-wait-descriptor-000.csv"):
            with self.subTest(nested=name):
                clone=nested/name.replace("-000.csv","-001.csv")
                clone.write_bytes((sd/name).read_bytes())
                with self.assertRaises(ValueError):self.verify()
                clone.unlink()
    def test_linked_capture_or_wrong_optical_dimensions_rejected(self):
        shot=self.two/"scene-optical-trace.png"
        content=shot.read_bytes()
        shot.write_bytes(content.replace((1280).to_bytes(4,"big"),
                                         (640).to_bytes(4,"big")))
        with self.assertRaises(ValueError):self.verify()
        shot.write_bytes(content)
        shot.unlink()
        target=self.temp/"external.png";target.write_bytes(content)
        shot.symlink_to(target)
        with self.assertRaises(ValueError):self.verify()
    def test_png_chunks_crc_and_terminator_required(self):
        shot=self.two/"scene-optical-trace.png"
        good=shot.read_bytes()
        self.assertEqual(len(self.verify()["captures"]),2)
        ihdr_crc_offset=8+4+4+13
        corrupt_crc=bytearray(good)
        corrupt_crc[ihdr_crc_offset]^=1
        no_idat=(b"\x89PNG\r\n\x1a\n"+good[8:33]+
                 png_chunk(b"IEND",b""))
        for invalid in (bytes(corrupt_crc),good[:-1],good+b"garbage",no_idat):
            with self.subTest(length=len(invalid)):
                shot.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    self.verify()
        shot.write_bytes(good)
        self.assertEqual(len(self.verify()["captures"]),2)

    def test_optional_old_probe_and_lease_are_not_exit_queue_measurements(self):
        sd=self.temp/f"vh-nexium-stage266-{RUN}-b"/a.RUN_GUEST_PATH
        age=sd/"audio-exit-probe-context-000.csv"
        age.write_bytes(b"scope,value\nsoftware_exit_probe_context_only,1\n")
        lease=sd/"audio-lease-reconciliation-000.csv"
        lease.write_bytes(b"scope,value\nsoftware_lease_only,1\n")
        report=self.verify()
        b=report["captures"][1]
        self.assertFalse(b["supplemental_telemetry_interpreted_as_exit_queue"])
        self.assertTrue(b["optional_original_telemetry"][age.name]["present"])
        self.assertFalse(b["optional_original_telemetry"][age.name]["parsed"])
        self.assertTrue(b["optional_original_telemetry"][lease.name]["present"])
        self.assertFalse(report["captures"][0]["optional_original_telemetry"][age.name]["present"])
        self.assertIsNone(report["captures"][0]["optional_original_telemetry"][age.name]["sha256"])
        (sd/"audio-exit-probe-context-001.csv").write_bytes(age.read_bytes())
        with self.assertRaises(ValueError):
            self.verify()
        (sd/"audio-exit-probe-context-001.csv").unlink()
        nested=sd/"archive"
        nested.mkdir()
        (nested/"audio-lease-reconciliation-001.csv").write_bytes(lease.read_bytes())
        with self.assertRaises(ValueError):
            self.verify()
    def test_hardlinked_evidence_does_not_prove_isolated_guest_sessions(self):
        # A second path to the same inode is not a second independent capture.
        left=self.temp/f"vh-nexium-stage266-{RUN}-a"/a.RUN_GUEST_PATH
        right=self.temp/f"vh-nexium-stage266-{RUN}-b"/a.RUN_GUEST_PATH
        original=right/"audio-exit-tail-reason-000.csv"
        bytes_b=original.read_bytes()
        original.unlink()
        original.hardlink_to(left/original.name)
        try:
            with self.assertRaises(ValueError):
                self.verify()
        finally:
            original.unlink()
            original.write_bytes(bytes_b)
        # The optical trace must also be unique to its purported run.
        image=self.two/"scene-optical-trace.png"
        bytes_img=image.read_bytes()
        image.unlink()
        image.hardlink_to(self.one/image.name)
        try:
            with self.assertRaises(ValueError):
                self.verify()
        finally:
            image.unlink()
            image.write_bytes(bytes_img)

    def test_no_unproven_guest_capture_can_be_backfilled(self):
        x=self.two/"guest-sd-root.txt"
        text=x.read_text()
        x.unlink()
        with self.assertRaises(ValueError):self.verify()
        x.write_text(text)
        with self.assertRaises(ValueError):self.verify(attempt=0)

if __name__=="__main__":
    unittest.main()
