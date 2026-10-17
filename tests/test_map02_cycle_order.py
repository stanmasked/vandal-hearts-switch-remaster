"""Asset-free adversarial tests of the in-process MAP02 cycle state machine.

The harness emits calls itself: these tests do NOT execute original game
LoadCdFile / ContinueLoadingCdFile / DrawOTag, nor prove a MAP02 render.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include "map02_cycle_order.h"
#include "map02_cd_read_probe.h"
#include <limits.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    char out[512];
    unsigned char sectors[12u * 2048u], returned[12u * 2048u];
    int n, i;
    if (argc != 2) return 2;
    for (i = 0; i < (int)sizeof sectors; ++i)
        sectors[i] = (unsigned char)(i ^ (i >> 8));
    memcpy(returned, sectors, sizeof sectors);
    if (!strcmp(argv[1], "draw-early")) {
        vh_map02_cycle_draw_start(73);
        vh_map02_cycle_draw_finish(73, 1);
    }
    /* Match the pinned instrumented source's callback order:
     * original CD probe hook precedes the cycle hook at each boundary. */
    if (strcmp(argv[1], "cd-missing-claim"))
        vh_map02_cd_loader_claim(42, 42, 0x1bcc, 12);
    if (!strcmp(argv[1], "cd-duplicate-claim"))
        vh_map02_cd_loader_claim(42, 42, 0x1bcc, 12);
    vh_map02_cycle_load(42, 42, 0x1bcc, 12);
    if (!strcmp(argv[1], "duplicate-claim"))
        vh_map02_cycle_load(42, 42, 0x1bcc, 12);
    if (!strcmp(argv[1], "overflow-unrelated-read")) {
        vh_map02_cd_read_start(INT_MAX, INT_MAX);
        vh_map02_cycle_read_start(INT_MAX, INT_MAX);
    }
    if (!strcmp(argv[1], "overflow-overlapping-read")) {
        vh_map02_cd_read_start(0x1bcc, INT_MAX);
        vh_map02_cycle_read_start(0x1bcc, INT_MAX);
    }

    if (strcmp(argv[1], "cd-missing-read"))
        vh_map02_cd_read_start(0x1bcc, 12);
    if (strcmp(argv[1], "finish-first"))
        vh_map02_cycle_read_start(0x1bcc, 12);
    if (strcmp(argv[1], "cd-missing-read")) {
        for (i = 0; i < 12; ++i) {
            if (!strcmp(argv[1], "cd-missing-sector") && i == 11)
                continue;
            vh_map02_cd_read_sector(
                0x1bcc + i + (!strcmp(argv[1], "cd-wrong-sector") && i == 5),
                sectors + (size_t)i * 2048u);
        }
        if (!strcmp(argv[1], "cd-tampered-transfer"))
            returned[0] ^= 1u;
        vh_map02_cd_read_finish(0x1bcc, 12, returned);
    }
    vh_map02_cycle_read_finish(0x1bcc, 12);

    if (strcmp(argv[1], "cd-missing-completion"))
        vh_map02_cd_loader_complete(42, 42, 99);
    if (!strcmp(argv[1], "cd-duplicate-completion"))
        vh_map02_cd_loader_complete(42, 42, 99);

    if (strcmp(argv[1], "missing-completion"))
        vh_map02_cycle_loader_complete(42, 42, 99);
    if (!strcmp(argv[1], "duplicate-completion"))
        vh_map02_cycle_loader_complete(42, 42, 99);
    if (strcmp(argv[1], "no-draw")) {
        vh_map02_cycle_draw_start(73);
        vh_map02_cycle_draw_finish(73,
            strcmp(argv[1], "broken-ot") != 0);
    }
    n = vh_map02_cycle_format_jsonl(out, sizeof out);
    printf("failed=%d receipt=%d\n", vh_map02_cycle_failed(), n > 0);
    if (n > 0) fwrite(out, 1, (size_t)n, stdout);
    return 0;
}
"""


class CycleOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-cycle-order-")
        root = Path(cls.temp.name)
        src = root / "driver.c"
        src.write_text(HARNESS, encoding="utf-8")
        cls.exe = root / "driver"
        command = [
            "cc", "-std=gnu99", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
            "-I", str(ROOT / "tools"), str(src),
            str(ROOT / "tools/map02_cycle_order.c"),
            str(ROOT / "tools/map02_cd_read_probe.c"),
            str(ROOT / "tools/map02_capture_session.c"),
            "-o", str(cls.exe),
        ]
        built = subprocess.run(command, capture_output=True, text=True,
                               timeout=45)
        if built.returncode:
            raise AssertionError(built.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_mode(self, mode, *, frame="73", directory=None):
        env = dict(os.environ)
        env["VH_MAP02_PROBE_FRAME"] = frame
        if directory is not None:
            env["VH_MAP02_CYCLE_OUTPUT_DIR"] = str(directory)
        else:
            env.pop("VH_MAP02_CYCLE_OUTPUT_DIR", None)
        return subprocess.run([str(self.exe), mode], env=env,
                              capture_output=True, text=True, timeout=5)

    def test_ordered_receipt_is_bounded_and_explicit(self):
        proc = self.run_mode("good")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("failed=0 receipt=1", proc.stdout)
        self.assertIn('"gpu_draw_frame":73', proc.stdout)
        self.assertIn('"original_map02_rendering_proven":false', proc.stdout)

    def test_missing_or_invalid_target_frame_rejected(self):
        for value in ("", "0", "-73", "73junk", "4294967296", "72"):
            with self.subTest(value=value):
                proc = self.run_mode("good", frame=value)
                self.assertIn("receipt=0", proc.stdout)

    def test_fail_closed_for_out_of_order_or_duplicate(self):
        for mode in ("draw-early", "finish-first", "duplicate-claim",
                     "missing-completion", "duplicate-completion",
                     "broken-ot", "no-draw"):
            with self.subTest(mode=mode):
                proc = self.run_mode(mode)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("receipt=0", proc.stdout)

    def test_overflow_safe_extent_filter_for_unrelated_and_malformed_reads(self):
        unrelated = self.run_mode("overflow-unrelated-read")
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        self.assertIn("failed=0 receipt=1", unrelated.stdout)
        malformed = self.run_mode("overflow-overlapping-read")
        self.assertEqual(malformed.returncode, 0, malformed.stderr)
        self.assertIn("failed=1 receipt=0", malformed.stdout)

    def test_original_cd_crc_proof_is_mandatory_before_cycle_receipt(self):
        for mode in ("cd-missing-claim", "cd-duplicate-claim",
                     "cd-missing-read", "cd-missing-sector",
                     "cd-wrong-sector", "cd-tampered-transfer",
                     "cd-missing-completion", "cd-duplicate-completion"):
            with self.subTest(mode=mode):
                proc = self.run_mode(mode)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("failed=1 receipt=0", proc.stdout)

    def test_invalid_cd_state_never_publishes_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "private"
            out.mkdir(mode=0o700)
            proc = self.run_mode("cd-tampered-transfer", directory=out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("receipt=0", proc.stdout)
            self.assertIn("failed=1", proc.stdout)
            self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())

    def test_private_exclusive_receipt_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "receipts"
            out.mkdir(mode=0o700)
            file = out / "map02-single-process-cycle.jsonl"
            first = self.run_mode("good", directory=out)
            self.assertIn("failed=0 receipt=1", first.stdout)
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            previous = file.read_bytes()
            second = self.run_mode("good", directory=out)
            self.assertIn("failed=1 receipt=0", second.stdout)
            self.assertEqual(file.read_bytes(), previous)

    def test_non_private_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "public"
            out.mkdir(mode=0o755)
            proc = self.run_mode("good", directory=out)
            self.assertIn("failed=1 receipt=0", proc.stdout)
            self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())

    def test_symlink_output_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir(mode=0o700)
            link = Path(tmp) / "link"
            link.symlink_to(real, target_is_directory=True)
            proc = self.run_mode("good", directory=link)
            self.assertIn("failed=1 receipt=0", proc.stdout)
            self.assertFalse((real / "map02-single-process-cycle.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
