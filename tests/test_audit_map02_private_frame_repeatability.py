"""Real synthetic C11 two-launch native MAP02 GPU + BGR555 repeatability tests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_map02_joint_native_capture_c11 import PRODUCER
from tools.capture_map02_live_frame_pipe import capture
from tools import audit_map02_private_frame_repeatability as repeat


class NativeIndependentRunRepeatabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
            raise unittest.SkipTest("Linux procfs and C11 compiler required")
        cls.work = tempfile.TemporaryDirectory(prefix="vh-map02-two-run-c11-")
        root = Path(cls.work.name)
        source = root / "producer.c"
        cls.executable = root / "producer"
        # Same ELF, but an explicit test-only argument can change one
        # BGR555 word BEFORE the final after-VRAM journal snapshot.
        needle = "native_vram[0][0] = 0x7fff;\n        if (bad_vram)"
        replacement = ('native_vram[0][0] = 0x7fff;\n'
                       '        if (argc > 1 && !strcmp(argv[1], "alternate")) '
                       'native_vram[0][0] = 0x7ffe;\n'
                       '        if (bad_vram)')
        if PRODUCER.count(needle) != 1:
            raise RuntimeError("MAP02 C11 producer anchor drift")
        updated = PRODUCER.replace(needle, replacement)
        before = 'if (!write_image(dir, "gpu-0000-vram.bin")) return 43;'
        if updated.count(before) != 1:
            raise RuntimeError("MAP02 C11 before-snapshot anchor drift")
        updated = updated.replace(
            before,
            'if (argc > 1 && !strcmp(argv[1], "alternate-before")) '
            'native_vram[0][0] = 0x1234;\n        ' + before)
        source.write_text(updated, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise unittest.SkipTest("C11 compiler missing")
        subprocess.run([
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1", "-Itools",
            str(source), "tools/map02_native_frame_pipe.c",
            "-o", str(cls.executable),
        ], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-two-run-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.f1, self.j1, self.f2, self.j2 = (
            root / name for name in ("first-frame", "first-gpu",
                                    "second-frame", "second-gpu"))
        for folder in (self.f1, self.j1, self.f2, self.j2):
            folder.mkdir(mode=0o700)
        self.capture(self.f1, self.j1)
        self.capture(self.f2, self.j2)

    def capture(self, frame_dir, journal_dir, *args):
        return capture(self.executable, frame_dir, frame=123,
                       width=1024, height=512, executable_sha256=self.digest,
                       timeout=8, args=args, gpu_journal_dir=journal_dir)

    def run_repeat(self):
        return repeat.audit(self.f1, self.j1, self.f2, self.j2, self.executable)

    def test_two_independent_real_native_captures_are_bit_exact(self):
        result = self.run_repeat()
        self.assertTrue(result["repeated_native_frame_pixels_identical"])
        self.assertTrue(result["repeated_gpu_final_vram_identical"])
        self.assertTrue(result["repeated_gpu_event_journal_identical"])
        self.assertTrue(result["two_full_replays_per_capture_verified"])
        self.assertTrue(result["four_private_file_inventories_stable_through_replays"])
        self.assertTrue(result["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertEqual(result["first_gpu_vram_snapshot_count"], 2)
        self.assertEqual(result["second_gpu_vram_snapshot_count"], 2)
        self.assertEqual(result["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(result["different_gpu_vram_snapshots_in_common_prefix"], 0)
        self.assertIsNone(result["first_different_gpu_vram_snapshot_index"])
        self.assertEqual(result["different_bgr555_pixels"], 0)
        self.assertEqual(result["first_gpu_pairs_verified"], 1)
        self.assertFalse(result["ps1_hardware_pixel_equivalence_verified"])
        self.assertFalse(result["gpu_journal_writer_kernel_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        for folder in (self.f1, self.j1, self.f2, self.j2):
            self.assertNotIn(str(folder), json.dumps(result))

    def test_same_executable_can_produce_a_different_native_frame(self):
        for path in self.f2.iterdir():
            path.unlink()
        for path in self.j2.iterdir():
            path.unlink()
        self.capture(self.f2, self.j2, "alternate")
        out = self.run_repeat()
        self.assertFalse(out["repeated_native_frame_pixels_identical"])
        self.assertEqual(out["different_bgr555_pixels"], 1)
        self.assertEqual(out["changed_scanlines"], 1)
        self.assertEqual(out["stp_bit_differences"], 0)
        self.assertNotEqual(out["first_image_sha256"],
                            out["second_image_sha256"])
        self.assertFalse(out["repeated_gpu_final_vram_identical"])
        self.assertEqual(out["different_gpu_vram_snapshots_in_common_prefix"], 1)
        self.assertEqual(out["first_different_gpu_vram_snapshot_index"], 1)
        self.assertFalse(out["repeated_full_gpu_vram_snapshot_sequence_identical"])
        # Event JSONL captures draw order and attributes, but NOT raw
        # post-draw VRAM pixels. The same two events can write different
        # pixels while the JSONL digest stays byte-identical.
        self.assertTrue(out["repeated_gpu_event_journal_identical"])

    def test_transient_before_vram_difference_converges_to_same_final_frame(self):
        # The *same* compiled C11 ELF can create a different before-
        # DrawOTag snapshot and still produce an identical after-VRAM
        # frame and identical two-line JSONL GPU command journal.
        for folder in (self.f2, self.j2):
            for path in folder.iterdir():
                path.unlink()
        self.capture(self.f2, self.j2, "alternate-before")
        result = self.run_repeat()
        self.assertTrue(result["repeated_native_frame_pixels_identical"])
        self.assertTrue(result["repeated_gpu_final_vram_identical"])
        self.assertTrue(result["repeated_gpu_event_journal_identical"])
        self.assertFalse(result["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertEqual(result["different_bgr555_pixels"], 0)
        self.assertEqual(result["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(result["different_gpu_vram_snapshots_in_common_prefix"], 1)
        self.assertEqual(result["first_different_gpu_vram_snapshot_index"], 0)
        self.assertEqual(result["unmatched_gpu_vram_snapshots"], 0)

    def test_snapshot_comparator_accepts_distinct_pair_lengths_as_diagnostic(self):
        # Pure, asset-free bounds test. The actual journal/replay layers
        # separately authenticate each snapshot and event count.
        original_raw = repeat._private_raw
        actual = [b"\x00" * (1024 * 512 * 2),
                  b"\x01" * (1024 * 512 * 2)]
        def fake_read(fd, name):
            index = int(name[4:8])
            return actual[index % 2], ("synthetic", index)
        with patch.object(repeat, "_private_raw", side_effect=fake_read):
            with self.assertRaises(IndexError):
                # Only two known snapshots: keep synthetic mocks honest.
                fake_read(0, "gpu-0002-vram.bin")
            diagnostics = repeat._gpu_snapshot_differences(
                1, 2, 1, 2, lambda: None)
        self.assertEqual(diagnostics["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(diagnostics["unmatched_gpu_vram_snapshots"], 2)
        self.assertFalse(
            diagnostics["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertEqual(diagnostics["different_gpu_vram_snapshots_in_common_prefix"], 0)
        self.assertIsNone(diagnostics["first_different_gpu_vram_snapshot_index"])

    def test_overlapping_capture_roles_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "directory roles overlap"):
            repeat.audit(self.f1, self.j1, self.f1, self.j2, self.executable)

    def test_changing_one_native_image_is_detected_on_replay(self):
        with (self.f2 / "process-frame.bgr555").open("r+b") as file:
            file.seek(0)
            file.write(b"\x00\x00")
        with self.assertRaises(ValueError):
            self.run_repeat()

    def test_missing_native_gpu_journal_cannot_be_downgraded(self):
        (self.j2 / "gpu-native-events.jsonl").unlink()
        with self.assertRaises((OSError, ValueError)):
            self.run_repeat()

    def test_swap_same_byte_file_between_replays_refused(self):
        real = repeat.replay
        seen = []
        def swap(*args, **kwargs):
            receipt = real(*args, **kwargs)
            seen.append(1)
            if len(seen) == 1:
                target = self.f1 / "process-frame.bgr555"
                replacement = self.f1 / "replacement"
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, target)
            return receipt
        with patch.object(repeat, "replay", side_effect=swap):
            with self.assertRaises(ValueError):
                self.run_repeat()

    def test_same_byte_gpu_event_inode_swap_refused_even_if_hash_identical(self):
        real = repeat.replay
        seen = []
        def swap(*args, **kwargs):
            receipt = real(*args, **kwargs)
            seen.append(1)
            if len(seen) == 1:
                target = self.j1 / "gpu-native-events.jsonl"
                replacement = self.j1 / "replacement-events"
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, target)
            return receipt
        with patch.object(repeat, "replay", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "file identity changed"):
                self.run_repeat()

    def test_cli_report_contains_only_hashes_and_counts(self):
        proc = subprocess.run([
            sys.executable, "-m", "tools.audit_map02_private_frame_repeatability",
            "--first-frame", str(self.f1), "--first-journal", str(self.j1),
            "--second-frame", str(self.f2), "--second-journal", str(self.j2),
            "--executable", str(self.executable),
        ], text=True, capture_output=True, timeout=14)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["repeated_native_frame_pixels_identical"])
        self.assertNotIn(str(self.executable), proc.stdout)
        self.assertNotIn(str(self.f1), proc.stdout)

    def test_failure_does_not_leak_missing_private_path(self):
        secret = self.f1.parent / "private-missing-journal"
        proc = subprocess.run([
            sys.executable, "-m", "tools.audit_map02_private_frame_repeatability",
            "--first-frame", str(self.f1), "--first-journal", str(secret),
            "--second-frame", str(self.f2), "--second-journal", str(self.j2),
            "--executable", str(self.executable),
        ], text=True, capture_output=True, timeout=14)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("repeatability audit failed", proc.stderr)
        self.assertNotIn(str(secret), proc.stderr)


if __name__ == "__main__":
    unittest.main()
