#!/usr/bin/env python3
"""POSIX private publisher and synthetic v82 trace validation regressions."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.verify_map02_v82_native_trace import validate,Refused

def fixture():
    entries=[
        ("gp1_mmio",1,0xe1000020,90,0),
        ("vblank",2,0,100,7),
        ("gp1_mmio",3,0x01000000,110,0),
        ("vblank",4,0,200,8),
        ("vblank",5,0,300,9),
        ("vblank",6,0,400,10),
    ]
    return b"".join((json.dumps(dict(kind=k,seq=s,value=v,cycle=c,frame=f),
                                separators=(",",":"))+"\n").encode()
                    for k,s,v,c,f in entries)

class V82Publish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        so=Path(cls.temp.name)/"v82.so"
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        Path(cls.temp.name)/"vh82_private_publish.h")
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),"-I",cls.temp.name,"-o",str(so)],
                       check=True,capture_output=True)
        cls.dll=ctypes.CDLL(str(so))
        cls.dll.vh82_publish_private.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh82_publish_private.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_exclusive_private_publish_and_identical_readback(self):
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/"trace.jsonl"
            raw=fixture()
            self.assertEqual(self.dll.vh82_publish_private(os.fsencode(dst),raw,len(raw)),0)
            self.assertEqual(dst.read_bytes(),raw)
            self.assertEqual(dst.stat().st_mode&0o777,0o600)
            self.assertFalse(Path(str(dst)+".tmp").exists())
            self.assertEqual(self.dll.vh82_publish_private(os.fsencode(dst),raw,len(raw)),-1)
            self.assertEqual(dst.read_bytes(),raw)
    def test_refuse_preexisting_temporary_file(self):
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/"trace.jsonl"
            existing=Path(str(dst)+".tmp")
            existing.write_bytes(b"DO NOT TOUCH")
            raw=fixture()
            self.assertEqual(self.dll.vh82_publish_private(os.fsencode(dst),raw,len(raw)),-1)
            self.assertEqual(existing.read_bytes(),b"DO NOT TOUCH")
            self.assertFalse(dst.exists())
    def test_refuse_symlink_tmp(self):
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/"trace.jsonl"
            other=Path(td)/"private";other.write_bytes(b"SAFE")
            Path(str(dst)+".tmp").symlink_to(other)
            raw=fixture()
            self.assertEqual(self.dll.vh82_publish_private(os.fsencode(dst),raw,len(raw)),-1)
            self.assertEqual(other.read_bytes(),b"SAFE")
    def test_refuse_invalid_paths_and_empty(self):
        raw=fixture()
        self.assertEqual(self.dll.vh82_publish_private(b"relative.jsonl",raw,len(raw)),-1)
        self.assertEqual(self.dll.vh82_publish_private(b"/tmp/../tmp/trace.jsonl",raw,len(raw)),-1)
        self.assertEqual(self.dll.vh82_publish_private(b"/tmp/trace.jsonl",raw,0),-1)

class V82Trace(unittest.TestCase):
    def test_expected_events(self):
        r=validate(fixture())
        self.assertEqual((r["events"],r["vblank_edges"],r["gp1_mmio"]),(6,4,2))
        self.assertFalse(r["HD_replacement_approved"])
    def test_wrong_vblank_frame_refused(self):
        bad=fixture().replace(b'"frame":9',b'"frame":12')
        with self.assertRaises(Refused):validate(bad)
    def test_missing_event_refused(self):
        lines=fixture().splitlines(keepends=True)
        with self.assertRaises(Refused):validate(b"".join(lines[:2]+lines[3:]))
    def test_dma_does_not_turn_into_gp0(self):
        raw=fixture().replace(b'"kind":"gp1_mmio"',b'"kind":"gpu_dma2_start"',1)
        with self.assertRaises(Refused):validate(raw)
    def test_mutated_gpu_frame_claim_refused(self):
        raw=fixture().replace(b'"cycle":110,"frame":0',b'"cycle":110,"frame":8')
        with self.assertRaises(Refused):validate(raw)
    def test_reject_truncated(self):
        with self.assertRaises(Refused):validate(fixture()[:-1])
    def test_patch_only_under_opt_in_and_after_oracle(self):
        s=(ROOT/"tools/apply_map02_v82_pcsx_rearmed.py").read_text()
        self.assertIn("vh82_export_smoke",s)
        self.assertIn("VH78_VBLANK_VRAM_PASS",s)
        self.assertIn("vh82_publish_private(dest",s)
        for token in ("VH82_CAPTURE_REFUSED", "VH82_PRIVATE_PUBLISH_REFUSED",
                      "VH82_PRIVATE_EXPORT_PASS vblanks=%u gp1_mmio=%u entries=%u bytes=%d drops=0"):
            self.assertIn(token + r"\n", s)
            self.assertNotIn(token + "\n", s)
        self.assertIn("HD_replacement_approved=False",s)

if __name__=="__main__":unittest.main()
