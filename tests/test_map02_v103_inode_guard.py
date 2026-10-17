#!/usr/bin/env python3
"""v103 native real C ABI: intermediate symlink and same-byte inode swap."""
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
from test_map02_v102_anchored_paths import fixture as v102_fixture,encode
from tools.summarize_map02_v102_anchored_paths import summarize as prior
from tools.summarize_map02_v103_inode_guard import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=v102_fixture()
    for kind,value in zip(KINDS,(12,4,1)):
        rows.append(dict(kind=kind,value=value,seq=len(rows)+1,cycle=0,frame=0))
    return rows

class NativeV103PathGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native compiler not available")
        cls.temp=tempfile.TemporaryDirectory()
        base=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        base/"vh82_private_publish.h")
        so=base/"libvh103.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(base),"-o",str(so)],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(so))
        cls.lib.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh82_publish_private.restype=ctypes.c_int
        cls.lib.vh101_verify_private_commit.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh101_verify_private_commit.restype=ctypes.c_int
        cls.lib.vh103_safe_parent_walks.restype=ctypes.c_uint
        cls.lib.vh103_test_replace_final.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
        cls.lib.vh103_test_replace_final.restype=ctypes.c_int
        cls.lib.vh100_test_fail_at.argtypes=[ctypes.c_int]
        cls.lib.vh101_test_fail_at.argtypes=[ctypes.c_int]
    @classmethod
    def tearDownClass(cls):
        cls.lib.vh100_test_fail_at(0)
        cls.lib.vh101_test_fail_at(0)
        cls.temp.cleanup()
    def setUp(self):
        self.lib.vh100_test_fail_at(0)
        self.lib.vh101_test_fail_at(0)
    def publish(self,path,data):
        return self.lib.vh82_publish_private(os.fsencode(path),data,len(data))
    def verify(self,path,data):
        return self.lib.vh101_verify_private_commit(os.fsencode(path),data,len(data))
    def test_real_ancestor_symlink_refused_before_stage_creation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            actual=root/"real";actual.mkdir()
            middle=actual/"nested";middle.mkdir()
            alias=root/"alias";alias.symlink_to(actual,target_is_directory=True)
            private=alias/"nested"/"journal"
            self.assertEqual(self.publish(private,b"SECRET"),-1)
            self.assertFalse((middle/"journal").exists())
            self.assertFalse((middle/"journal.tmp").exists())
            self.assertEqual(self.verify(private,b"SECRET"),-1)
    def test_second_level_symlink_refused_despite_matching_real_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            first=root/"first";first.mkdir()
            target=root/"target";target.mkdir()
            (first/"intermediate").symlink_to(target,target_is_directory=True)
            path=first/"intermediate"/"private"
            self.assertEqual(self.publish(path,b"DO NOT WRITE"),-1)
            self.assertFalse((target/"private").exists())
    def test_correct_multilevel_directory_succeeds_without_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            top=Path(td)/"a";top.mkdir()
            mid=top/"b";mid.mkdir()
            leaf=mid/"c";leaf.mkdir()
            path=leaf/"private"
            before=self.lib.vh103_safe_parent_walks()
            payload=b"ROOTED PATH SAFE"
            self.assertEqual(self.publish(path,payload),0)
            self.assertEqual(self.verify(path,payload),0)
            self.assertGreater(self.lib.vh103_safe_parent_walks(),before+4)
            self.assertEqual(path.read_bytes(),payload)
    def test_identical_bytes_but_different_inode_between_lookup_and_open(self):
        for phase in (1,2):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as td:
                root=Path(td)
                active=root/"committed"
                substitute=root/"replacement"
                backup=root/"original-backup"
                payload=b"same bytes do NOT prove same original inode\n"
                self.assertEqual(self.publish(active,payload),0)
                substitute.write_bytes(payload);substitute.chmod(0o600)
                first_inode=active.stat().st_ino
                replacement_inode=substitute.stat().st_ino
                self.assertNotEqual(first_inode,replacement_inode)
                before=self.lib.vh103_safe_parent_walks()
                self.assertEqual(self.lib.vh103_test_replace_final(
                    os.fsencode(active),os.fsencode(substitute),
                    os.fsencode(backup),phase),0)
                self.assertEqual(self.verify(active,payload),-1)
                self.assertEqual(backup.read_bytes(),payload)
                self.assertEqual(active.read_bytes(),payload)
                self.assertEqual(backup.stat().st_ino,first_inode)
                self.assertEqual(active.stat().st_ino,replacement_inode)
                self.assertGreater(self.lib.vh103_safe_parent_walks(),before)
                # No implicit recovery or deletion. A separate explicit
                # clean public target is the only allowed new publication.
                fresh=root/"new"
                self.assertEqual(self.publish(fresh,b"FRESH"),0)
                self.assertEqual(backup.read_bytes(),payload)
    def test_foreign_stage_and_leaf_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"journal";stage=Path(str(p)+".tmp")
            stage.write_bytes(b"PREVIOUS");stage.chmod(0o600)
            self.assertEqual(self.publish(p,b"NEW"),-1)
            self.assertEqual(stage.read_bytes(),b"PREVIOUS")
            stage.unlink()
            foreign=Path(td)/"foreign";foreign.write_bytes(b"KEEP")
            p.symlink_to(foreign)
            self.assertEqual(self.publish(p,b"NEW"),-1)
            self.assertEqual(foreign.read_bytes(),b"KEEP")
    def test_real_v102_predecessor_and_v103_suffix(self):
        p=summarize(encode(fixture()))
        self.assertEqual(p["real_parent_path_component_checks_at_least"],12)
        self.assertEqual(p["successful_original_committed_file_verifications"],4)
        self.assertTrue(p["intermediate_symlink_rejected_inside_native_emulator"])
        self.assertEqual(p["final_private_journal_events"],p["previous_checkpoint_events"]+3)
        self.assertFalse(p["HD_replacement_approved"])
        self.assertEqual(prior(encode(fixture()))["native_anchored_private_publishes"],2)
    def test_refuse_forged_values_and_clock(self):
        for index in (-3,-2,-1):
            x=fixture();x[index]["value"]-=1
            with self.assertRaises(Refused):summarize(encode(x))
        x=fixture();x[-1]["frame"]=9
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_duplicate_and_swapped_events(self):
        x=fixture();x[-1]["kind"],x[-2]["kind"]=x[-2]["kind"],x[-1]["kind"]
        with self.assertRaises(Refused):summarize(encode(x))
        x=fixture();x.insert(-1,dict(x[-1]))
        for n,item in enumerate(x):item["seq"]=n+1
        with self.assertRaises(Refused):summarize(encode(x))
    def test_pinned_source_preserves_predecessor_oracle_and_no_retail_claim(self):
        src=(ROOT/"tools/apply_map02_v103_pcsx_rearmed.py").read_text()
        for mark in ("apply_v102(root)","--vh103-inode-path-smoke",
                     "symlink(\".\",link_path)","vh103_safe_parent_walks()",
                     "VH103_PATH_GUARD_PASS",
                     "original_retail_MAP02_verified=False",
                     "HD_replacement_approved=False"):
            self.assertIn(mark,src)

if __name__=="__main__":unittest.main()
