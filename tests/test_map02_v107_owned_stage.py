#!/usr/bin/env python3
"""v107: protect exact .tmp inode at every no-clobber publication boundary."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class NativeOwnedStage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:
            raise unittest.SkipTest("native GCC/Clang unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        work=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                        work/"vh82_private_publish.h")
        lib=work/"v107.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-DVH100_FAULT_TEST","-shared","-fPIC",
                        str(ROOT/"tools/map02_v82_private_publish.c"),
                        "-I",str(work),"-o",str(lib)],
                       check=True,capture_output=True)
        cls.dll=ctypes.CDLL(str(lib))
        cls.dll.vh82_publish_private.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
        cls.dll.vh82_publish_private.restype=ctypes.c_int
        cls.dll.vh107_test_replace_stage.argtypes=[
            ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
        cls.dll.vh107_test_replace_stage.restype=ctypes.c_int
        cls.dll.vh102_anchored_publishes.restype=ctypes.c_uint

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def publish(self,p,b):
        return self.dll.vh82_publish_private(os.fsencode(p),b,len(b))

    def replace(self,stage,other,backup,phase):
        return self.dll.vh107_test_replace_stage(
            os.fsencode(stage),os.fsencode(other),os.fsencode(backup),phase)

    def test_control_still_publishes_private_no_replace(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"committed"
            b=b"original sealed private test bytes\n"
            before=self.dll.vh102_anchored_publishes()
            self.assertEqual(self.publish(p,b),0)
            self.assertEqual(self.dll.vh102_anchored_publishes(),before+1)
            self.assertEqual(p.read_bytes(),b)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            self.assertFalse(Path(str(p)+".tmp").exists())
            self.assertEqual(self.publish(p,b"overwrite"),-1)
            self.assertEqual(p.read_bytes(),b)

    def test_same_byte_foreign_stage_rejected_preserved_at_all_phases(self):
        data=b"same byte exact payload is not the same inode\n"
        for phase in (1,2,3,4):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as td:
                root=Path(td)
                final=root/"trace"
                stage=Path(str(final)+".tmp")
                replacement=root/"outside-original-name"
                backup=root/"owned-stage-relocated"
                replacement.write_bytes(data)
                replacement.chmod(0o600)
                foreign_ino=replacement.stat().st_ino
                prior=self.dll.vh102_anchored_publishes()
                self.assertEqual(self.replace(stage,replacement,backup,phase),0)
                self.assertEqual(self.publish(final,data),-1)
                self.assertEqual(self.dll.vh102_anchored_publishes(),prior)
                self.assertTrue(stage.exists(),f"foreign stage removed, phase {phase}")
                self.assertEqual(stage.read_bytes(),data)
                self.assertEqual(backup.read_bytes(),data)
                self.assertEqual(stage.stat().st_ino,foreign_ino)
                self.assertNotEqual(backup.stat().st_ino,foreign_ino)
                self.assertEqual(stage.stat().st_mode & 0o777,0o600)
                self.assertFalse(replacement.exists())
                if phase<=2:
                    self.assertFalse(final.exists())
                elif phase==3:
                    # Wrong inode hard-linked after an injected pre-link swap
                    # must NOT count as successfully published.
                    self.assertEqual(final.stat().st_ino,foreign_ino)
                    self.assertEqual(final.read_bytes(),data)
                else:
                    # Original inode was already linked but its stage name
                    # was swapped before unlink; never delete new foreign one.
                    self.assertEqual(final.stat().st_ino,backup.stat().st_ino)
                    self.assertNotEqual(final.stat().st_ino,foreign_ino)
                self.assertEqual(self.publish(final,b"overwrite"),-1)
                if final.exists():
                    self.assertEqual(final.read_bytes(),data)
                fresh=root/"fresh-different-name"
                self.assertEqual(self.publish(fresh,b"new safe observation"),0)
                self.assertEqual(fresh.read_bytes(),b"new safe observation")
                self.assertEqual(stage.stat().st_ino,foreign_ino)

    def test_normal_production_build_has_no_v107_fault_symbols(self):
        cc=shutil.which(os.environ.get("CC","cc"))
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            shutil.copyfile(ROOT/"tools/map02_v82_private_publish.h",
                            work/"vh82_private_publish.h")
            lib=work/"production.so"
            subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                            "-shared","-fPIC",
                            str(ROOT/"tools/map02_v82_private_publish.c"),
                            "-I",td,"-o",str(lib)],
                           check=True,capture_output=True)
            normal=ctypes.CDLL(str(lib))
            self.assertFalse(hasattr(normal,"vh107_test_replace_stage"))


if __name__=="__main__":
    unittest.main()
