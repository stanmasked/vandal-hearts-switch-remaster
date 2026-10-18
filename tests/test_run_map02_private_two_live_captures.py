"""Actual synthetic C11 two-launch ELF -> GPU/BGR555 -> audit integration tests."""
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
from tools.capture_map02_live_frame_pipe import capture as original_capture
from tools import run_map02_private_two_live_captures as two_live


class TwoLiveElfPrivateAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
            raise unittest.SkipTest("Linux procfs required")
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-live-twice-")
        folder = Path(cls.workspace.name)
        source = folder / "producer.c"
        cls.executable = folder / "synthetic-elf"
        # Keep the baseline fixture unchanged by default. One optional
        # test-only argv can alter an after-VRAM pixel while preserving
        # the pinned ELF hash and a fully valid native GPU journal.
        needle = 'native_vram[0][0] = 0x7fff;\n        if (bad_vram)'
        replacement = ('native_vram[0][0] = 0x7fff;\n'
                       '        if (argc > 1 && !strcmp(argv[1], "alternate")) '
                       'native_vram[0][0] = 0x7ffe;\n'
                       '        if (bad_vram)')
        if PRODUCER.count(needle) != 1:
            raise RuntimeError("MAP02 synthetic GPU C11 fixture anchor drift")
        source.write_text(PRODUCER.replace(needle, replacement), encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise unittest.SkipTest("C compiler missing")
        subprocess.run([
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1", "-Itools",
            str(source), "tools/map02_native_frame_pipe.c",
            "-o", str(cls.executable),
        ], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-local-twice-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.dirs = [root / name for name in (
            "frame-1", "journal-1", "frame-2", "journal-2")]
        for folder in self.dirs:
            folder.mkdir(mode=0o700)

    def run_two(self, **kwargs):
        return two_live.run(
            self.executable, *self.dirs, frame=kwargs.pop("frame", 123),
            executable_sha256=kwargs.pop("sha", self.digest),
            timeout=kwargs.pop("timeout", 8), **kwargs)

    def test_two_real_linux_elf_launches_produce_exact_match(self):
        result = self.run_two()
        self.assertEqual(result["schema"], two_live.SCHEMA)
        self.assertTrue(result["two_native_elf_captures_and_complete_replays_verified"])
        self.assertTrue(result["same_elf_arguments_used_for_both_launches"])
        self.assertTrue(result["same_executable_inode_and_sha_pinned_through_both_launches"])
        self.assertFalse(result["strict_gpu_timeline_match_required"])
        self.assertFalse(result["strict_gpu_timeline_match_verified"])
        self.assertTrue(result["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertTrue(result["gpu_vram_timeline_commitments_identical"])
        self.assertEqual(result["first_gpu_vram_timeline_sha256"],
                         result["second_gpu_vram_timeline_sha256"])
        self.assertIsNone(result["first_different_gpu_snapshot_phase"])
        self.assertIsNone(result["first_different_gpu_snapshot_changed_pixels"])
        self.assertEqual(result["different_gpu_before_vram_snapshots"], 0)
        self.assertEqual(result["different_gpu_after_vram_snapshots"], 0)
        self.assertEqual(result["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(result["different_bgr555_pixels"], 0)
        self.assertFalse(result["original_ps1_reference_authenticated"])
        self.assertFalse(result["retail_gameplay_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        for folder in self.dirs:
            self.assertGreater(len(list(folder.iterdir())), 0)
            self.assertNotIn(str(folder), json.dumps(result))

    def test_opt_in_strict_bit_exact_gpu_timeline_succeeds(self):
        result = self.run_two(require_identical_gpu_timeline=True)
        self.assertTrue(result["strict_gpu_timeline_match_required"])
        self.assertTrue(result["strict_gpu_timeline_match_verified"])
        self.assertTrue(result["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertTrue(result["repeated_gpu_event_journal_identical"])
        self.assertEqual(result["unmatched_gpu_vram_snapshots"], 0)

    def test_invalid_strict_mode_type_refused_before_launch(self):
        with self.assertRaisesRegex(ValueError, "arguments invalid"):
            self.run_two(require_identical_gpu_timeline="true")
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))

    def test_nonidentical_native_vram_remains_diagnostic_without_strict_mode(self):
        # Only the test harness changes the argv on the SECOND invocation:
        # this allows two genuine independently validated C11 ELF/GPU
        # sessions with different final VRAM, without changing ELF bytes.
        real_capture = two_live.capture
        called = []
        def alter_second(*args, **kwargs):
            called.append(1)
            if len(called) == 2:
                kwargs["args"] = ("alternate",)
            return real_capture(*args, **kwargs)
        with patch.object(two_live, "capture", side_effect=alter_second):
            report = self.run_two()
        self.assertEqual(len(called), 2)
        self.assertEqual(report["different_bgr555_pixels"], 1)
        self.assertFalse(report["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertTrue(report["repeated_gpu_event_journal_identical"])
        self.assertFalse(report["strict_gpu_timeline_match_required"])
        self.assertFalse(report["strict_gpu_timeline_match_verified"])

    def test_strict_mode_rejects_different_native_vram_with_same_gpu_events(self):
        real_capture = two_live.capture
        called = []
        def alter_second(*args, **kwargs):
            called.append(1)
            if len(called) == 2:
                kwargs["args"] = ("alternate",)
            return real_capture(*args, **kwargs)
        with patch.object(two_live, "capture", side_effect=alter_second):
            with self.assertRaisesRegex(ValueError, "not bit-exact"):
                self.run_two(require_identical_gpu_timeline=True)
        self.assertEqual(len(called), 2)
        self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
        self.assertEqual(len(list(self.dirs[2].iterdir())), 2)

    def test_strict_gpu_timeline_gate_rejects_missing_claims(self):
        good = self.run_two()
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "repeated_full_gpu_vram_snapshot_sequence_identical": None})
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "repeated_gpu_event_journal_identical": False})
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "gpu_vram_snapshots_compared": True})
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "second_gpu_vram_timeline_sha256": "0" * 64})
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "first_gpu_vram_timeline_sha256": "G" * 64})

    def test_strict_cli_flag_succeeds_with_two_real_synthetic_launches(self):
        cmd = [
            sys.executable, "-m", "tools.run_map02_private_two_live_captures",
            "--executable", str(self.executable),
            "--executable-sha256", self.digest,
            "--first-frame", str(self.dirs[0]),
            "--first-journal", str(self.dirs[1]),
            "--second-frame", str(self.dirs[2]),
            "--second-journal", str(self.dirs[3]),
            "--frame", "123", "--require-identical-gpu-timeline",
        ]
        completed = subprocess.run(cmd, text=True, capture_output=True,
                                   timeout=22)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertTrue(output["strict_gpu_timeline_match_required"])
        self.assertTrue(output["strict_gpu_timeline_match_verified"])
        self.assertNotIn(str(self.executable), completed.stdout)

    def test_same_byte_executable_inode_swap_between_launches_refused(self):
        # Operate on a per-test ELF copy, never on the class shared C11 ELF.
        old = self.executable
        self.executable = self.dirs[0].parent / "local-copy-elf"
        shutil.copy2(old, self.executable)
        calls = []
        def swap_after_first(*args, **kwargs):
            result = original_capture(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                replacement = self.executable.with_name("replacement-elf")
                shutil.copy2(self.executable, replacement)
                os.replace(replacement, self.executable)
            return result
        with patch.object(two_live, "capture", side_effect=swap_after_first):
            with self.assertRaisesRegex(ValueError, "ELF identity changed"):
                self.run_two()
        self.assertEqual(calls, [1])
        self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
        self.assertEqual(list(self.dirs[2].iterdir()), [])
        self.assertEqual(list(self.dirs[3].iterdir()), [])

    def test_inplace_executable_mtime_mutation_between_runs_refused(self):
        old = self.executable
        self.executable = self.dirs[0].parent / "local-copy-elf"
        shutil.copy2(old, self.executable)
        calls = []
        def change_mtime_after_first(*args, **kwargs):
            result = original_capture(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                info = self.executable.stat()
                os.utime(self.executable,
                         ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
            return result
        with patch.object(two_live, "capture", side_effect=change_mtime_after_first):
            with self.assertRaisesRegex(ValueError, "ELF identity changed"):
                self.run_two()
        self.assertEqual(calls, [1])
        self.assertEqual(list(self.dirs[2].iterdir()), [])

    def test_symlink_executable_refused_before_both_launches(self):
        alias = self.dirs[0].parent / "private-elf-link"
        alias.symlink_to(self.executable)
        with self.assertRaises(OSError):
            two_live.run(alias, *self.dirs, frame=123,
                         executable_sha256=self.digest)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))

    def test_duplicated_output_role_fails_before_any_launch(self):
        with self.assertRaisesRegex(ValueError, "directory roles overlap"):
            two_live.run(self.executable, self.dirs[0], self.dirs[1],
                         self.dirs[0], self.dirs[3], frame=123,
                         executable_sha256=self.digest)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))

    def test_nonempty_second_journal_fails_before_first_launch(self):
        existing = self.dirs[3] / "keep.txt"
        existing.write_text("do not touch", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.run_two()
        self.assertEqual(existing.read_text(encoding="utf-8"), "do not touch")
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs[:3]))

    def test_wrong_elf_sha_aborts_without_publishing_frame(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.run_two(sha="0" * 64)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))

    def test_invalid_frame_label_is_refused_before_running(self):
        with self.assertRaisesRegex(ValueError, "arguments invalid"):
            self.run_two(frame=0)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))

    def test_later_elf_failure_never_reports_success(self):
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                kwargs["args"] = ("bad-vram",)
            return original_capture(*args, **kwargs)
        with patch.object(two_live, "capture", side_effect=fail_second):
            with self.assertRaises(ValueError):
                self.run_two()
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(self.dirs[0].iterdir())), 2)

    def test_identical_byte_swap_after_second_publication_fails(self):
        calls = []
        def swap_first_after_second(*args, **kwargs):
            result = original_capture(*args, **kwargs)
            calls.append(1)
            if len(calls) == 2:
                target = self.dirs[0] / "process-frame.bgr555"
                other = self.dirs[0] / "byte-identical-replacement"
                other.write_bytes(target.read_bytes())
                other.chmod(0o600)
                os.replace(other, target)
            return result
        with patch.object(two_live, "capture",
                          side_effect=swap_first_after_second):
            with self.assertRaisesRegex(ValueError, "published files changed"):
                self.run_two()

    def test_forged_provenance_flags_cannot_pass_final_join(self):
        real_audit = two_live.audit
        def falsify(*args, **kwargs):
            result = real_audit(*args, **kwargs)
            result["ps1_hardware_pixel_equivalence_verified"] = True
            return result
        with patch.object(two_live, "audit", side_effect=falsify):
            with self.assertRaisesRegex(ValueError, "witness invalid"):
                self.run_two()

    def test_cli_reports_only_digests_not_private_paths(self):
        command = [
            sys.executable, "-m", "tools.run_map02_private_two_live_captures",
            "--executable", str(self.executable),
            "--executable-sha256", self.digest,
            "--first-frame", str(self.dirs[0]),
            "--first-journal", str(self.dirs[1]),
            "--second-frame", str(self.dirs[2]),
            "--second-journal", str(self.dirs[3]),
            "--frame", "123",
        ]
        completed = subprocess.run(command, text=True, capture_output=True,
                                   timeout=22)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["two_native_elf_captures_and_complete_replays_verified"])
        self.assertNotIn(str(self.executable), completed.stdout)
        self.assertNotIn(str(self.dirs[0]), completed.stdout)

    def test_cli_missing_executable_does_not_reveal_private_path(self):
        private = self.dirs[0].parent / "retail-game-image-secret"
        command = [
            sys.executable, "-m", "tools.run_map02_private_two_live_captures",
            "--executable", str(private),
            "--executable-sha256", self.digest,
            "--first-frame", str(self.dirs[0]),
            "--first-journal", str(self.dirs[1]),
            "--second-frame", str(self.dirs[2]),
            "--second-journal", str(self.dirs[3]),
            "--frame", "123",
        ]
        completed = subprocess.run(command, text=True, capture_output=True,
                                   timeout=10)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("failed verification", completed.stderr)
        self.assertNotIn(str(private), completed.stderr)


if __name__ == "__main__":
    unittest.main()
