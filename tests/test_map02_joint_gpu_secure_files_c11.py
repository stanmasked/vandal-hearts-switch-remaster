"""Native Linux C test of the joint MAP02 GPU observer's secure file publisher."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.instrument_map02_joint_gpu_frame import SECURE_JOURNAL

SOURCE = (r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
''' + SECURE_JOURNAL + r'''
int main(int argc, char **argv)
{
    FILE *a, *b;
    struct stat file_stat;
    if (argc < 3 || vh_map02_joint_events_completed != 0u) return 31;
    if (strcmp(argv[1], "new") == 0) {
        a = VH_Map02SecureFile(argv[2]);
        if (!a) return 32;
        if (fwrite("private", 1, 7, a) != 7 || fclose(a)) return 33;
        if (stat(argv[2], &file_stat)) return 34;
        return (file_stat.st_mode & 0777) == 0600 ? 0 : 35;
    }
    if (strcmp(argv[1], "refuse") == 0) {
        a = VH_Map02SecureFile(argv[2]);
        if (a) { fclose(a); return 36; }
        return 0;
    }
    if (strcmp(argv[1], "exclusive") == 0) {
        a = VH_Map02SecureFile(argv[2]);
        if (!a) return 37;
        if (fwrite("ONE", 1, 3, a) != 3 || fclose(a)) return 38;
        b = VH_Map02SecureFile(argv[2]);
        if (b) { fclose(b); return 39; }
        return 0;
    }
    if (strcmp(argv[1], "log") == 0 && argc == 5) {
        a = VH_Map02SecureLog(argv[2]);
        if (!a) return 40;
        if (fputs("first\n", a) < 0 || VH_Map02FlushLog(a)) return 41;
        if (rename(argv[2], argv[3])) return 42;
        if (symlink(argv[4], argv[2])) return 43;
        b = VH_Map02SecureLog(argv[2]);
        if (a != b) return 44;
        if (fputs("second\n", b) < 0 || VH_Map02FlushLog(b)) return 45;
        return 0;
    }
    return 46;
}
''')


class NativeJointPrivatePublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix" or not Path("/proc/self/fd").is_dir():
            raise unittest.SkipTest("Linux procfs required for private journal test")
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-map02-journal-c-")
        root = Path(cls.temp.name)
        src = root / "publisher.c"
        cls.program = root / "publisher"
        src.write_text(SOURCE, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise RuntimeError("native C compiler missing")
        subprocess.run([
            cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1",
            str(src), "-o", str(cls.program)
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.temp_single = tempfile.TemporaryDirectory(prefix="vh-map02-journal-")
        self.addCleanup(self.temp_single.cleanup)
        self.directory = Path(self.temp_single.name)

    def run_c(self, mode, *args):
        result = subprocess.run([str(self.program), mode, *map(str, args)],
                                capture_output=True, timeout=4)
        self.assertEqual(result.returncode, 0,
                         f"native journal writer exit={result.returncode}")
        self.assertEqual(result.stdout, b"")

    def test_exclusive_new_file_is_owner_private(self):
        target = self.directory / "private.bin"
        self.run_c("new", target)
        self.assertEqual(target.read_bytes(), b"private")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_open_existing_file_never_truncates(self):
        target = self.directory / "existing"
        target.write_bytes(b"DO NOT CHANGE")
        self.run_c("refuse", target)
        self.assertEqual(target.read_bytes(), b"DO NOT CHANGE")

    def test_second_creation_in_one_session_refused(self):
        target = self.directory / "same"
        self.run_c("exclusive", target)
        self.assertEqual(target.read_bytes(), b"ONE")

    def test_symlink_to_external_file_refused(self):
        target = self.directory / "link"
        external = self.directory / "important"
        external.write_bytes(b"KEEP ME")
        target.symlink_to(external)
        self.run_c("refuse", target)
        self.assertEqual(external.read_bytes(), b"KEEP ME")

    def test_dangling_symlink_refused(self):
        target = self.directory / "link"
        target.symlink_to(self.directory / "nonexistent")
        self.run_c("refuse", target)
        self.assertTrue(target.is_symlink())

    def test_hardlink_to_external_file_refused(self):
        target = self.directory / "alias"
        external = self.directory / "important"
        external.write_bytes(b"KEEP ME")
        os.link(external, target)
        self.run_c("refuse", target)
        self.assertEqual(external.read_bytes(), b"KEEP ME")

    def test_open_journal_stays_on_original_inode_during_symlink_swap(self):
        journal = self.directory / "events.jsonl"
        moved = self.directory / "moved-events.jsonl"
        decoy = self.directory / "decoy.jsonl"
        decoy.write_bytes(b"UNCHANGED")
        self.run_c("log", journal, moved, decoy)
        self.assertEqual(moved.read_bytes(), b"first\nsecond\n")
        self.assertEqual(decoy.read_bytes(), b"UNCHANGED")
        self.assertTrue(journal.is_symlink())

    def test_other_child_cannot_open_precreated_log(self):
        target = self.directory / "events.jsonl"
        self.run_c("new", target)
        self.run_c("refuse", target)
        self.assertEqual(target.read_bytes(), b"private")


if __name__ == "__main__":
    unittest.main()
