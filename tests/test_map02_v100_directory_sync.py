#!/usr/bin/env python3
"""v100 actual POSIX directory fsync and deterministic fault-phase ABI tests."""
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
from test_map02_v99_interrupted import fixture as previous_fixture,encode
from tools.summarize_map02_v99_interrupted import summarize as prior
from tools.summarize_map02_v100_directory_sync import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    out=previous_fixture()
    for kind,val in zip(KINDS,(2,2,1)):
        out.append(dict(kind=kind,value=val,seq=len(out)+1,cycle=0,frame=0))
    return out

class DirectorySyncABI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        folder=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        folder/"vh82_private_publish.h")
        library=folder/"libvh100.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-fPIC","-shared",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(folder),"-o",str(library)],
                       check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh82_publish_private.restype=ctypes.c_int
        cls.lib.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.lib.vh99_private_state.restype=ctypes.c_int
        cls.lib.vh100_test_fail_at.argtypes=[ctypes.c_int]
        cls.lib.vh100_directory_syncs.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):
        cls.lib.vh100_test_fail_at(0)
        cls.temp.cleanup()
    def setUp(self):
        self.lib.vh100_test_fail_at(0)
    def publish(self,path,payload=b"native private dirsync bytes\n"):
        return self.lib.vh82_publish_private(os.fsencode(path),payload,len(payload))
    def state(self,path):
        return self.lib.vh99_private_state(os.fsencode(path))
    def test_success_uses_two_real_parent_fsyncs(self):
        with tempfile.TemporaryDirectory() as td:
            first=Path(td)/"generation1"
            second=Path(td)/"generation2"
            initial=self.lib.vh100_directory_syncs()
            self.assertEqual(self.publish(first),0)
            self.assertEqual(self.lib.vh100_directory_syncs(),initial+2)
            self.assertEqual(self.publish(second,b"NEW DATA"),0)
            self.assertEqual(self.lib.vh100_directory_syncs(),initial+4)
            self.assertEqual(self.publish(first,b"WRONG"),-1)
            self.assertEqual(self.lib.vh100_directory_syncs(),initial+4)
            self.assertEqual(self.state(first),1)
            self.assertEqual(self.state(second),1)
            self.assertEqual(first.read_bytes(),b"native private dirsync bytes\n")
            self.assertEqual(second.read_bytes(),b"NEW DATA")
            self.assertFalse(Path(str(first)+".tmp").exists())
            self.assertFalse(Path(str(second)+".tmp").exists())
            self.assertEqual(first.stat().st_mode & 0o777,0o600)
    def test_injected_failure_after_final_link_not_silently_successful(self):
        for phase,synced,state in ((1,0,3),(2,1,3),(3,1,1)):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as td:
                target=Path(td)/"failure"
                next_path=Path(td)/"fresh"
                before=self.lib.vh100_directory_syncs()
                self.lib.vh100_test_fail_at(phase)
                self.assertEqual(self.publish(target,b"PARTIAL COMMIT\n"),-1)
                self.assertEqual(self.lib.vh100_directory_syncs(),before+synced)
                self.assertEqual(self.state(target),state)
                self.assertEqual(target.read_bytes(),b"PARTIAL COMMIT\n")
                self.assertEqual(self.publish(target,b"NO REPLACE"),-1)
                self.assertEqual(target.read_bytes(),b"PARTIAL COMMIT\n")
                self.assertEqual(self.state(target),state)
                self.lib.vh100_test_fail_at(0)
                self.assertEqual(self.publish(next_path,b"NEW COMPLETE\n"),0)
                self.assertEqual(next_path.read_bytes(),b"NEW COMPLETE\n")
                self.assertEqual(target.read_bytes(),b"PARTIAL COMMIT\n")
                self.assertEqual(self.state(next_path),1)
    def test_unsafe_or_occupied_temp_refused_before_commit(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"pending"
            tmp=Path(str(target)+".tmp")
            tmp.write_bytes(b"FOREIGN STAGE")
            tmp.chmod(0o600)
            start=self.lib.vh100_directory_syncs()
            self.assertEqual(self.publish(target),-1)
            self.assertEqual(self.lib.vh100_directory_syncs(),start)
            self.assertEqual(tmp.read_bytes(),b"FOREIGN STAGE")
            self.assertEqual(self.state(target),2)
            self.assertFalse(target.exists())
            poisoned=Path(td)/"symlink"
            Path(str(poisoned)+".tmp").symlink_to(tmp)
            self.assertEqual(self.publish(poisoned),-1)
            self.assertEqual(self.state(poisoned),-1)
            self.assertEqual(tmp.read_bytes(),b"FOREIGN STAGE")
    def test_failed_post_link_cleanup_requires_new_name(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"generation1"
            other=Path(td)/"generation2"
            self.lib.vh100_test_fail_at(2)
            self.assertEqual(self.publish(target,b"OLD"),-1)
            self.assertEqual(self.state(target),3)
            staged=Path(str(target)+".tmp")
            self.assertEqual(staged.read_bytes(),b"OLD")
            self.lib.vh100_test_fail_at(0)
            self.assertEqual(self.publish(target,b"FORBIDDEN"),-1)
            self.assertEqual(self.publish(other,b"SECOND"),0)
            self.assertEqual(staged.read_bytes(),b"OLD")
            self.assertEqual(target.read_bytes(),b"OLD")
            self.assertEqual(other.read_bytes(),b"SECOND")
    def test_unsafe_relative_and_traversal_path_refused(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self.publish(Path("relative")), -1)
            self.assertEqual(self.publish(Path(td)/"../unsafe"),-1)
            self.assertEqual(self.publish(Path(td)/"."),-1)

class V100PrivateAudit(unittest.TestCase):
    def test_success_and_old_v99_checkpoint(self):
        proof=summarize(encode(fixture()))
        self.assertEqual(proof["successful_post_hardlink_parent_directory_syncs"],2)
        self.assertEqual(proof["successful_post_stage_unlink_parent_directory_syncs"],2)
        self.assertEqual(proof["final_private_journal_events"],
                         proof["predecessor_private_events"]+3)
        self.assertFalse(proof["real_power_loss_simulated"])
        self.assertFalse(proof["HD_replacement_approved"])
        self.assertTrue(prior(encode(fixture()))["only_distinct_unoccupied_target_accepted"])
    def test_reject_missing_post_link_fsync(self):
        rows=fixture();rows[-3]["value"]=1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_missing_post_unlink_fsync(self):
        rows=fixture();rows[-2]["value"]=1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_target_accepted(self):
        rows=fixture();rows[-1]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_kind(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,x in enumerate(rows):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_forged_CPU_cycle_or_frame(self):
        rows=fixture();rows[-2]["cycle"]=1
        with self.assertRaises(Refused):summarize(encode(rows))
        rows=fixture();rows[-1]["frame"]=9
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_pinned_full_emulator_is_opt_in_only(self):
        source=(ROOT/"tools/apply_map02_v100_pcsx_rearmed.py").read_text()
        for needle in ("apply_v99(root)","--vh100-directory-fsync-smoke",
                       "vh100_directory_syncs()",
                       "VH100_DURABILITY_PASS",
                       "native_parent_directory_fsync_post_link=True",
                       "isolated_faults_only_never_production=True",
                       "original_retail_MAP02_verified=False",
                       "HD_replacement_approved=False"):
            self.assertIn(needle,source)

if __name__=="__main__":unittest.main()
