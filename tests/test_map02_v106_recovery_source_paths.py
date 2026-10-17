#!/usr/bin/env python3
"""v106 native rooted no-follow recovery-source tests, incl. deterministic redirect."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class NativeSourcePaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:
            raise unittest.SkipTest("native GCC/Clang unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        work=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        work/"vh82_private_publish.h")
        lib=work/"v106.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(work),"-o",str(lib)],
                       capture_output=True,check=True)
        cls.dll=ctypes.CDLL(str(lib))
        cls.dll.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh82_publish_private.restype=ctypes.c_int
        cls.dll.vh98_publish_recovery.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh98_publish_recovery.restype=ctypes.c_int
        cls.dll.vh99_publish_after_interruption.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh99_publish_after_interruption.restype=ctypes.c_int
        cls.dll.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.dll.vh99_private_state.restype=ctypes.c_int
        cls.dll.vh102_test_parent_redirect.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
        cls.dll.vh102_test_parent_redirect.restype=ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def publish(self,p,b):
        return self.dll.vh82_publish_private(os.fsencode(p),b,len(b))

    def recover(self,p,q,b):
        return self.dll.vh98_publish_recovery(
            os.fsencode(p),os.fsencode(q),b,len(b))

    def interrupted(self,p,q,b):
        return self.dll.vh99_publish_after_interruption(
            os.fsencode(p),os.fsencode(q),b,len(b))

    @staticmethod
    def stage(p,b=b"incomplete 0600 journal"):
        s=Path(str(p)+".tmp")
        s.write_bytes(b)
        s.chmod(0o600)
        return s

    def redirect(self,parent,moved,target):
        return self.dll.vh102_test_parent_redirect(
            os.fsencode(parent),os.fsencode(moved),
            os.fsencode(target),1)

    def test_nested_real_source_recovery_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source=root/"real"/"nested"
            source.mkdir(parents=True)
            old=source/"completed"; staged=source/"abandoned"
            self.assertEqual(self.publish(old,b"original"),0)
            self.stage(staged)
            self.assertEqual(self.recover(old,root/"fresh1",b"generation2"),0)
            self.assertEqual(self.interrupted(staged,root/"fresh2",b"generation3"),0)
            self.assertEqual(old.read_bytes(),b"original")
            self.assertEqual((root/"fresh1").read_bytes(),b"generation2")
            self.assertEqual((root/"fresh2").read_bytes(),b"generation3")

    def test_intermediate_symlink_rejected_for_both_source_types(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            real=root/"real"; real.mkdir()
            alias=root/"alias"; alias.symlink_to(real,target_is_directory=True)
            completed=real/"finished"
            self.assertEqual(self.publish(completed,b"trusted"),0)
            staged=self.stage(real/"abandoned",b"partial")
            self.assertEqual(self.recover(alias/"finished",root/"next1",b"next"),-1)
            self.assertEqual(self.dll.vh99_private_state(
                os.fsencode(alias/"abandoned")),-1)
            self.assertEqual(self.interrupted(
                alias/"abandoned",root/"next2",b"next"),-1)
            self.assertEqual(completed.read_bytes(),b"trusted")
            self.assertEqual(staged.read_bytes(),b"partial")
            self.assertFalse((root/"next1").exists())
            self.assertFalse((root/"next2").exists())

    def test_symlink_in_grandparent_and_leaf_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            real=root/"real"; inner=real/"inner"; inner.mkdir(parents=True)
            link=root/"link"; link.symlink_to(real,target_is_directory=True)
            done=inner/"done"; self.assertEqual(self.publish(done,b"old"),0)
            stage=self.stage(inner/"partial")
            leaf_link=inner/"done_link";leaf_link.symlink_to(done)
            target=root/"new"
            self.assertEqual(self.recover(link/"inner"/"done",target,b"new"),-1)
            self.assertEqual(self.recover(leaf_link,target,b"new"),-1)
            self.assertEqual(self.interrupted(
                link/"inner"/"partial",target,b"new"),-1)
            self.assertEqual(done.read_bytes(),b"old")
            self.assertEqual(stage.read_bytes(),b"incomplete 0600 journal")
            self.assertFalse(target.exists())

    def test_swapped_source_parent_refused_after_distinct_new_commit_v98(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            parent=root/"source";parent.mkdir()
            decoy=root/"decoy";decoy.mkdir()
            moved=root/"old-source-original"
            old=parent/"original"
            original=b"trusted old completed journal"
            fresh=root/"new"
            self.assertEqual(self.publish(old,original),0)
            self.assertEqual(self.redirect(parent,moved,decoy),0)
            self.assertEqual(self.recover(old,fresh,b"new generation"),-1)
            self.assertTrue(parent.is_symlink())
            self.assertEqual((moved/"original").read_bytes(),original)
            self.assertEqual(fresh.read_bytes(),b"new generation")
            self.assertEqual(self.recover(old,fresh,b"clobber"),-1)
            self.assertEqual(fresh.read_bytes(),b"new generation")

    def test_swapped_source_parent_refused_after_distinct_new_commit_v99(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            parent=root/"source";parent.mkdir()
            decoy=root/"decoy";decoy.mkdir()
            moved=root/"old-source-original"
            interrupted=parent/"incomplete"
            staged=self.stage(interrupted,b"preserve abandoned bytes")
            fresh=root/"new"
            self.assertEqual(self.redirect(parent,moved,decoy),0)
            self.assertEqual(self.interrupted(interrupted,fresh,b"new bytes"),-1)
            self.assertTrue(parent.is_symlink())
            self.assertEqual((moved/"incomplete.tmp").read_bytes(),
                             b"preserve abandoned bytes")
            self.assertEqual(fresh.read_bytes(),b"new bytes")
            self.assertEqual(self.dll.vh99_private_state(
                os.fsencode(interrupted)),-1)
            self.assertEqual(self.interrupted(interrupted,fresh,b"overwrite"),-1)
            self.assertEqual(fresh.read_bytes(),b"new bytes")

    def test_no_relative_dotdot_or_trailing_source_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            path=root/"owned"; self.assertEqual(self.publish(path,b"old"),0)
            fresh=root/"fresh"
            for unsafe in (root/"."/ "owned",root/".."/"owned",
                           Path("relative"),Path(str(root)+"/")):
                # pathlib normalizes interior '.', so only non-normalized
                # string cases below are authoritative for dot segments.
                if unsafe==path:
                    continue
                self.assertEqual(self.recover(unsafe,fresh,b"new"),-1)
            for unsafe in (str(root)+"/./owned",str(root)+"/../owned",
                           str(root)+"//owned",str(path)+"/",
                           str(root)+"/."):

                self.assertEqual(self.recover(unsafe,fresh,b"new"),-1)
                self.assertEqual(self.dll.vh99_private_state(os.fsencode(unsafe)),-1)
            self.assertFalse(fresh.exists())


if __name__=="__main__":
    unittest.main()
