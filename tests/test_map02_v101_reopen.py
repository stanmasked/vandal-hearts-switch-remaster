#!/usr/bin/env python3
"""v101 real POSIX committed private reopen and fsync fail-closed tests."""
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
from test_map02_v100_directory_sync import fixture as previous_fixture,encode
from tools.summarize_map02_v100_directory_sync import summarize as summarize_prior
from tools.summarize_map02_v101_reopen import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    events=previous_fixture()
    for kind,value in zip(KINDS,(4,4,1)):
        events.append(dict(kind=kind,value=value,seq=len(events)+1,
                           cycle=0,frame=0))
    return events

class NativePrivateReopen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        folder=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        folder/"vh82_private_publish.h")
        so=folder/"libvh101.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(folder),"-o",str(so)],
                       check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(so))
        cls.lib.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh82_publish_private.restype=ctypes.c_int
        cls.lib.vh101_verify_private_commit.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh101_verify_private_commit.restype=ctypes.c_int
        cls.lib.vh101_verified_commits.restype=ctypes.c_uint
        cls.lib.vh101_reopened_directory_syncs.restype=ctypes.c_uint
        cls.lib.vh101_test_fail_at.argtypes=[ctypes.c_int]
        cls.lib.vh100_test_fail_at.argtypes=[ctypes.c_int]
        cls.lib.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.lib.vh99_private_state.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):
        cls.lib.vh101_test_fail_at(0)
        cls.lib.vh100_test_fail_at(0)
        cls.temp.cleanup()
    def setUp(self):
        self.lib.vh101_test_fail_at(0)
        self.lib.vh100_test_fail_at(0)
    def publish(self,p,data):
        return self.lib.vh82_publish_private(os.fsencode(p),data,len(data))
    def verify(self,p,data):
        return self.lib.vh101_verify_private_commit(os.fsencode(p),data,len(data))
    def state(self,p):
        return self.lib.vh99_private_state(os.fsencode(p))
    def test_one_publish_verified_then_reopened_second_time(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"committed"
            payload=b"private evidence complete\n"
            before=self.lib.vh101_verified_commits()
            sync_before=self.lib.vh101_reopened_directory_syncs()
            self.assertEqual(self.publish(p,payload),0)
            self.assertEqual(self.state(p),1)
            self.assertEqual(self.lib.vh101_verified_commits(),before+1)
            self.assertEqual(self.lib.vh101_reopened_directory_syncs(),sync_before+1)
            self.assertEqual(self.verify(p,payload),0)
            self.assertEqual(self.lib.vh101_verified_commits(),before+2)
            self.assertEqual(self.lib.vh101_reopened_directory_syncs(),sync_before+2)
            self.assertEqual(p.read_bytes(),payload)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            self.assertFalse(Path(str(p)+".tmp").exists())
            self.assertEqual(self.publish(p,b"overwrite"),-1)
            self.assertEqual(p.read_bytes(),payload)
    def test_wrong_content_and_modified_inode_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"final"
            good=b"private PASS\n"
            self.assertEqual(self.publish(p,good),0)
            count=self.lib.vh101_verified_commits()
            self.assertEqual(self.verify(p,b"wrong content\n"),-1)
            self.assertEqual(self.verify(p,b"short"),-1)
            self.assertEqual(self.lib.vh101_verified_commits(),count)
            p.write_bytes(b"MODIFIED!!!!\n")
            self.assertEqual(self.verify(p,good),-1)
            self.assertEqual(p.read_bytes(),b"MODIFIED!!!!\n")
    def test_leftover_stage_never_certifies_completed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"final"
            payload=b"committed before leftover"
            self.assertEqual(self.publish(p,payload),0)
            stage=Path(str(p)+".tmp")
            stage.write_bytes(b"foreign incomplete")
            stage.chmod(0o600)
            self.assertEqual(self.state(p),3)
            self.assertEqual(self.verify(p,payload),-1)
            self.assertEqual(stage.read_bytes(),b"foreign incomplete")
            stage.unlink()
            self.assertEqual(self.verify(p,payload),0)
    def test_invalid_symlink_and_insecure_file_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"saved"
            alias=Path(td)/"link"
            data=b"owned"
            self.assertEqual(self.publish(p,data),0)
            alias.symlink_to(p)
            self.assertEqual(self.verify(alias,data),-1)
            p.chmod(0o644)
            self.assertEqual(self.verify(p,data),-1)
            p.chmod(0o600)
            self.assertEqual(self.verify(p,data),0)
    def test_new_parent_directory_must_be_reopenable_without_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            physical=Path(td)/"storage"
            physical.mkdir()
            alias=Path(td)/"linked_parent"
            alias.symlink_to(physical,target_is_directory=True)
            raw=physical/"one"
            data=b"bytes"
            self.assertEqual(self.publish(raw,data),0)
            self.assertEqual(self.verify(alias/"one",data),-1)
            self.assertEqual(raw.read_bytes(),data)
    def test_fault_injected_existing_file_or_directory_sync(self):
        for phase in (1,2,3):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as td:
                path=Path(td)/"committed"
                second=Path(td)/"new"
                data=b"completed-but-verification-uncertain\n"
                self.lib.vh101_test_fail_at(phase)
                before=self.lib.vh101_verified_commits()
                self.assertEqual(self.publish(path,data),-1)
                self.assertEqual(path.read_bytes(),data)
                self.assertEqual(self.state(path),1)
                self.assertEqual(self.lib.vh101_verified_commits(),before)
                self.assertEqual(self.publish(path,b"overwrite"),-1)
                self.assertEqual(path.read_bytes(),data)
                self.lib.vh101_test_fail_at(0)
                self.assertEqual(self.publish(second,b"NEXT"),0)
                self.assertEqual(path.read_bytes(),data)
                self.assertEqual(second.read_bytes(),b"NEXT")
    def test_reopened_existing_private_file_failure_does_not_delete(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"one"
            data=b"retained"
            self.assertEqual(self.publish(p,data),0)
            self.lib.vh101_test_fail_at(3)
            self.assertEqual(self.verify(p,data),-1)
            self.assertEqual(p.read_bytes(),data)
            self.assertEqual(self.state(p),1)
            self.lib.vh101_test_fail_at(0)
            self.assertEqual(self.verify(p,data),0)

class V101Audit(unittest.TestCase):
    def test_valid_and_v100_independently_still_valid(self):
        proof=summarize(encode(fixture()))
        self.assertEqual(proof["successful_reopened_file_byte_checks"],4)
        self.assertEqual(proof["successful_reopened_parent_directory_fsyncs"],4)
        self.assertEqual(proof["final_private_journal_events"],
                         proof["previous_checkpoint_events"]+3)
        self.assertFalse(proof["power_loss_physically_tested"])
        self.assertFalse(proof["HD_replacement_approved"])
        self.assertEqual(summarize_prior(encode(fixture()))[
                         "successful_post_hardlink_parent_directory_syncs"],2)
    def test_refuse_missing_reopen(self):
        events=fixture();events[-3]["value"]=3
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_missing_second_directory_sync(self):
        events=fixture();events[-2]["value"]=3
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_accepted_wrong_bytes(self):
        events=fixture();events[-1]["value"]=0
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_duplicate_or_swapped_event(self):
        events=fixture();events[-2]["kind"],events[-1]["kind"]=events[-1]["kind"],events[-2]["kind"]
        with self.assertRaises(Refused):summarize(encode(events))
        events=fixture();events.insert(-1,dict(events[-1]))
        for i,e in enumerate(events):e["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_forged_cpu_time(self):
        events=fixture();events[-1]["frame"]=2
        with self.assertRaises(Refused):summarize(encode(events))
    def test_pinned_opt_in_and_hardware_not_claimed(self):
        s=(ROOT/"tools/apply_map02_v101_pcsx_rearmed.py").read_text()
        for name in ("apply_v100(root)","--vh101-reopened-verify-smoke",
                     "vh101_verify_private_commit","VH101_REOPEN_PASS",
                     "never_auto_reuse_ambiguous_filename=True",
                     "original_retail_MAP02_verified=False",
                     "HD_replacement_approved=False"):
            self.assertIn(name,s)

if __name__=="__main__":unittest.main()
