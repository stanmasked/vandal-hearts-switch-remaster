#!/usr/bin/env python3
"""v81 C exporter tests; source-authored events are NOT retail capture."""
import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"tools"
class V81Jsonl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc: raise unittest.SkipTest("C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        path=Path(cls.temp.name)/"libvh81.so"
        for version in (80,81):
            shutil.copyfile(ROOT/f"map02_v{version}_{'native_timeline' if version==80 else 'event_jsonl'}.h",
                            Path(cls.temp.name)/f"vh{version}_{'native_timeline' if version==80 else 'event_jsonl'}.h")
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-fPIC","-shared",
                        str(ROOT/"map02_v80_native_timeline.c"),
                        str(ROOT/"map02_v81_event_jsonl.c"),"-I",cls.temp.name,"-o",str(path)],
                       check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(path))
        cls.lib.vh80_record.argtypes=[ctypes.c_uint32]*4
        cls.lib.vh81_format_jsonl.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        cls.lib.vh81_format_jsonl.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def setUp(self):
        self.lib.vh80_reset()
    def record(self,kind,value,cycle,frame):
        self.lib.vh80_record(kind,value,cycle,frame)
    def export(self,n=2048):
        b=ctypes.create_string_buffer(n)
        ret=self.lib.vh81_format_jsonl(b,n)
        return ret,b.value
    def valid(self):
        self.record(1,0,100,7)
        self.record(2,0xe1000020,110,0)
        self.record(3,0x1234,120,0)
        self.record(1,0,200,8)
    def test_expected_emulator_event_types(self):
        self.valid()
        count,payload=self.export()
        self.assertEqual(count,len(payload))
        events=[json.loads(s) for s in payload.decode().splitlines()]
        self.assertEqual([e["kind"] for e in events],
                         ["vblank","gp1_mmio","gpu_dma2_start","vblank"])
        self.assertEqual([e["seq"] for e in events],[1,2,3,4])
        self.assertEqual(events[2]["value"],0x1234)
    def test_no_events_refused(self):
        self.assertEqual(self.export()[0],-1)
    def test_only_one_edge_refused(self):
        self.record(1,0,100,7)
        self.assertEqual(self.export()[0],-1)
    def test_small_buffer_refused(self):
        self.valid()
        self.assertEqual(self.export(32)[0],-1)
    def test_overflow_refused(self):
        self.valid()
        for i in range(4093):self.record(1,0,i,7)
        self.record(1,0,0,0)
        self.assertEqual(self.export(1000000)[0],-1)
    def test_invalid_kind_refused(self):
        self.valid()
        self.record(999,0,0,0)
        self.assertEqual(self.export()[0],-1)
    def test_deterministic_serialization(self):
        self.valid()
        self.assertEqual(self.export(),self.export())

if __name__=="__main__":unittest.main()
