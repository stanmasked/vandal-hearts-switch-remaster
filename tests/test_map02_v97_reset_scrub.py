#!/usr/bin/env python3
"""v97 actual native C journal reset scrubbing + private memory reuse refusal."""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v96_boundary import fixture as v96_fixture,NativeEvent,encode
from tools.summarize_map02_v96_boundary import summarize as previous
from tools.summarize_map02_v97_reset_scrub import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=v96_fixture()
    for name,value in zip(KINDS,(2,524288,2)):
        rows.append(dict(kind=name,value=value,seq=len(rows)+1,cycle=0,frame=0))
    return rows

class NativeScrub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        base=Path(cls.temp.name);tools=ROOT/"tools"
        for n,part in ((80,"native_timeline"),(81,"event_jsonl")):
            shutil.copyfile(tools/f"map02_v{n}_{part}.h",
                            base/f"vh{n}_{part}.h")
        binary=base/"libvh97.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-shared","-fPIC",
                        str(tools/"map02_v80_native_timeline.c"),
                        str(tools/"map02_v81_event_jsonl.c"),
                        "-I",str(base),"-o",str(binary)],
                       check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(binary))
        cls.lib.vh80_record.argtypes=[ctypes.c_uint32]*4
        cls.lib.vh80_events.restype=ctypes.POINTER(NativeEvent)
        for name in ("vh80_count","vh80_dropped","vh94_merge_runs",
                     "vh97_reset_epoch","vh97_buffers_erased"):
            getattr(cls.lib,name).restype=ctypes.c_uint
        cls.lib.vh94_snapshot_check.restype=ctypes.c_int
        cls.lib.vh81_format_jsonl.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        cls.lib.vh81_format_jsonl.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.lib.vh80_reset()
        self.add_seed(17)
    def add_seed(self,seed):
        self.lib.vh80_record(1,seed,100,7)
        self.lib.vh80_record(8,seed+1,0,0)
        self.lib.vh80_record(1,seed+2,200,8)
    def export(self,out):
        return self.lib.vh81_format_jsonl(out,len(out))
    def test_epoch_reset_erases_source_lanes_and_merged_cache(self):
        out=ctypes.create_string_buffer(524288)
        previous_bytes=self.export(out)
        self.assertGreater(previous_bytes,0)
        old=out.raw[:previous_bytes]
        view=self.lib.vh80_events()
        self.assertEqual(view[0].sequence,1)
        epoch=self.lib.vh97_reset_epoch()
        self.lib.vh80_reset()
        self.assertEqual(self.lib.vh97_reset_epoch(),epoch+1)
        self.assertEqual(self.lib.vh80_count(),0)
        self.assertEqual(self.lib.vh80_dropped(),0)
        self.assertEqual(self.lib.vh97_buffers_erased(),1)
        self.assertEqual(view[0].sequence,0)
        self.assertEqual(view[0].value,0)
        self.assertEqual(self.lib.vh94_snapshot_check(),-1)
        ctypes.memset(out,0xa5,len(out))
        self.assertEqual(self.export(out),-1)
        self.assertEqual(out.raw,b"\0"*len(out))
        self.add_seed(90)
        newsize=self.export(out)
        self.assertGreater(newsize,0)
        self.assertNotEqual(out.raw[:newsize],old)
        self.assertIn(b'"value":90',out.raw[:newsize])
        self.assertNotIn(b'"value":17',out.raw[:newsize])
        self.assertEqual(out.raw[newsize:],b"\0"*(len(out)-newsize))
        self.assertEqual(self.lib.vh80_events()[0].sequence,1)
    def test_reuse_old_long_serialization_never_leaks_on_short_export(self):
        out=ctypes.create_string_buffer(524288)
        for n in range(100): self.lib.vh80_record(4,n,0,0)
        longer=self.export(out)
        self.assertGreater(longer,1000)
        old_raw=out.raw[:longer]
        self.lib.vh80_reset()
        self.assertEqual(self.lib.vh97_buffers_erased(),1)
        self.add_seed(300)
        shorter=self.export(out)
        self.assertLess(shorter,longer)
        self.assertNotIn(b'"kind":"gp0_unai_handled"',out.raw[:shorter])
        self.assertEqual(out.raw[shorter:],b"\0"*(len(out)-shorter))
        self.assertNotEqual(out.raw[:shorter],old_raw[:shorter])
        self.assertEqual(self.lib.vh94_snapshot_check(),0)
    def test_overflow_then_reset_clears_poisoned_generation(self):
        out=ctypes.create_string_buffer(524288)
        self.assertGreater(self.export(out),0)
        self.lib.vh80_record(999,0,0,0)
        self.assertEqual(self.lib.vh80_dropped(),1)
        ctypes.memset(out,0xbb,len(out))
        self.assertEqual(self.export(out),-1)
        self.assertEqual(out.raw,b"\0"*len(out))
        old_epoch=self.lib.vh97_reset_epoch()
        self.lib.vh80_reset()
        self.assertEqual(self.lib.vh97_reset_epoch(),old_epoch+1)
        self.assertEqual(self.lib.vh97_buffers_erased(),1)
        self.assertEqual(self.lib.vh80_dropped(),0)
        self.add_seed(501)
        self.assertGreater(self.export(out),0)
        self.assertEqual(self.lib.vh80_events()[0].sequence,1)
    def test_three_fresh_reset_generations_do_not_mix(self):
        out=ctypes.create_string_buffer(524288)
        past=[]
        for k in range(3):
            self.lib.vh80_reset()
            self.assertEqual(self.lib.vh97_buffers_erased(),1)
            self.assertEqual(self.lib.vh94_snapshot_check(),-1)
            self.add_seed(700+k*10)
            n=self.export(out)
            self.assertGreater(n,0)
            result=out.raw[:n]
            self.assertTrue(all(previous!=result for previous in past))
            self.assertEqual(self.lib.vh80_events()[0].sequence,1)
            self.assertEqual(self.lib.vh80_count(),3)
            past.append(result)

