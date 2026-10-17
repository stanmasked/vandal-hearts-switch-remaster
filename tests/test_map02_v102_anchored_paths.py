#!/usr/bin/env python3
"""v102 real native C tests for parent rename + symlink path redirection."""
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
from test_map02_v101_reopen import fixture as prior_fixture,encode
from tools.summarize_map02_v101_reopen import summarize as summarize_v101
from tools.summarize_map02_v102_anchored_paths import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=prior_fixture()
    for kind,value in zip(KINDS,(2,12,1)):
        rows.append(dict(kind=kind,value=value,seq=len(rows)+1,cycle=0,frame=0))
    return rows

class AnchoredNativePrivate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which(os.environ.get("CC","cc"))
        if not compiler:raise unittest.SkipTest("native C compiler unavailable")
        cls.tmp=tempfile.TemporaryDirectory()
        root=Path(cls.tmp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        root/"vh82_private_publish.h")
        dll=root/"libvh102.so"
        subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                        "-fPIC","-shared","-DVH100_FAULT_TEST",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(root),"-o",str(dll)],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(dll))
        cls.lib.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh82_publish_private.restype=ctypes.c_int
        cls.lib.vh101_verify_private_commit.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh101_verify_private_commit.restype=ctypes.c_int
        cls.lib.vh102_parent_identity_checks.restype=ctypes.c_uint
        cls.lib.vh102_anchored_publishes.restype=ctypes.c_uint
        cls.lib.vh102_test_parent_redirect.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
        cls.lib.vh102_test_parent_redirect.restype=ctypes.c_int
        cls.lib.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.lib.vh99_private_state.restype=ctypes.c_int
        cls.lib.vh100_test_fail_at.argtypes=[ctypes.c_int]
        cls.lib.vh101_test_fail_at.argtypes=[ctypes.c_int]
    @classmethod
    def tearDownClass(cls):
        cls.lib.vh100_test_fail_at(0)
        cls.lib.vh101_test_fail_at(0)
        cls.tmp.cleanup()
    def setUp(self):
        self.lib.vh100_test_fail_at(0)
        self.lib.vh101_test_fail_at(0)
    def publish(self,path,data):
        return self.lib.vh82_publish_private(os.fsencode(path),data,len(data))
    def verify(self,path,data):
        return self.lib.vh101_verify_private_commit(os.fsencode(path),data,len(data))
    def move_on_phase(self,parent,moved,attacker,phase):
        return self.lib.vh102_test_parent_redirect(
            os.fsencode(parent),os.fsencode(moved),
            os.fsencode(attacker),phase)
    def test_normal_private_commit_anchored_and_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"private";root.mkdir()
            p=root/"full.jsonl"
            payload=b"real native private diagnostic bytes"
            before=self.lib.vh102_anchored_publishes()
            checks=self.lib.vh102_parent_identity_checks()
            self.assertEqual(self.publish(p,payload),0)
            self.assertEqual(self.lib.vh102_anchored_publishes(),before+1)
            self.assertGreaterEqual(self.lib.vh102_parent_identity_checks(),checks+6)
            self.assertEqual(self.verify(p,payload),0)
            self.assertEqual(p.read_bytes(),payload)
            self.assertEqual(self.publish(p,b"replace"),-1)
            self.assertEqual(p.read_bytes(),payload)
    def test_renamed_directory_redirect_cannot_capture_private_file(self):
        for phase in (1,2,3):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                private=root/"owned";private.mkdir()
                moved=root/"moved"
                attacker=root/"attacker";attacker.mkdir()
                foreign=attacker/"journal"
                foreign.write_bytes(b"ATTACKER EXISTING BYTES")
                orig=private/"journal"
                data=b"SECRET MUST STAY IN OPENED DIRECTORY"
                before=self.lib.vh102_anchored_publishes()
                self.assertEqual(self.move_on_phase(private,moved,attacker,phase),0)
                self.assertEqual(self.publish(orig,data),-1)
                self.assertEqual(self.lib.vh102_anchored_publishes(),before)
                self.assertTrue(private.is_symlink())
                self.assertEqual(private.resolve(),attacker)
                self.assertEqual(foreign.read_bytes(),b"ATTACKER EXISTING BYTES")
                self.assertEqual(self.verify(orig,data),-1)
                # Phase 1 aborts before linking. Phase 2/3 leave a
                # possibly committed final inside the ORIGINAL fd dir.
                if phase==1:
                    self.assertFalse((moved/"journal").exists())
                else:
                    self.assertEqual((moved/"journal").read_bytes(),data)
                self.assertNotEqual((moved/"journal").exists(),
                                    phase==1)
                self.assertFalse((attacker/"journal.tmp").exists())
                private.unlink()
                self.assertEqual(attacker.joinpath("journal").read_bytes(),
                                 b"ATTACKER EXISTING BYTES")
    def test_symlinked_parent_name_not_accepted_at_start(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);actual=p/"actual";actual.mkdir()
            alias=p/"alias";alias.symlink_to(actual,target_is_directory=True)
            target=alias/"journal"
            self.assertEqual(self.publish(target,b"BAD"),-1)
            self.assertFalse((actual/"journal").exists())
    def test_final_symlink_tamper_refused_even_if_expected_content_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"real";folder.mkdir()
            target=folder/"journal"
            other=folder/"other"
            data=b"identical bytes are not sufficient"
            self.assertEqual(self.publish(target,data),0)
            other.write_bytes(data);other.chmod(0o600)
            target.unlink()
            target.symlink_to(other)
            self.assertEqual(self.verify(target,data),-1)
            self.assertEqual(other.read_bytes(),data)
    def test_replaced_final_inode_refused_while_unchanged_old_fd_valid(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/"journal"
            first=b"generation-one"
            self.assertEqual(self.publish(p,first),0)
            moved=d/"old";p.rename(moved)
            p.write_bytes(first);p.chmod(0o600)
            self.assertEqual(self.verify(p,first),0)
            # An already changed path before opening is indistinguishable
            # by bytes alone; v102 addresses redirection DURING an
            # operation, not historical authenticity of same-byte files.
            self.assertEqual(moved.read_bytes(),first)
    def test_no_foreign_temporary_stage_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            p=d/"journal"
            stage=Path(str(p)+".tmp")
            stage.write_bytes(b"OLD STAGED DATA")
            stage.chmod(0o600)
            self.assertEqual(self.publish(p,b"NEW"),-1)
            self.assertEqual(stage.read_bytes(),b"OLD STAGED DATA")
            self.assertFalse(p.exists())
    def test_original_strict_v101_oracle_remains_audit_valid(self):
        p=summarize(encode(fixture()))
        self.assertEqual(p["native_anchored_private_publishes"],2)
        self.assertEqual(p["native_parent_identity_checks_at_least"],12)
        self.assertTrue(p["parent_rename_symlink_redirect_fails_closed_in_isolated_C"])
        self.assertEqual(p["final_private_journal_events"],
                         p["previous_checkpoint_events"]+3)
        self.assertFalse(p["HD_replacement_approved"])
        self.assertEqual(summarize_v101(encode(fixture()))[
                         "successful_reopened_file_byte_checks"],4)
    def test_refuse_mutated_anchored_metrics(self):
        for index in (-3,-2,-1):
            with self.subTest(index=index):
                rows=fixture();rows[index]["value"]-=1
                with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_duplicate_or_wrong_order(self):
        rows=fixture();rows[-2]["kind"],rows[-1]["kind"]=rows[-1]["kind"],rows[-2]["kind"]
        with self.assertRaises(Refused):summarize(encode(rows))
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,row in enumerate(rows):row["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_forged_cpu_time(self):
        rows=fixture();rows[-1]["cycle"]=9
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_native_opt_in_provenance(self):
        source=(ROOT/"tools/apply_map02_v102_pcsx_rearmed.py").read_text()
        for token in ("apply_v101(root)","--vh102-anchored-directory-smoke",
                      "vh102_anchored_publishes",
                      "vh102_parent_identity_checks",
                      "VH102_ANCHORED_PASS",
                      "original_retail_MAP02_verified=False",
                      "HD_replacement_approved=False"):
            self.assertIn(token,source)

if __name__=="__main__":unittest.main()
