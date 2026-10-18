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
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

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

    if (!strcmp(argv[1], "cd-premature-sector"))
        vh_map02_cd_read_sector(0x1bcc, sectors);
    if (!strcmp(argv[1], "cd-orphan-finish"))
        vh_map02_cd_read_finish(0x1bcc, 12, returned);
    if (!strcmp(argv[1], "cd-unrelated-before-and-after")) {
        vh_map02_cd_read_sector(0x1bcb, sectors);
        vh_map02_cd_read_finish(0x1bca, 1, returned);
    }
    if (strcmp(argv[1], "cd-missing-read"))
        vh_map02_cd_read_start(0x1bcc, 12);
    if (strcmp(argv[1], "finish-first"))
        vh_map02_cycle_read_start(0x1bcc, 12);
    if (strcmp(argv[1], "cd-missing-read")) {
        for (i = 0; i < 12; ++i) {
            if ((!strcmp(argv[1], "cd-missing-sector") ||
                 !strcmp(argv[1], "cd-short-buffer-pointer")) && i == 11)
                continue;
            vh_map02_cd_read_sector(
                0x1bcc + i + (!strcmp(argv[1], "cd-wrong-sector") && i == 5),
                sectors + (size_t)i * 2048u);
        }
        if (!strcmp(argv[1], "cd-tampered-transfer"))
            returned[0] ^= 1u;
        if (!strcmp(argv[1], "cd-short-buffer-pointer"))
            vh_map02_cd_read_finish(0x1bcc, 12, (const unsigned char *)1);
        else if (!strcmp(argv[1], "cd-wrong-length-pointer"))
            vh_map02_cd_read_finish(0x1bcc, 11, (const unsigned char *)1);
        else if (!strcmp(argv[1], "cd-wrong-lba-pointer"))
            vh_map02_cd_read_finish(0x1bcd, 12, (const unsigned char *)1);
        else if (!strcmp(argv[1], "cd-null-transfer"))
            vh_map02_cd_read_finish(0x1bcc, 12, NULL);
        else
            vh_map02_cd_read_finish(0x1bcc, 12, returned);
    }
    if (!strcmp(argv[1], "cd-delayed-sector"))
        vh_map02_cd_read_sector(0x1bcc + 7, sectors + 7u * 2048u);
    if (!strcmp(argv[1], "cd-duplicate-finish"))
        vh_map02_cd_read_finish(0x1bcc, 12, returned);
    if (!strcmp(argv[1], "cd-unrelated-before-and-after")) {
        vh_map02_cd_read_sector(0x1bcb, sectors);
        vh_map02_cd_read_finish(0x1bca, 1, returned);
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
    /* The chosen DrawOTag has now returned and its provisional receipt
     * exists. _exit(0) deliberately skips normal-exit seal creation. */
    if (!strcmp(argv[1], "abrupt-zero-exit"))
        _exit(0);
    /* Exercise a fault later in the SAME original process. */
    if (!strcmp(argv[1], "post-publish-cd-duplicate-claim"))
        vh_map02_cd_loader_claim(42, 42, 0x1bcc, 12);
    if (!strcmp(argv[1], "post-publish-cd-sector") ||
        !strcmp(argv[1], "post-publish-replace"))
        vh_map02_cd_read_sector(0x1bcc, sectors);
    if (!strcmp(argv[1], "post-publish-cycle-extra-load"))
        vh_map02_cycle_load(42, 42, 0x1bcc, 12);
    if (!strcmp(argv[1], "post-publish-cycle-extra-draw"))
        vh_map02_cycle_draw_finish(73, 1);
    if (!strcmp(argv[1], "post-publish-unrelated-cd")) {
        vh_map02_cd_read_sector(0x1bcb, sectors);
        vh_map02_cd_read_finish(0x1bca, 1, returned);
    }
    if (!strcmp(argv[1], "post-publish-dir-replace") ||
        !strcmp(argv[1], "post-publish-dir-symlink")) {
        const char *root = getenv("VH_MAP02_CYCLE_OUTPUT_DIR");
        char moved[4096];
        int length;
        if (!root) return 14;
        length = snprintf(moved, sizeof moved, "%s.moved", root);
        if (length <= 0 || (size_t)length >= sizeof moved) return 15;
        if (rename(root, moved)) return 16;
        if (!strcmp(argv[1], "post-publish-dir-replace")) {
            if (mkdir(root, 0700)) return 17;
        } else {
            if (symlink(moved, root)) return 18;
        }
    }
    if (!strcmp(argv[1], "post-publish-replace")) {
        const char *root = getenv("VH_MAP02_CYCLE_OUTPUT_DIR");
        int dir, replacement;
        if (!root) return 8;
        dir = open(root, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
        if (dir < 0) return 9;
        if (renameat(dir, "map02-single-process-cycle.jsonl",
                     dir, "prior-original-receipt") != 0) return 10;
        replacement = openat(dir, "map02-single-process-cycle.jsonl",
                             O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (replacement < 0) return 11;
        if (write(replacement, "foreign-not-to-delete", 21) != 21) return 12;
        if (close(replacement) != 0 || close(dir) != 0) return 13;
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
#include <errno.h>
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
    static int receipt_file_syncs, output_dir_syncs;
    struct stat st;
    const char *fault = getenv("VH_MAP02_TEST_FAULT");
    const char *root = getenv("VH_MAP02_CYCLE_OUTPUT_DIR");
    if (!original) original = (fsync_fn)dlsym(RTLD_NEXT, "fsync");
    /* Failures DURING clean-exit sealing must never leave a believable
     * receipt+seal pair. Count only MAP02 fixture fsyncs; no retail data. */
    if (!injected && fault && root &&
        !strncmp(fault, "seal-", 5) && fstat(fd, &st) == 0) {
        int trigger = 0;
        if (S_ISREG(st.st_mode) && st.st_size > 100)
            trigger = (++receipt_file_syncs == 2 &&
                       (!strcmp(fault, "seal-fsync-error") ||
                        !strcmp(fault, "seal-flip") ||
                        !strcmp(fault, "seal-replace-identical") ||
                        !strcmp(fault, "seal-mode") ||
                        !strcmp(fault, "seal-link")));
        if (S_ISDIR(st.st_mode))
            trigger = (++output_dir_syncs == 2 &&
                       (!strcmp(fault, "seal-dir-error") ||
                        !strcmp(fault, "seal-dir-flip") ||
                        !strcmp(fault, "seal-dir-replace-identical") ||
                        !strcmp(fault, "seal-dir-mode") ||
                        !strcmp(fault, "seal-dir-link")));
        if (trigger) {
            injected = 1;
            if (!strcmp(fault, "seal-fsync-error") ||
                !strcmp(fault, "seal-dir-error")) {
                errno = EIO;
                return -1;
            }
            {
                int dfd = open(root, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
                int seal = -1;
                if (dfd < 0) return -1;
                seal = openat(dfd, "map02-cycle-clean-exit.jsonl",
                              O_RDONLY | O_NOFOLLOW);
                if (seal < 0) { close(dfd); return -1; }
                if (!strcmp(fault, "seal-mode")) {
                    if (fchmod(seal, 0644)) return -1;
                } else if (!strcmp(fault, "seal-dir-mode")) {
                    if (fchmod(dfd, 0755)) return -1;
                } else if (!strcmp(fault, "seal-link") ||
                           !strcmp(fault, "seal-dir-link")) {
                    if (linkat(dfd, "map02-cycle-clean-exit.jsonl",
                               dfd, "seal-hardlink-alias", 0)) return -1;
                } else if (!strcmp(fault, "seal-flip") ||
                    !strcmp(fault, "seal-dir-flip")) {
                    int modify = openat(dfd, "map02-cycle-clean-exit.jsonl",
                                        O_RDWR | O_NOFOLLOW);
                    if (modify < 0 || pwrite(modify, "!", 1, 0) != 1)
                        return -1;
                    close(modify);
                } else {
                    char buf[512];
                    ssize_t n = pread(seal, buf, sizeof buf, 0);
                    int tmp = openat(dfd, "seal-foreign-temp",
                                     O_WRONLY | O_CREAT | O_EXCL |
                                     O_NOFOLLOW, 0600);
                    if (n <= 0 || tmp < 0 || write(tmp, buf, (size_t)n) != n)
                        return -1;
                    if (close(tmp) ||
                        renameat(dfd, "seal-foreign-temp", dfd,
                                 "map02-cycle-clean-exit.jsonl"))
                        return -1;
                }
                close(seal);
                close(dfd);
            }
        }
    }
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
                     "cd-missing-completion", "cd-duplicate-completion",
                     "cd-premature-sector", "cd-orphan-finish",
                     "cd-delayed-sector", "cd-duplicate-finish",
                     "cd-short-buffer-pointer", "cd-wrong-length-pointer",
                     "cd-wrong-lba-pointer", "cd-null-transfer"):
            with self.subTest(mode=mode):
                proc = self.run_mode(mode)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("failed=1 receipt=0", proc.stdout)

    def test_malformed_cd_finish_does_not_dereference_invalid_buffer(self):
        # Deliberately inaccessible pointers: a malformed original CdRead
        # transfer must fail before the observer scans 12 * 2048 bytes.
        for mode in ("cd-short-buffer-pointer", "cd-wrong-length-pointer",
                     "cd-wrong-lba-pointer"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                proc = self.run_mode(mode, directory=out)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("failed=1 receipt=0", proc.stdout)
                self.assertFalse(
                    (out / "map02-single-process-cycle.jsonl").exists())

    def test_unrelated_cd_callbacks_outside_map02_read_are_ignored(self):
        proc = self.run_mode("cd-unrelated-before-and-after")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("failed=0 receipt=1", proc.stdout)
        self.assertIn('"original_cd_raw_user_crc32":', proc.stdout)

    def test_late_or_duplicate_map02_callbacks_never_publish(self):
        for mode in ("cd-premature-sector", "cd-orphan-finish",
                     "cd-delayed-sector", "cd-duplicate-finish"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                proc = self.run_mode(mode, directory=out)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("failed=1 receipt=0", proc.stdout)
                self.assertFalse(
                    (out / "map02-single-process-cycle.jsonl").exists())

    def test_invalid_cd_state_never_publishes_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "private"
            out.mkdir(mode=0o700)
            proc = self.run_mode("cd-tampered-transfer", directory=out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("receipt=0", proc.stdout)
            self.assertIn("failed=1", proc.stdout)
            self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())

    def test_late_source_fault_after_draw_retracts_published_receipt_on_exit(self):
        for mode in ("post-publish-cd-duplicate-claim",
                     "post-publish-cd-sector",
                     "post-publish-cycle-extra-load",
                     "post-publish-cycle-extra-draw"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                proc = self.run_mode(mode, directory=out)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("failed=1 receipt=0", proc.stdout)
                self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())

    def test_late_unrelated_cd_activity_preserves_completed_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "private"
            out.mkdir(mode=0o700)
            proc = self.run_mode("post-publish-unrelated-cd", directory=out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("failed=0 receipt=1", proc.stdout)
            self.assertTrue((out / "map02-single-process-cycle.jsonl").exists())

    def test_late_revocation_must_not_delete_replaced_foreign_inode(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "private"
            out.mkdir(mode=0o700)
            proc = self.run_mode("post-publish-replace", directory=out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("failed=1 receipt=0", proc.stdout)
            current = out / "map02-single-process-cycle.jsonl"
            original = out / "prior-original-receipt"
            self.assertEqual(current.read_bytes(), b"foreign-not-to-delete")
            self.assertIn(b"cycle-order.v2", original.read_bytes())
            self.assertNotEqual(current.stat().st_ino, original.stat().st_ino)

    def test_normal_exit_refuses_renamed_or_symlinked_output_directory(self):
        for mode in ("post-publish-dir-replace",
                     "post-publish-dir-symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                moved = Path(tmp) / "private.moved"
                out.mkdir(mode=0o700)
                result = self.run_mode(mode, directory=out)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("failed=0 receipt=1", result.stdout)
                self.assertTrue(moved.is_dir())
                self.assertFalse(
                    (moved / "map02-single-process-cycle.jsonl").exists())
                self.assertFalse(
                    (moved / "map02-cycle-clean-exit.jsonl").exists())
                if mode == "post-publish-dir-replace":
                    self.assertTrue(out.is_dir())
                    self.assertEqual(list(out.iterdir()), [])
                else:
                    self.assertTrue(out.is_symlink())
                self.assertFalse(
                    (out / "map02-cycle-clean-exit.jsonl").exists())

    def test_clean_exit_requires_distinct_matching_private_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "private"
            folder.mkdir(mode=0o700)
            outcome = self.run_mode("good", directory=folder)
            self.assertEqual(outcome.returncode, 0, outcome.stderr)
            receipt = folder / "map02-single-process-cycle.jsonl"
            seal = folder / "map02-cycle-clean-exit.jsonl"
            self.assertEqual(receipt.read_bytes(), seal.read_bytes())
            self.assertNotEqual(receipt.stat().st_ino, seal.stat().st_ino)
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertEqual(seal.stat().st_mode & 0o777, 0o600)
            self.assertEqual(set(p.name for p in folder.iterdir()),
                             {receipt.name, seal.name})

    def test_abrupt_zero_exit_leaves_unsealed_cycle_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "private"
            folder.mkdir(mode=0o700)
            outcome = self.run_mode("abrupt-zero-exit", directory=folder)
            self.assertEqual(outcome.returncode, 0, outcome.stderr)
            self.assertTrue(
                (folder / "map02-single-process-cycle.jsonl").is_file())
            self.assertFalse(
                (folder / "map02-cycle-clean-exit.jsonl").exists())

    def test_clean_exit_seal_rejects_mode_change_during_file_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "private"
            out.mkdir(mode=0o700)
            result = self.run_mode("good", directory=out, fault="seal-mode")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())
            self.assertFalse((out / "map02-cycle-clean-exit.jsonl").exists())
            self.assertEqual(list(out.iterdir()), [])

    def test_clean_exit_seal_rejects_mode_change_during_dir_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "private"
            out.mkdir(mode=0o700)
            result = self.run_mode("good", directory=out, fault="seal-dir-mode")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(out.stat().st_mode & 0o777, 0o755)
            self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())
            self.assertFalse((out / "map02-cycle-clean-exit.jsonl").exists())

    def test_clean_exit_seal_rejects_hardlinks_during_sync(self):
        for fault in ("seal-link", "seal-dir-link"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                result = self.run_mode("good", directory=out, fault=fault)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())
                self.assertFalse((out / "map02-cycle-clean-exit.jsonl").exists())
                alias = out / "seal-hardlink-alias"
                self.assertTrue(alias.is_file())
                self.assertIn(b"vh.map02.cycle-order.v2", alias.read_bytes())
                self.assertEqual(alias.stat().st_nlink, 1)

    def test_clean_exit_fsync_failure_revokes_both_private_receipts(self):
        for fault in ("seal-fsync-error", "seal-dir-error"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                result = self.run_mode("good", directory=out, fault=fault)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())
                self.assertFalse((out / "map02-cycle-clean-exit.jsonl").exists())
                self.assertEqual(list(out.iterdir()), [])

    def test_clean_exit_seal_byte_corruption_revokes_both_receipts(self):
        for fault in ("seal-flip", "seal-dir-flip"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                result = self.run_mode("good", directory=out, fault=fault)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())
                self.assertFalse((out / "map02-cycle-clean-exit.jsonl").exists())

    def test_clean_exit_refuses_identical_foreign_seal_inode_without_unlink(self):
        for fault in ("seal-replace-identical",
                      "seal-dir-replace-identical"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "private"
                out.mkdir(mode=0o700)
                result = self.run_mode("good", directory=out, fault=fault)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((out / "map02-single-process-cycle.jsonl").exists())
                seal = out / "map02-cycle-clean-exit.jsonl"
                self.assertTrue(seal.is_file(), "foreign seal inode was deleted")
                self.assertIn(b"vh.map02.cycle-order.v2", seal.read_bytes())

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
