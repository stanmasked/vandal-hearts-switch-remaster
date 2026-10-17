#!/usr/bin/env python3
"""v98: live pinned native POSIX private no-clobber failure/retry regression."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v97_reset_scrub import fixture as previous_fixture,encode
from tools.summarize_map02_v97_reset_scrub import summarize as prior
from tools.summarize_map02_v98_recovery import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    events=previous_fixture()
    for kind in KINDS:
        events.append(dict(kind=kind,value=1,seq=len(events)+1,cycle=0,frame=0))
    return events

class NativePrivateRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        target=Path(cls.temp.name)/"libvh98.so"
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        Path(cls.temp.name)/"vh82_private_publish.h")
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",cls.temp.name,"-o",str(target)],
                       check=True,capture_output=True)
        cls.dll=ctypes.CDLL(str(target))
        cls.dll.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh82_publish_private.restype=ctypes.c_int
        cls.dll.vh98_publish_recovery.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh98_publish_recovery.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def base(self,path,payload):
        return self.dll.vh82_publish_private(os.fsencode(path),payload,len(payload))
    def recover(self,old,new,payload):
        return self.dll.vh98_publish_recovery(
            os.fsencode(old),os.fsencode(new),payload,len(payload))
    def test_old_generation_immutable_and_distinct_recovery_only(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"private.epoch1.jsonl"
            new=Path(td)/"private.epoch2.jsonl"
            original=b'{"generation":1,"scope":"private"}\n'
            updated=b'{"generation":2,"scope":"private"}\n'
            self.assertEqual(self.base(old,original),0)
            old_stat=old.stat()
            self.assertEqual(self.base(old,updated),-1)
            self.assertEqual(self.recover(old,old,updated),-1)
            self.assertFalse(new.exists())
            self.assertEqual(self.recover(old,new,updated),0)
            self.assertEqual(self.recover(old,new,updated),-1)
            self.assertEqual(self.base(new,original),-1)
            self.assertEqual(old.read_bytes(),original)
            self.assertEqual(new.read_bytes(),updated)
            self.assertEqual(old.stat().st_ino,old_stat.st_ino)
            self.assertEqual(old.stat().st_mode & 0o777,0o600)
            self.assertEqual(new.stat().st_mode & 0o777,0o600)
            self.assertFalse(Path(str(new)+".tmp").exists())
    def test_fail_at_existing_temp_then_recover_using_new_unique_name(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"private.old"
            first=Path(td)/"private.retryA"
            second=Path(td)/"private.retryB"
            original=b"IMMUTABLE OLD\n"
            update=b"RECOVERED\n"
            self.assertEqual(self.base(old,original),0)
            stale=Path(str(first)+".tmp");stale.write_bytes(b"DONT REMOVE OTHER FILE")
            self.assertEqual(self.recover(old,first,update),-1)
            self.assertEqual(stale.read_bytes(),b"DONT REMOVE OTHER FILE")
            self.assertFalse(first.exists())
            self.assertEqual(self.recover(old,second,update),0)
            self.assertEqual(old.read_bytes(),original)
            self.assertEqual(second.read_bytes(),update)
            self.assertEqual(stale.read_bytes(),b"DONT REMOVE OTHER FILE")
    def test_reject_symlink_previous_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"original"
            link=Path(td)/"alias"
            new=Path(td)/"next"
            self.assertEqual(self.base(old,b"good"),0)
            link.symlink_to(old)
            for candidate in (link,Path(td)/"missing"):
                self.assertEqual(self.recover(candidate,new,b"other"),-1)
            self.assertEqual(self.recover(old,old,b"other"),-1)
            self.assertEqual(self.recover(old,Path(td)/"../next",b"other"),-1)
            self.assertEqual(self.recover(old,Path("relative"),b"other"),-1)
            self.assertFalse(new.exists())
            self.assertEqual(old.read_bytes(),b"good")
    def test_refuse_previous_file_with_weak_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"old"
            new=Path(td)/"new"
            old.write_bytes(b"unprotected")
            old.chmod(0o644)
            self.assertEqual(self.recover(old,new,b"other"),-1)
            self.assertFalse(new.exists())
            self.assertEqual(old.read_bytes(),b"unprotected")
    def test_recovery_after_prior_name_already_exists(self):
        with tempfile.TemporaryDirectory() as td:
            first=Path(td)/"stage1"
            second=Path(td)/"stage2"
            third=Path(td)/"stage3"
            self.assertEqual(self.base(first,b"one\n"),0)
            self.assertEqual(self.recover(first,second,b"two\n"),0)
            self.assertEqual(self.recover(first,third,b"three\n"),0)
            self.assertEqual(self.recover(second,third,b"other"),-1)
            self.assertEqual([p.read_bytes() for p in (first,second,third)],
                             [b"one\n",b"two\n",b"three\n"])

class PrivateRecoveryProof(unittest.TestCase):
    def test_complete_new_aggregate_and_previous_v97(self):
        r=summarize(encode(fixture()))
        self.assertEqual(r["final_private_journal_events"],
                         r["previous_checkpoint_events"]+3)
        self.assertTrue(r["preexisting_private_file_rejected"])
        self.assertTrue(r["new_private_filename_published_exclusively"])
        self.assertFalse(r["HD_replacement_approved"])
        self.assertEqual(prior(encode(fixture()))["initial_identical_in_memory_replays"],2)
    def test_reject_bogus_old_refusal(self):
        rows=fixture();rows[-3]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_recovery_failure(self):
        rows=fixture();rows[-2]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_unblocked_duplicate(self):
        rows=fixture();rows[-1]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_aggregate(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,item in enumerate(rows):item["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_bad_order(self):
        rows=fixture()
        rows[-3]["kind"],rows[-2]["kind"]=rows[-2]["kind"],rows[-3]["kind"]
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_fabricated_frame_cycle(self):
        rows=fixture();rows[-3]["frame"]=10
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_verify_original_pinned_GPU_oracle_not_reset(self):
        src=(ROOT/"tools/apply_map02_v98_pcsx_rearmed.py").read_text()
        for token in ("apply_v97(root)","--vh98-private-recovery-smoke",
                      "vh98_publish_recovery(oldfile,nextfile",
                      "vh82_publish_private(oldfile",
                      "VH98_RECOVERY_PASS",
                      "original_final_v82_private_destination_untouched=True",
                      "retail_MAP02_verified=False",
                      "HD_replacement_approved=False"):
            self.assertIn(token,src)

if __name__=="__main__":unittest.main()
