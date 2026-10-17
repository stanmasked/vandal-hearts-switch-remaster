#!/usr/bin/env python3
"""v99 native POSIX interrupted .tmp publication: no reuse, replay or leaks."""
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
from test_map02_v98_recovery import fixture as v98_fixture,encode
from tools.summarize_map02_v98_recovery import summarize as prior
from tools.summarize_map02_v99_interrupted import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    items=v98_fixture()
    for name in KINDS:
        items.append(dict(kind=name,value=1,seq=len(items)+1,cycle=0,frame=0))
    return items

class NativeInterruptedExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        td=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        td/"vh82_private_publish.h")
        binary=td/"libvh99.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(td),"-o",str(binary)],
                       capture_output=True,check=True)
        cls.lib=ctypes.CDLL(str(binary))
        cls.lib.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh82_publish_private.restype=ctypes.c_int
        cls.lib.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.lib.vh99_private_state.restype=ctypes.c_int
        cls.lib.vh99_publish_after_interruption.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.lib.vh99_publish_after_interruption.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def state(self,path):
        return self.lib.vh99_private_state(os.fsencode(path))
    def publish(self,path,data):
        return self.lib.vh82_publish_private(os.fsencode(path),data,len(data))
    def recover(self,abandoned,new,data):
        return self.lib.vh99_publish_after_interruption(
            os.fsencode(abandoned),os.fsencode(new),data,len(data))
    def stage(self,path,data=b"TRUNCATED PREVIOUS GPU LOG"):
        staged=Path(str(path)+".tmp")
        staged.write_bytes(data)
        staged.chmod(0o600)
        return staged
    def test_interrupted_stage_cannot_publish_old_but_fresh_name_can(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"old.final"
            new=Path(td)/"new.final"
            partial=b'{"truncated":true'
            complete=b'{"generation":2,"complete":true}\n'
            stale=self.stage(old,partial)
            before=stale.stat()
            self.assertEqual(self.state(old),2)
            self.assertEqual(self.state(new),0)
            self.assertEqual(self.publish(old,complete),-1)
            self.assertEqual(self.recover(old,old,complete),-1)
            self.assertFalse(old.exists())
            self.assertEqual(self.recover(old,new,complete),0)
            self.assertEqual(self.recover(old,new,complete),-1)
            self.assertEqual(self.state(old),2)
            self.assertEqual(self.state(new),1)
            self.assertEqual(stale.read_bytes(),partial)
            self.assertEqual(new.read_bytes(),complete)
            self.assertEqual(stale.stat().st_ino,before.st_ino)
            self.assertEqual(stale.stat().st_size,before.st_size)
            self.assertFalse(old.exists())
            self.assertEqual(new.stat().st_mode & 0o777,0o600)
            self.assertFalse(Path(str(new)+".tmp").exists())
    def test_private_states_after_crash_before_and_after_link(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"stage"
            self.assertEqual(self.state(root),0)
            stage=self.stage(root)
            self.assertEqual(self.state(root),2)
            stage.unlink()
            self.assertEqual(self.publish(root,b"COMMITTED\n"),0)
            self.assertEqual(self.state(root),1)
            self.stage(root,b"OLD STAGED RESIDUE")
            self.assertEqual(self.state(root),3)
            self.assertEqual(self.recover(root,Path(td)/"new",b"NEXT\n"),-1)
            self.assertEqual(root.read_bytes(),b"COMMITTED\n")
    def test_reject_foreign_symlink_stage_without_removal(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"abandoned"
            new=Path(td)/"new"
            victim=Path(td)/"victim";victim.write_bytes(b"KEEP UNTOUCHED")
            stage=Path(str(old)+".tmp")
            stage.symlink_to(victim)
            self.assertEqual(self.state(old),-1)
            self.assertEqual(self.recover(old,new,b"new data"),-1)
            self.assertTrue(stage.is_symlink())
            self.assertEqual(victim.read_bytes(),b"KEEP UNTOUCHED")
            self.assertFalse(new.exists())
    def test_refuse_insecure_stage_mode(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"old"
            stage=self.stage(old)
            stage.chmod(0o644)
            self.assertEqual(self.state(old),-1)
            self.assertEqual(self.recover(old,Path(td)/"new",b"good"),-1)
            self.assertEqual(stage.read_bytes(),b"TRUNCATED PREVIOUS GPU LOG")
    def test_failed_new_temp_kept_then_choose_another_new_name(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"abandoned"
            original=b"INCOMPLETE"
            staged=self.stage(old,original)
            blocked=Path(td)/"blocked"
            unsafe_temp=Path(str(blocked)+".tmp")
            unsafe_temp.write_bytes(b"FOREIGN TMP")
            unsafe_temp.chmod(0o600)
            self.assertEqual(self.state(blocked),2)
            self.assertEqual(self.recover(old,blocked,b"RESTART"),-1)
            self.assertEqual(unsafe_temp.read_bytes(),b"FOREIGN TMP")
            self.assertFalse(blocked.exists())
            third=Path(td)/"unique"
            self.assertEqual(self.recover(old,third,b"RESTART"),0)
            self.assertEqual(staged.read_bytes(),original)
            self.assertEqual(third.read_bytes(),b"RESTART")
    def test_existing_complete_target_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"abandoned"
            target=Path(td)/"present"
            staged=self.stage(old,b"PARTIAL")
            self.assertEqual(self.publish(target,b"ORIGINAL"),0)
            self.assertEqual(self.recover(old,target,b"REPLACEMENT"),-1)
            self.assertEqual(target.read_bytes(),b"ORIGINAL")
            self.assertEqual(staged.read_bytes(),b"PARTIAL")
    def test_missing_old_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"missing"
            new=Path(td)/"next"
            self.assertEqual(self.recover(old,new,b"NEW"),-1)
            self.assertEqual(self.state(Path(td)/"../unsafe"),-1)
            self.stage(old,b"PARTIAL")
            self.assertEqual(self.recover(old,Path(td)/"../unsafe",b"NEW"),-1)
            self.assertEqual(self.recover(old,Path("relative"),b"NEW"),-1)
            self.assertFalse(new.exists())
    def test_empty_old_stage_still_incomplete_not_success(self):
        with tempfile.TemporaryDirectory() as td:
            old=Path(td)/"empty"
            new=Path(td)/"fresh"
            staged=self.stage(old,b"")
            self.assertEqual(self.state(old),2)
            self.assertEqual(self.publish(old,b"full"),-1)
            self.assertEqual(self.recover(old,new,b"full"),0)
            self.assertEqual(staged.read_bytes(),b"")
            self.assertEqual(new.read_bytes(),b"full")

class PrivateV99Audit(unittest.TestCase):
    def test_v99_valid_suffix_and_full_v98_checkpoint(self):
        report=summarize(encode(fixture()))
        self.assertEqual(report["final_private_journal_events"],
                         report["earlier_v98_checkpoint_entries"]+3)
        self.assertTrue(report["incomplete_stage_refused_for_original_final_path"])
        self.assertTrue(report["existing_staged_data_remained_byte_exact"])
        self.assertFalse(report["HD_replacement_approved"])
        self.assertTrue(prior(encode(fixture()))["duplicate_new_private_filename_rejected"])
    def test_refuse_interrupted_stage_accepted_as_complete(self):
        rows=fixture();rows[-3]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_successful_fresh_recovery(self):
        rows=fixture();rows[-2]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_staged_file_mutation(self):
        rows=fixture();rows[-1]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_reordered_metrics(self):
        rows=fixture();rows[-1]["kind"],rows[-2]["kind"]=rows[-2]["kind"],rows[-1]["kind"]
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_duplicate_metric(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,x in enumerate(rows):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_forged_emulator_frame(self):
        rows=fixture();rows[-1]["frame"]=22
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_source_retains_original_pcsx_provenance(self):
        code=(ROOT/"tools/apply_map02_v99_pcsx_rearmed.py").read_text()
        for check in ("apply_v98(root)","--vh99-interrupted-export-smoke",
                      "vh99_private_state(abandoned)","vh99_publish_after_interruption",
                      "VH99_INTERRUPTION_PASS","original_v82_final_destination_untouched=True",
                      "original_retail_MAP02_verified=False",
                      "HD_replacement_approved=False"):
            self.assertIn(check,code)

if __name__=="__main__":unittest.main()
