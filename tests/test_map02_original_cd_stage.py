"""Asset-free five-file atomic MAP02 original CdRead and GPU scoped staging."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from tests.test_map02_scoped_blend_stage import HARNESS, ROOT

INJECTION = r"""
#ifdef VH_MAP02_CD_READ_PROBE
    {
        unsigned char raw[2048], data[12 * 2048];
        int i;
        for (i = 0; i < (int)sizeof(data); i++)
            data[i] = (unsigned char)(i & 255);
        vh_map02_cd_loader_claim(42, 42, 0x1bcc, 12);
        vh_map02_cd_read_start(0x1bcc, 12);
        for (i = 0; i < 12; i++) {
            memcpy(raw, data + i * 2048, sizeof raw);
            vh_map02_cd_read_sector(0x1bcc + i, raw);
        }
        vh_map02_cd_read_finish(0x1bcc, 12, data);
        if (strcmp(argv[2], "pair-incomplete-cd"))
            vh_map02_cd_loader_complete(42, 42, 99);
    }
#endif
"""
SOURCE = (
    HARNESS.replace('#include "map02_scoped_blend_stage.h"',
                    '#include "map02_scoped_blend_stage.h"\n'
                    '#include "map02_cd_read_probe.h"')
    .replace('    if (strncmp(argv[2], "pair-", 5) == 0)',
             INJECTION + '\n    if (strncmp(argv[2], "pair-", 5) == 0)')
    .replace('    return 3;\n}',
             '    if (strcmp(argv[2], "pair-incomplete-cd") == 0) {\n'
             '        assert(!result); return 0;\n'
             '    }\n    return 3;\n}')
)


class OriginalCdFiveFileStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        harness = self.root / "cd-paired.c"
        harness.write_text(SOURCE, encoding="utf-8")
        self.exe = self.root / "original-cd-five-stage"
        subprocess.run(
            ["cc", "-std=gnu99", "-Wall", "-Wextra", "-Werror",
             "-DVH_MAP02_VRAM_EDGE_PROBE", "-DVH_MAP02_CAPTURE_SESSION",
             "-DVH_MAP02_CD_READ_PROBE",
             "-I", str(ROOT / "tools"),
             str(harness),
             *[str(ROOT / "tools" / name) for name in (
                 "map02_scoped_blend_sink.c",
                 "map02_scoped_blend_stage.c",
                 "map02_vram_edges.c",
                 "map02_capture_session.c",
                 "map02_cd_read_probe.c",
             )],
             "-o", str(self.exe)],
            check=True, capture_output=True, text=True,
        )

    def call(self, directory, mode):
        p = subprocess.run([str(self.exe), str(directory), mode],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)

    def test_private_original_map02_cd_and_four_gpu_streams_staged_atomically(self):
        self.call(self.private, "pair-publish")
        expected = {
            "gpu-scoped-session.json",
            "map02-original-cd-read.pending.jsonl",
            "blendg1-native-events.pending.jsonl",
            "putpixel-native-events.pending.jsonl",
            "vram-edges-native-events.pending.jsonl",
        }
        self.assertEqual({p.name for p in self.private.iterdir()}, expected)
        for item in self.private.iterdir():
            self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o600)
        session = json.loads((self.private / "gpu-scoped-session.json").read_bytes())
        cd = json.loads(
            (self.private / "map02-original-cd-read.pending.jsonl").read_bytes())
        self.assertEqual(cd["capture_session"], session["capture_session"])
        self.assertEqual(cd["lba"], 0x1bcc)
        self.assertEqual(cd["sectors"], 12)
        self.assertEqual(cd["bytes"], 24576)
        self.assertTrue(cd["loader_completed"])
        self.assertEqual(cd["raw_user_crc32"], cd["returned_user_crc32"])
        self.assertFalse(list(self.private.glob(".*.tmp")))

    def test_failed_real_loader_completion_rolls_back_all_five(self):
        self.call(self.private, "pair-incomplete-cd")
        self.assertEqual(list(self.private.iterdir()), [])

    def test_existing_cd_file_prevents_any_other_gpu_witness_publishing(self):
        target = self.private / "map02-original-cd-read.pending.jsonl"
        target.write_bytes(b"do not overwrite\n")
        self.call(self.private, "pair-refuse")
        self.assertEqual([p.name for p in self.private.iterdir()], [target.name])
        self.assertEqual(target.read_bytes(), b"do not overwrite\n")
        self.assertFalse(list(self.private.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
