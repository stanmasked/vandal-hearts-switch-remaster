"""Compile and run a synthetic native GPU-journal + terminal BGR555 producer.

Exercises the SAME pinned ELF launch for journal, final VRAM and live pipe.
No game data is used; the C producer simulates one observed primitive.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_map02_joint_gpu_frame as native_audit
from tools.capture_map02_live_frame_pipe import capture
from tools.replay_map02_live_frame_receipt import replay

PRODUCER = r'''
#define _POSIX_C_SOURCE 200809L
#include "map02_native_frame_pipe.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
static uint16_t native_vram[512][1024];

static int write_image(const char *dir, const char *name) {
    char path[2048];
    FILE *out;
    if (snprintf(path, sizeof(path), "%s/%s", dir, name) >= (int)sizeof(path))
        return 0;
    out = fopen(path, "wb");
    if (!out) return 0;
    if (fwrite(native_vram, 1, sizeof(native_vram), out) != sizeof(native_vram)) {
        fclose(out);
        return 0;
    }
    return fclose(out) == 0;
}
static int log_event(FILE *stream, unsigned step, const char *phase, unsigned frame) {
    return fprintf(stream,
       "{\"stage\":\"native_vram\",\"step\":%u,\"frame\":%u,"
       "\"phase\":\"%s\",\"operation\":\"draw\","
       "\"snapshot\":\"gpu-%04u-vram.bin\","
       "\"rect\":null,\"dest\":[0,0],\"rgb\":[0,0,0],"
       "\"primitive_type\":4,\"semi\":0,\"window\":[0,0,0,0],"
       "\"draw_mode\":[0,0,0],\"upload\":\"\",\"ft4\":null}\n",
       step, frame, phase, step) > 0;
}
int main(int argc, char **argv) {
    const char *dir = getenv("VH_MAP02_GPU_CAPTURE_DIR");
    const char *selected = getenv("VH_MAP02_PRIVATE_FRAME_PIPE_FRAME");
    const char *gpu_frame = getenv("VH_MAP02_GPU_CAPTURE_FRAME");
    char logfile[2048];
    FILE *events;
    int wrong_frame = argc > 1 && !strcmp(argv[1], "wrong-frame");
    int bad_vram = argc > 1 && !strcmp(argv[1], "bad-vram");
    int extra_file = argc > 1 && !strcmp(argv[1], "extra-file");
    int omit_journal = argc > 1 && !strcmp(argv[1], "no-journal");
    if (!dir || !selected || !gpu_frame ||
        strcmp(selected, "123") || strcmp(gpu_frame, selected))
        return 41;
    /* Require the launcher to hand us a pinned inherited directory FD,
     * not a mutable journal pathname or a caller-authored output route. */
    if (strncmp(dir, "/proc/self/fd/", 14) != 0) return 51;
    if (argc > 1 && !strcmp(argv[1], "swap-journal-path")) {
        char realpath[2048], parked[2300], redirect[2300];
        ssize_t n = readlink(dir, realpath, sizeof(realpath) - 1);
        if (n <= 0) return 52;
        realpath[n] = '\0';
        if (snprintf(parked, sizeof(parked), "%s-parked", realpath) >=
            (int)sizeof(parked) ||
            snprintf(redirect, sizeof(redirect), "%s-redirect", realpath) >=
            (int)sizeof(redirect)) return 53;
        if (rename(realpath, parked) || mkdir(redirect, 0700) ||
            symlink(redirect, realpath)) return 54;
    }
    if (!omit_journal) {
        if (!write_image(dir, "gpu-0000-vram.bin")) return 43;
        native_vram[0][0] = 0x7fff;
        if (bad_vram) native_vram[0][0] = 0;
        if (!write_image(dir, "gpu-0001-vram.bin")) return 44;
        if (bad_vram) native_vram[0][0] = 0x7fff;
        if (snprintf(logfile, sizeof(logfile), "%s/gpu-native-events.jsonl", dir) >=
                (int)sizeof(logfile)) return 45;
        events = fopen(logfile, "wb");
        if (!events) return 46;
        if (!log_event(events, 0, "before", wrong_frame ? 124 : 123) ||
            !log_event(events, 1, "after", wrong_frame ? 124 : 123) ||
            fflush(events) != 0) return 47;
        if (argc > 1 && !strcmp(argv[1], "closed-log")) {
            if (fclose(events) != 0) return 55;
        } else if (argc > 1 && !strcmp(argv[1], "readonly-log")) {
            if (fclose(events) != 0) return 56;
            events = fopen(logfile, "rb");
            if (!events) return 57;
        }

        if (extra_file) {
            if (snprintf(logfile, sizeof(logfile), "%s/unexpected.txt", dir) >=
                    (int)sizeof(logfile)) return 48;
            events = fopen(logfile, "wb");
            if (!events || fclose(events) != 0) return 49;
        }
    } else {
        native_vram[0][0] = 0x7fff;
    }
    if (vh_map02_frame_pipe_wait_release(STDIN_FILENO) != 0) return 42;
    if (argc > 1 && !strcmp(argv[1], "replace-log-after-release")) {
        char original[2048], backup[2300];
        unsigned char piece[4096];
        size_t got;
        FILE *reader, *writer;
        if (snprintf(original, sizeof(original), "%s/gpu-native-events.jsonl",
                     dir) >= (int)sizeof(original) ||
            snprintf(backup, sizeof(backup), "%s/swapped-log", dir) >=
                    (int)sizeof(backup)) return 58;
        if (rename(original, backup) != 0) return 59;
        reader = fopen(backup, "rb");
        writer = fopen(original, "wb");
        if (!reader || !writer) return 60;
        while ((got = fread(piece, 1, sizeof(piece), reader)) != 0) {
            if (fwrite(piece, 1, got, writer) != got) return 61;
        }
        if (ferror(reader) || fclose(reader) || fclose(writer) ||
            unlink(backup) != 0) return 62;
        /* Same JSONL bytes, but a DIFFERENT inode than the one the
         * pinned child held open when the launcher released stdout. */
    }
    return vh_map02_frame_pipe_emit(STDOUT_FILENO, 123, 1024, 512,
                                    &native_vram[0][0], 1024) == 0 ? 0 : 50;
}
'''


class JointNativeCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-joint-c11-")
        root = Path(cls.workspace.name)
        cls.executable = root / "producer"
        src = root / "producer.c"
        src.write_text(PRODUCER, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise RuntimeError("selected C compiler missing")
        subprocess.run(
            [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1", "-Itools",
             str(src), "tools/map02_native_frame_pipe.c",
             "-o", str(cls.executable)], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-joint-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out = root / "output"
        self.journal = root / "journal"
        self.out.mkdir(mode=0o700)
        self.journal.mkdir(mode=0o700)

    def run_joint(self, *args, **kwargs):
        return capture(self.executable, self.out,
                       frame=123, width=1024, height=512,
                       executable_sha256=self.digest, timeout=kwargs.get("timeout", 8), args=args,
                       gpu_journal_dir=kwargs.get("journal_dir", self.journal))

    def assert_no_published_frame(self):
        self.assertEqual(list(self.out.iterdir()), [])

    def test_full_frame_matches_last_same_launch_native_gpu_after_event(self):
        result = self.run_joint()
        self.assertEqual(result["schema"], "vh.map02.live-child-pipe-bgr555-gpu.v1")
        self.assertTrue(result["terminal_after_vram_matched"])
        self.assertTrue(result["gpu_journal_same_elf_launch_requested"])
        self.assertTrue(result["child_writable_gpu_journal_fd_observed"])
        self.assertFalse(result["gpu_journal_writer_kernel_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        self.assertEqual(result["gpu_journal_pairs_verified"], 1)
        self.assertEqual(len((self.out / "process-frame.bgr555").read_bytes()),
                         1024 * 512 * 2)
        verified = replay(self.out, executable=self.executable,
                          gpu_journal_dir=self.journal)
        self.assertTrue(verified["gpu_terminal_frame_equal"])
        self.assertTrue(verified["child_writable_gpu_journal_fd_observed"])
        self.assertEqual(verified["terminal_gpu_after_vram_sha256"],
                         result["image_sha256"])
        self.assertFalse(verified["gpu_journal_writer_kernel_authenticated"])
        self.assertNotIn(str(self.journal), str(result))

    def test_joint_producer_receives_inherited_directory_fd(self):
        # The C test executable rejects any journal destination other than
        # /proc/self/fd/N, so a successful full capture tests pass_fds and
        # resolution of writes through the pinned directory inode.
        receipt = self.run_joint()
        self.assertTrue(receipt["terminal_after_vram_matched"])
        self.assertTrue((self.journal / "gpu-native-events.jsonl").is_file())

    def test_mutable_journal_path_swap_never_redirects_native_writes(self):
        # The ELF renames the directory and substitutes a symlink after
        # launch. Writes via /proc/self/fd/N remain in the original inode.
        # The parent refuses publication when its original pathname
        # ceases to resolve to the held journal directory.
        with self.assertRaises(OSError):
            self.run_joint("swap-journal-path")
        self.assert_no_published_frame()
        parked = self.journal.with_name(self.journal.name + "-parked")
        redirect = self.journal.with_name(self.journal.name + "-redirect")
        self.assertTrue((parked / "gpu-native-events.jsonl").is_file())
        self.assertEqual(list(redirect.iterdir()), [])
        self.assertTrue(self.journal.is_symlink())

    def test_wrong_event_frame_refused(self):
        with self.assertRaisesRegex(ValueError, "frame"):
            self.run_joint("wrong-frame")
        self.assert_no_published_frame()

    def test_terminal_image_not_equal_gpu_after_snapshot_refused(self):
        with self.assertRaisesRegex(ValueError, "differs from last journaled"):
            self.run_joint("bad-vram")
        self.assert_no_published_frame()

    def test_unexpected_journal_file_refused(self):
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.run_joint("extra-file")
        self.assert_no_published_frame()

    def test_missing_native_gpu_journal_refused(self):
        with self.assertRaisesRegex(ValueError, "timed out observing writable"):
            self.run_joint("no-journal", timeout=0.5)
        self.assert_no_published_frame()

    def test_closed_child_gpu_journal_fd_refused_before_release(self):
        with self.assertRaisesRegex(ValueError, "timed out observing writable"):
            self.run_joint("closed-log", timeout=0.5)
        self.assert_no_published_frame()

    def test_readonly_child_gpu_journal_fd_refused_before_release(self):
        with self.assertRaisesRegex(ValueError, "timed out observing writable"):
            self.run_joint("readonly-log", timeout=0.5)
        self.assert_no_published_frame()

    def test_kernel_child_writable_fd_receipt_flag_cannot_be_forged(self):
        self.run_joint()
        import json
        meta = self.out / "process-frame.json"
        data = json.loads(meta.read_text(encoding="utf-8"))
        data["child_writable_gpu_journal_fd_observed"] = False
        meta.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evidence flags"):
            replay(self.out, executable=self.executable,
                   gpu_journal_dir=self.journal)

    def test_same_bytes_new_gpu_journal_inode_after_child_gate_refused(self):
        # The child held the real write fd at gate release, then replaces
        # the journal pathname with another inode containing identical
        # JSONL bytes. Hash-only replay would miss this substitution.
        with self.assertRaisesRegex(ValueError, "inode changed after child fd observation"):
            self.run_joint("replace-log-after-release")
        self.assert_no_published_frame()
        self.assertTrue((self.journal / "gpu-native-events.jsonl").is_file())
        self.assertFalse((self.journal / "swapped-log").exists())

    def test_replay_requires_the_journal_for_v2_receipt(self):
        self.run_joint()
        with self.assertRaisesRegex(ValueError, "requires exactly one"):
            replay(self.out, executable=self.executable)

    def test_altered_journal_rejected_by_replay(self):
        self.run_joint()
        path = self.journal / "gpu-0001-vram.bin"
        with path.open("r+b") as stream:
            stream.write(b"\x12\x34")
        with self.assertRaises(ValueError):
            replay(self.out, executable=self.executable,
                   gpu_journal_dir=self.journal)

    def test_insecure_journal_dir_refused_before_child(self):
        self.journal.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.run_joint()
        self.assert_no_published_frame()

    def test_nonempty_journal_refused_before_child(self):
        (self.journal / "old").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_joint()
        self.assert_no_published_frame()

    def test_world_readable_native_journal_snapshot_rejected(self):
        # A private journal that leaked permissions must never publish
        # a successful frame/receipt, even if its bytes match.
        # First produce a valid journal; reject at independent replay.
        self.run_joint()
        image = self.journal / "gpu-0001-vram.bin"
        image.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode"):
            replay(self.out, executable=self.executable,
                   gpu_journal_dir=self.journal)

    def test_native_journal_hardlink_refused(self):
        self.run_joint()
        target = self.journal / "gpu-0001-vram.bin"
        alias = self.journal.parent / "outside-linked-vram.bin"
        os.link(target, alias)
        with self.assertRaisesRegex(ValueError, "mode"):
            replay(self.out, executable=self.executable,
                   gpu_journal_dir=self.journal)

    def test_symlinked_native_journal_file_refused(self):
        self.run_joint()
        original = self.journal / "gpu-0001-vram.bin"
        destination = self.journal.parent / "moved-vram.bin"
        original.rename(destination)
        original.symlink_to(destination)
        with self.assertRaises(OSError):
            replay(self.out, executable=self.executable,
                   gpu_journal_dir=self.journal)

    def test_same_bytes_different_inode_during_gpu_replay_rejected(self):
        original_verify = native_audit.verify_capture
        calls = [0]
        def swap_after_first(*a, **kw):
            result = original_verify(*a, **kw)
            calls[0] += 1
            if calls[0] == 1:
                target = self.journal / "gpu-0000-vram.bin"
                other = self.journal / "replacement.bin"
                other.write_bytes(target.read_bytes())
                other.chmod(0o600)
                other.replace(target)
            return result
        with patch.object(native_audit, "verify_capture",
                          side_effect=swap_after_first):
            with self.assertRaisesRegex(ValueError, "files/directory changed"):
                self.run_joint()
        self.assertEqual(calls[0], 2)
        self.assert_no_published_frame()

    def test_joint_mode_wrong_geometry_refused(self):
        with self.assertRaisesRegex(ValueError, "full native VRAM"):
            capture(self.executable, self.out, frame=123, width=2, height=2,
                    executable_sha256=self.digest,
                    gpu_journal_dir=self.journal)
        self.assert_no_published_frame()


if __name__ == "__main__":
    unittest.main()
