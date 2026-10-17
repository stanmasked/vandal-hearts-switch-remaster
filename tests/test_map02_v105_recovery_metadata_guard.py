#!/usr/bin/env python3
"""v105 native fail-closed old-source/abandoned-stage same-inode recovery tests."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class NativeRecoveryMetadataGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:
            raise unittest.SkipTest("native GCC/Clang is unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        directory=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        directory/"vh82_private_publish.h")
        library=directory/"vh105.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(directory),"-o",str(library)],
                       check=True,capture_output=True)
        cls.dll=ctypes.CDLL(str(library))
        for name,count in (("vh82_publish_private",3),
                           ("vh98_publish_recovery",4),
                           ("vh99_publish_after_interruption",4)):
            method=getattr(cls.dll,name)
            method.argtypes=[ctypes.c_char_p]*(count-1)+[ctypes.c_size_t]
            method.restype=ctypes.c_int
        cls.dll.vh99_private_state.argtypes=[ctypes.c_char_p]
        cls.dll.vh99_private_state.restype=ctypes.c_int
        cls.dll.vh105_test_change_during_recovery.argtypes=[ctypes.c_int]
        cls.dll.vh105_test_change_during_recovery.restype=None

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def publish(self,path,data):
        return self.dll.vh82_publish_private(os.fsencode(path),data,len(data))

    def recover_old(self,old,fresh,data):
        return self.dll.vh98_publish_recovery(os.fsencode(old),
                                              os.fsencode(fresh),data,len(data))

    def recover_stage(self,old,fresh,data):
        return self.dll.vh99_publish_after_interruption(
            os.fsencode(old),os.fsencode(fresh),data,len(data))

    def test_clean_recovery_old_and_abandoned_stage_preserve_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            old=root/"old"
            new=root/"new"
            stage_old=root/"abandoned"
            stage=Path(str(stage_old)+".tmp")
            original=b"first immutable generation"
            partial=b"partial incomplete contents"
            self.assertEqual(self.publish(old,original),0)
            stage.write_bytes(partial)
            stage.chmod(0o600)
            self.assertEqual(self.recover_old(old,new,b"second generation"),0)
            self.assertEqual(self.recover_stage(stage_old,root/"fresh",b"complete"),0)
            self.assertEqual(old.read_bytes(),original)
            self.assertEqual(stage.read_bytes(),partial)
            self.assertEqual(new.read_bytes(),b"second generation")
            self.assertEqual((root/"fresh").read_bytes(),b"complete")

    def test_old_committed_file_rewrite_same_inode_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            old=root/"old"; fresh=root/"fresh"
            original=b"previous 0600 private GPU journal"
            current=b"new committed private GPU journal"
            self.assertEqual(self.publish(old,original),0)
            original_stat=old.stat()
            self.dll.vh105_test_change_during_recovery(1)
            self.assertEqual(self.recover_old(old,fresh,current),-1)
            changed=old.stat()
            self.assertEqual(changed.st_ino,original_stat.st_ino)
            self.assertEqual(changed.st_size,original_stat.st_size)
            self.assertNotEqual(old.read_bytes(),original)
            self.assertEqual(fresh.read_bytes(),current)
            self.assertEqual(fresh.stat().st_mode & 0o777,0o600)
            self.assertEqual(self.recover_old(old,fresh,b"overwrite"),-1)
            self.assertEqual(fresh.read_bytes(),current)
            self.assertFalse(Path(str(fresh)+".tmp").exists())

    def test_abandoned_stage_rewrite_same_inode_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            old=root/"old"; fresh=root/"fresh"
            stage=Path(str(old)+".tmp")
            incomplete=b"partial old private GPU observer"
            latest=b"separate fresh private observation"
            stage.write_bytes(incomplete)
            stage.chmod(0o600)
            original_stat=stage.stat()
            self.assertEqual(self.dll.vh99_private_state(os.fsencode(old)),2)
            self.dll.vh105_test_change_during_recovery(2)
            self.assertEqual(self.recover_stage(old,fresh,latest),-1)
            changed=stage.stat()
            self.assertEqual(changed.st_ino,original_stat.st_ino)
            self.assertEqual(changed.st_size,original_stat.st_size)
            self.assertNotEqual(stage.read_bytes(),incomplete)
            self.assertEqual(fresh.read_bytes(),latest)
            self.assertEqual(self.dll.vh99_private_state(os.fsencode(old)),2)
            self.assertEqual(self.dll.vh99_private_state(os.fsencode(fresh)),1)
            self.assertEqual(self.recover_stage(old,fresh,b"reuse"),-1)
            self.assertEqual(fresh.read_bytes(),latest)

    def test_normal_build_excludes_all_v105_test_hooks(self):
        cc=shutil.which(os.environ.get("CC","cc"))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"normal.so"
            shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                            Path(td)/"vh82_private_publish.h")
            subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                            "-shared","-fPIC",
                            str(ROOT/"tools/map02_v82_private_publish.c"),
                            "-I",td,"-o",str(path)],check=True,capture_output=True)
            prod=ctypes.CDLL(str(path))
            self.assertFalse(hasattr(prod,"vh105_test_change_during_recovery"))


if __name__=="__main__":
    unittest.main()
