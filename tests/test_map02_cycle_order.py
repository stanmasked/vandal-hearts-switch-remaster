"""Asset-free adversarial tests of the in-process MAP02 cycle state machine.

The harness emits calls itself: these tests do NOT execute original game
LoadCdFile / ContinueLoadingCdFile / DrawOTag, nor prove a MAP02 render.
"""
import os
import zlib
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

# Synthetic LD_PRELOAD fault injection. Never touches the user's game.
FAULT_SHIM = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int fsync(int fd) {
    typedef int (*fsync_fn)(int);
    static fsync_fn original;
    static int injected;
    struct stat st;
    const char *fault = getenv("VH_MAP02_TEST_FAULT");
    const char *root = getenv("VH_MAP02_CYCLE_OUTPUT_DIR");
    if (!original) original = (fsync_fn)dlsym(RTLD_NEXT, "fsync");
    if (!injected && fault && root && !strcmp(fault, "late-flip") &&
        fstat(fd, &st) == 0 && S_ISDIR(st.st_mode)) {
        int target = openat(fd, "map02-single-process-cycle.jsonl",
                            O_RDWR | O_NOFOLLOW);
        if (target >= 0) {
            injected = 1;
            if (pwrite(target, "?", 1, 1) != 1) return -1;
            close(target);
        }
    }
    if (!injected && fault && root &&
        (!strcmp(fault, "flip") || !strcmp(fault, "replace") ||
         !strcmp(fault, "replace-identical")) &&
        fstat(fd, &st) == 0 &&
        S_ISREG(st.st_mode) && st.st_size > 100) {
        injected = 1;
        if (!strcmp(fault, "flip")) {
            if (pwrite(fd, "!", 1, 0) != 1) return -1;
        } else if (!strcmp(fault, "replace") ||
                   !strcmp(fault, "replace-identical")) {
            int dir = open(root, O_RDONLY | O_DIRECTORY);
            int other = -1;
            if (dir < 0) return -1;
            other = openat(dir, "replacement-temp", O_CREAT | O_EXCL |
                           O_RDWR, 0600);
            if (other < 0) { close(dir); return -1; }
            if (!strcmp(fault, "replace")) {
                const char *foreign = "foreign-file-do-not-delete";
                if (write(other, foreign, strlen(foreign)) !=
                    (ssize_t)strlen(foreign)) return -1;
            } else {
                char buffer[512];
                ssize_t count = pread(fd, buffer, sizeof buffer, 0);
                if (count <= 0 || write(other, buffer, (size_t)count) != count)
                    return -1;
            }
            if (close(other) || renameat(dir, "replacement-temp", dir,
                        "map02-single-process-cycle.jsonl"))
                return -1;
            close(dir);
        }
    }
    return original(fd);
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
        shim = root / "fault.c"
        shim.write_text(FAULT_SHIM, encoding="utf-8")
        cls.fault_library = root / "libmap02_fault.so"
        shared = subprocess.run(
            ["cc", "-std=gnu99", "-Wall", "-Wextra", "-Werror",
             "-fPIC", "-shared", str(shim), "-ldl",
             "-o", str(cls.fault_library)],
            capture_output=True, text=True, timeout=45)
        if shared.returncode:
            raise AssertionError(shared.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_mode(self, mode, *, frame="73", directory=None, fault=None):
        env = dict(os.environ)
        env["VH_MAP02_PROBE_FRAME"] = frame
        if directory is not None:
            env["VH_MAP02_CYCLE_OUTPUT_DIR"] = str(directory)
        else:
            env.pop("VH_MAP02_CYCLE_OUTPUT_DIR", None)
        env.pop("VH_MAP02_TEST_FAULT", None)
        if fault is not None:
            env["VH_MAP02_TEST_FAULT"] = fault
            env["LD_PRELOAD"] = str(self.fault_library)
        return subprocess.run([str(self.exe), mode], env=env,
                              capture_output=True, text=True, timeout=5)

    def test_ordered_receipt_is_bounded_and_explicit(self):
        proc = self.run_mode("good")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("failed=0 receipt=1", proc.stdout)
        self.assertIn('"gpu_draw_frame":73', proc.stdout)
        self.assertIn('"schema":"vh.map02.cycle-order.v2"', proc.stdout)
        expected_sector_data = bytes((i ^ (i >> 8)) & 255
                                     for i in range(12 * 2048))
        expected_crc = zlib.crc32(expected_sector_data)
        self.assertIn('"original_cd_raw_user_crc32":"%08x"' % expected_crc,
                      proc.stdout)
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

    def test_in_place_flip_after_file_fsync_rejects_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "receipts"
            root.mkdir(mode=0o700)
            outcome = self.run_mode("good", directory=root, fault="flip")
            self.assertEqual(outcome.returncode, 0, outcome.stderr)
            self.assertIn("failed=1 receipt=0", outcome.stdout)
            self.assertFalse((root / "map02-single-process-cycle.jsonl").exists())

    def test_second_read_rejects_edit_during_directory_fsync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "receipts"
            root.mkdir(mode=0o700)
            result = self.run_mode("good", directory=root, fault="late-flip")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("failed=1 receipt=0", result.stdout)
            self.assertFalse((root / "map02-single-process-cycle.jsonl").exists())

    def test_replaced_name_is_not_unlinked_on_failure(self):
        for fault in ("replace", "replace-identical"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "receipts"
                root.mkdir(mode=0o700)
                outcome = self.run_mode("good", directory=root, fault=fault)
                self.assertEqual(outcome.returncode, 0, outcome.stderr)
                self.assertIn("failed=1 receipt=0", outcome.stdout)
                swapped = root / "map02-single-process-cycle.jsonl"
                self.assertTrue(swapped.is_file(), "foreign inode was unlinked")
                if fault == "replace":
                    self.assertEqual(swapped.read_bytes(),
                                     b"foreign-file-do-not-delete")
                else:
                    self.assertIn(b"ordered_source_hooks_observed", swapped.read_bytes())

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
