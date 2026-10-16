"""POSIX-only native BlendG1 staging smoke tests; synthetic colors only.

Verifies that a sealed bounded C witness is written once, privately, with
exact bytes, and no file is created for incomplete/invalid observations.
"""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include <assert.h>
#include <string.h>
#include "map02_scoped_blend_sink.h"
#include "map02_scoped_blend_stage.h"

int main(int argc, char **argv) {
    int result;
    if (argc != 3) return 2;
    vh_map02_scope_reset();
    if (strcmp(argv[2], "unselected") == 0) {
        assert(!vh_map02_stage_private_blendg1(argv[1]));
        return 0;
    }
    assert(vh_map02_scope_begin_frame(23, 9, 10));
    assert(vh_map02_scope_begin_primitive(0, 4));
    vh_map02_probe_begin(9, 10, 31, 0x0234, 3, 1, 1, 1);
    vh_map02_probe_blendg1(9, 10, 0x8234, 31, 0x0473, 3, 1);
    vh_map02_probe_end(9, 10, 0x0473);
    if (strcmp(argv[2], "incomplete") == 0) {
        assert(!vh_map02_stage_private_blendg1(argv[1]));
        return 0;
    }
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_end_frame());
    result = vh_map02_stage_private_blendg1(argv[1]);
    if (strcmp(argv[2], "publish") == 0) {
        assert(result);
        return 0;
    }
    if (strcmp(argv[2], "refuse") == 0) {
        assert(!result);
        return 0;
    }
    return 3;
}
"""


@unittest.skipUnless(os.name == "posix" and shutil.which("cc"),
                     "requires POSIX and a C99 host compiler")
class PrivateBlendStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        main = self.root / "main.c"
        self.binary = self.root / "stage-test"
        main.write_text(HARNESS, encoding="utf-8")
        subprocess.run([
            "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "tools"),
            str(main), str(ROOT / "tools/map02_scoped_blend_sink.c"),
            str(ROOT / "tools/map02_scoped_blend_stage.c"),
            "-o", str(self.binary)],
            check=True, capture_output=True, text=True)

    def run_stage(self, mode, directory=None):
        subprocess.run([str(self.binary), str(directory or self.private), mode],
                       check=True, capture_output=True, text=True)

    def test_private_complete_one_time_publication(self):
        self.run_stage("publish")
        final = self.private / "blendg1-native-events.pending.jsonl"
        raw = final.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o600)
        event = json.loads(raw)
        self.assertEqual(event["stage"], "native_blendg1")
        self.assertEqual(event["primitive_type"], 4)
        self.assertEqual(event["blend_fg"], 0x8234)
        self.assertEqual(event["blend_bg"], 31)
        self.assertEqual(event["blend_result"], 0x0473)
        self.run_stage("refuse")
        self.assertEqual(final.read_bytes(), raw)
        self.assertFalse(list(self.private.glob(".*.tmp")))

    def test_unselected_incomplete_and_nonprivate_directories(self):
        self.run_stage("unselected")
        self.run_stage("incomplete")
        self.assertEqual(list(self.private.iterdir()), [])
        os.chmod(self.private, 0o755)
        self.run_stage("refuse")
        self.assertEqual(list(self.private.iterdir()), [])

    def test_symlink_directory_and_existing_pending_symlink(self):
        shortcut = self.root / "directory-symlink"
        shortcut.symlink_to(self.private, target_is_directory=True)
        self.run_stage("refuse", shortcut)
        target = self.root / "existing.txt"
        target.write_text("untouched\n")
        (self.private / "blendg1-native-events.pending.jsonl").symlink_to(target)
        self.run_stage("refuse")
        self.assertEqual(target.read_text(), "untouched\n")
        self.assertFalse(list(self.private.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
