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
#include "map02_native_frame_pipe.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
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
    if (vh_map02_frame_pipe_wait_release(STDIN_FILENO) != 0) return 42;
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
            fclose(events) != 0) return 47;
        if (extra_file) {
            if (snprintf(logfile, sizeof(logfile), "%s/unexpected.txt", dir) >=
                    (int)sizeof(logfile)) return 48;
            events = fopen(logfile, "wb");
            if (!events || fclose(events) != 0) return 49;
        }
    } else {
        native_vram[0][0] = 0x7fff;
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
                       executable_sha256=self.digest, timeout=8, args=args,
                       gpu_journal_dir=kwargs.get("journal_dir", self.journal))

    def assert_no_published_frame(self):
        self.assertEqual(list(self.out.iterdir()), [])

    def test_full_frame_matches_last_same_launch_native_gpu_after_event(self):
        result = self.run_joint()
        self.assertEqual(result["schema"], "vh.map02.live-child-pipe-bgr555-gpu.v1")
        self.assertTrue(result["terminal_after_vram_matched"])
        self.assertTrue(result["gpu_journal_same_elf_launch_requested"])
        self.assertFalse(result["gpu_journal_writer_kernel_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        self.assertEqual(result["gpu_journal_pairs_verified"], 1)
        self.assertEqual(len((self.out / "process-frame.bgr555").read_bytes()),
                         1024 * 512 * 2)
        verified = replay(self.out, executable=self.executable,
                          gpu_journal_dir=self.journal)
        self.assertTrue(verified["gpu_terminal_frame_equal"])
        self.assertEqual(verified["terminal_gpu_after_vram_sha256"],
                         result["image_sha256"])
        self.assertFalse(verified["gpu_journal_writer_kernel_authenticated"])
        self.assertNotIn(str(self.journal), str(result))

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
        with self.assertRaisesRegex(ValueError, "missing"):
            self.run_joint("no-journal")
        self.assert_no_published_frame()

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
