#!/usr/bin/env python3
"""MAP02 v104 actual native C same-inode mutation around file and dir fsync."""
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
from test_map02_v103_inode_guard import fixture as old_fixture,encode
from tools.summarize_map02_v103_inode_guard import summarize as summarize_v103
from tools.summarize_map02_v104_content_guard import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=old_fixture()
    for name,value in zip(KINDS,(4,1,2)):
        rows.append(dict(kind=name,value=value,seq=len(rows)+1,cycle=0,frame=0))
    return rows

class NativeContentGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native GCC/Clang unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        directory=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        directory/"vh82_private_publish.h")
        lib=directory/"vh104.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(directory),"-o",str(lib)],
                       capture_output=True,check=True)
        cls.dll=ctypes.CDLL(str(lib))
        cls.dll.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh82_publish_private.restype=ctypes.c_int
        cls.dll.vh101_verify_private_commit.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh101_verify_private_commit.restype=ctypes.c_int
        cls.dll.vh104_test_mutate_bytes.argtypes=[ctypes.c_char_p,ctypes.c_int]
        cls.dll.vh104_test_mutate_bytes.restype=ctypes.c_int
        cls.dll.vh104_second_pass_reads.restype=ctypes.c_uint
        cls.dll.vh101_verified_commits.restype=ctypes.c_uint
        cls.dll.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.dll.vh99_private_state.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def publish(self,p,data):
        return self.dll.vh82_publish_private(os.fsencode(p),data,len(data))
    def verify(self,p,data):
        return self.dll.vh101_verify_private_commit(os.fsencode(p),data,len(data))
    def mutate_at(self,p,phase):
        return self.dll.vh104_test_mutate_bytes(os.fsencode(p),phase)
    def test_successful_publish_and_explicit_verify_both_double_read(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"journal"
            expected=b"ORIGINAL SIGNED PRIVATE GPU TRACE\n"
            before=self.dll.vh104_second_pass_reads()
            self.assertEqual(self.publish(p,expected),0)
            self.assertEqual(self.dll.vh104_second_pass_reads(),before+1)
            self.assertEqual(self.verify(p,expected),0)
            self.assertEqual(self.dll.vh104_second_pass_reads(),before+2)
            self.assertEqual(p.read_bytes(),expected)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            self.assertEqual(self.publish(p,b"CLASH"),-1)
    def test_mutation_after_initial_read_file_fsync_or_parent_fsync(self):
        expected=b"same inode, same SIZE must not prove unchanged CONTENT"
        for phase in (1,2,3):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as td:
                p=Path(td)/"private"
                fresh=Path(td)/"fresh"
                self.assertEqual(self.publish(p,expected),0)
                inode=p.stat().st_ino
                size=p.stat().st_size
                good=self.dll.vh104_second_pass_reads()
                good_commits=self.dll.vh101_verified_commits()
                self.assertEqual(self.mutate_at(p,phase),0)
                self.assertEqual(self.verify(p,expected),-1)
                self.assertEqual(p.stat().st_ino,inode)
                self.assertEqual(p.stat().st_size,size)
                self.assertNotEqual(p.read_bytes(),expected)
                self.assertEqual(self.dll.vh104_second_pass_reads(),good)
                self.assertEqual(self.dll.vh101_verified_commits(),good_commits)
                self.assertEqual(self.publish(p,expected),-1)
                # A true new observation must go to a distinct filename.
                self.assertEqual(self.publish(fresh,b"NEW UNMODIFIED"),0)
                self.assertEqual(fresh.read_bytes(),b"NEW UNMODIFIED")
                self.assertEqual(p.stat().st_ino,inode)
    def test_content_changes_without_inode_replacement_refused_and_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"trace"
            original=b"ABCD0123456789"
            self.assertEqual(self.publish(p,original),0)
            ino=p.stat().st_ino
            with p.open("r+b") as f:
                f.write(b"Z");f.flush();os.fsync(f.fileno())
            self.assertEqual(self.verify(p,original),-1)
            self.assertEqual(p.stat().st_ino,ino)
            self.assertEqual(p.stat().st_size,len(original))
            self.assertEqual(p.read_bytes(),b"ZBCD0123456789")
            self.assertEqual(self.publish(p,b"NEW"),-1)
    def test_unchanged_final_still_allowed_after_prior_refused_bad_expected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"original"
            data=b"never mutated"
            self.assertEqual(self.publish(p,data),0)
            before=self.dll.vh104_second_pass_reads()
            self.assertEqual(self.verify(p,b"different content"),-1)
            self.assertEqual(self.dll.vh104_second_pass_reads(),before)
            self.assertEqual(self.verify(p,data),0)
            self.assertEqual(self.dll.vh104_second_pass_reads(),before+1)
    def test_symlink_parent_and_stale_stage_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            parent=Path(td)/"dir";parent.mkdir()
            alias=Path(td)/"sym";alias.symlink_to(parent,target_is_directory=True)
            p=parent/"committed"
            data=b"stable"
            self.assertEqual(self.publish(p,data),0)
            self.assertEqual(self.verify(alias/"committed",data),-1)
            stage=Path(str(p)+".tmp");stage.write_bytes(b"FOREIGN")
            stage.chmod(0o600)
            self.assertEqual(self.verify(p,data),-1)
            self.assertEqual(stage.read_bytes(),b"FOREIGN")
    def test_previous_full_oracle_and_v104_strict_summary(self):
        proof=summarize(encode(fixture()))
        self.assertEqual(proof["post_fsync_full_file_reads_verified"],4)
        self.assertTrue(proof["same_inode_changed_bytes_refused"])
        self.assertEqual(proof["final_private_journal_events"],
                         proof["previous_checkpoint_events"]+3)
        self.assertFalse(proof["HD_replacement_approved"])
        self.assertEqual(summarize_v103(encode(fixture()))[
                         "successful_original_committed_file_verifications"],4)
    def test_refuse_misordered_duplicate_tampered_or_forged_suffix(self):
        for index in (-3,-2,-1):
            events=fixture();events[index]["value"]-=1
            with self.assertRaises(Refused):summarize(encode(events))
        events=fixture()
        events[-1]["kind"],events[-2]["kind"]=events[-2]["kind"],events[-1]["kind"]
        with self.assertRaises(Refused):summarize(encode(events))
        events=fixture()
        events.insert(-1,dict(events[-1]))
        for i,x in enumerate(events):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(events))
        events=fixture();events[-1]["frame"]=8
        with self.assertRaises(Refused):summarize(encode(events))
    def test_all_previous_pinned_gp0_checks_remain_required(self):
        s=(ROOT/"tools/apply_map02_v104_pcsx_rearmed.py").read_text()
        for token in ("apply_v103(root)","--vh104-double-readback-smoke",
                      "vh104_second_pass_reads()","VH104_CONTENT_PASS",
                      "same_inode_mutations_refused=True",
                      "HD_replacement_approved=False"):
            self.assertIn(token,s)

if __name__=="__main__":unittest.main()