class V97PrivateAudit(unittest.TestCase):
    def test_epoch_and_stable_serializer_proof(self):
        proof=summarize(encode(fixture()))
        self.assertEqual(proof["observer_epoch"],2)
        self.assertEqual(proof["verified_scrubbed_output_buffer_bytes"],524288)
        self.assertEqual(proof["initial_identical_in_memory_replays"],2)
        self.assertEqual(proof["final_private_journal_events"],
                         proof["previous_checkpoint_events"]+3)
        self.assertFalse(proof["HD_replacement_approved"])
    def test_v96_checkpoint_still_standalone(self):
        self.assertGreater(previous(encode(fixture()))["private_events"],4096)
    def test_refuse_zero_or_forged_epoch(self):
        rows=fixture();rows[-3]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_short_private_buffer_scrub(self):
        rows=fixture();rows[-2]["value"]=17
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_lost_replay(self):
        rows=fixture();rows[-1]["value"]=1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_bad_order_or_duplicate(self):
        rows=fixture();rows[-3]["kind"],rows[-2]["kind"]=rows[-2]["kind"],rows[-3]["kind"]
        with self.assertRaises(Refused):summarize(encode(rows))
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for n,r in enumerate(rows):r["seq"]=n+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_fake_emulator_timestamps(self):
        rows=fixture();rows[-1]["frame"]=45
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_source_guards_against_retail_claim_and_reset_of_live_trace(self):
        s=(ROOT/"tools/apply_map02_v97_pcsx_rearmed.py").read_text()
        for term in ("apply_v96(root)","--vh97-reset-scrub-smoke",
                     "vh97_reset_epoch()","memset(serialized,0xa5",
                     "memcmp(replayed,serialized",
                     "VH97_REUSE_PASS",
                     "v97_live_emulator_does_not_clear_predecessor_provenance=True",
                     "HD_replacement_approved=False"):
            self.assertIn(term,s)

if __name__=="__main__":unittest.main()
