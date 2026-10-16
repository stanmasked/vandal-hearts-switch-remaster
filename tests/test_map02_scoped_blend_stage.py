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
    vh_map02_probe_begin(9, 10, 0x0473, 0x0020, 0, 0, 0, 1);
    vh_map02_probe_end(9, 10, 0x0020); /* opaque, no BlendG1 call */
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_end_frame());
    if (strncmp(argv[2], "pair-", 5) == 0)
        result = vh_map02_stage_private_pair(argv[1]);
    else
        result = vh_map02_stage_private_blendg1(argv[1]);
    if (strcmp(argv[2], "publish") == 0 || strcmp(argv[2], "pair-publish") == 0) {
        assert(result);
        return 0;
    }
    if (strcmp(argv[2], "refuse") == 0 || strcmp(argv[2], "pair-refuse") == 0) {
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

    def test_pair_has_same_frame_and_independent_blend_events(self):
        self.run_stage("pair-publish")
        pixel_file = self.private / "putpixel-native-events.pending.jsonl"
        blend_file = self.private / "blendg1-native-events.pending.jsonl"
        pixel_raw, blend_raw = pixel_file.read_bytes(), blend_file.read_bytes()
        pixels = [json.loads(line) for line in pixel_raw.splitlines()]
        blends = [json.loads(line) for line in blend_raw.splitlines()]
        self.assertEqual(len(pixels), 2)
        self.assertEqual(len(blends), 1)
        self.assertEqual([p["step"] for p in pixels], [0, 1])
        self.assertEqual(pixels[0]["frame"], blends[0]["frame"])
        self.assertEqual(pixels[0]["primitive_ordinal"],
                         blends[0]["primitive_ordinal"])
        self.assertEqual(blends[0]["blend_fg"], pixels[0]["front"] | 0x8000)
        self.assertEqual(blends[0]["blend_result"], pixels[0]["after"])
        self.assertEqual([p["semi"] for p in pixels], [1, 0])
        self.assertEqual(stat.S_IMODE(pixel_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(blend_file.stat().st_mode), 0o600)
        self.run_stage("pair-refuse")
        self.assertEqual(pixel_file.read_bytes(), pixel_raw)
        self.assertEqual(blend_file.read_bytes(), blend_raw)
        self.assertFalse(list(self.private.glob(".*.tmp")))

    def test_pair_rolls_back_if_second_destination_exists(self):
        pixel_file = self.private / "putpixel-native-events.pending.jsonl"
        pixel_file.write_bytes(b"occupied\n")
        self.run_stage("pair-refuse")
        self.assertEqual(pixel_file.read_bytes(), b"occupied\n")
        self.assertFalse((self.private /
                          "blendg1-native-events.pending.jsonl").exists())
        self.assertFalse(list(self.private.glob(".*.tmp")))

    def test_pair_rejects_second_destination_symlink(self):
        target = self.root / "target"
        target.write_bytes(b"untouched\n")
        (self.private / "putpixel-native-events.pending.jsonl").symlink_to(target)
        self.run_stage("pair-refuse")
        self.assertEqual(target.read_bytes(), b"untouched\n")
        self.assertFalse((self.private /
                          "blendg1-native-events.pending.jsonl").exists())
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
