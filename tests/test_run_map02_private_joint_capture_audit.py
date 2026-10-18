"""Asset-free synthetic C11 ELF smoke tests for one-shot private GPU audit."""
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
from tools import run_map02_private_joint_capture_audit as joint_runner


class PrivateJointOneShotAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
            raise unittest.SkipTest("strict Linux ELF and procfs needed")
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-one-shot-c-")
        root = Path(cls.workspace.name)
        cls.executable = root / "producer"
        source = root / "producer.c"
        source.write_text(PRODUCER, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise RuntimeError("C compiler missing for native GPU capture")
        subprocess.run(
            [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1",
             "-Itools", str(source), "tools/map02_native_frame_pipe.c",
             "-o", str(cls.executable)],
            check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-one-shot-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.output = root / "private-frame"
        self.journal = root / "private-journal"
        self.output.mkdir(mode=0o700)
        self.journal.mkdir(mode=0o700)

    def run_capture(self, *args, **kwargs):
        return joint_runner.run(
            self.executable, self.output, self.journal, frame=123,
            executable_sha256=kwargs.pop("sha", self.digest),
            timeout=kwargs.pop("timeout", 4), args=args, **kwargs)

    def test_one_real_synthetic_child_two_complete_private_replays(self):
        result = self.run_capture()
        self.assertEqual(result["schema"], joint_runner.SCHEMA)
        self.assertEqual((result["width"], result["height"]), (1024, 512))
        self.assertEqual(result["frame"], 123)
        self.assertEqual(result["gpu_journal_pairs_verified"], 1)
        self.assertTrue(result["two_full_independent_private_replays_equal"])
        self.assertTrue(result["private_frame_and_journal_inodes_stable_through_replays"])
        self.assertEqual(result["terminal_gpu_after_vram_sha256"],
                         result["terminal_bgr555_sha256"])
        self.assertTrue(result["child_writable_gpu_journal_fd_observed"])
        self.assertTrue(result["terminal_frame_exactly_equals_gpu_after_vram"])
        for name in (
                "retail_gameplay_or_ps1_pixels_authenticated",
                "native_gpu_log_same_process_authenticated",
                "gpu_journal_writer_kernel_authenticated",
                "hd_replacement_authorized",
                "private_pixel_bytes_or_paths_emitted"):
            self.assertFalse(result[name])
        self.assertNotIn(str(self.output), json.dumps(result))
        self.assertNotIn(str(self.journal), json.dumps(result))
        self.assertNotIn(str(self.executable), json.dumps(result))

    def test_wrong_native_executable_digest_refused_without_publication(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.run_capture(sha="0" * 64)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.journal.iterdir()), [])

    def test_missing_native_journal_prevents_private_frame_publication(self):
        with self.assertRaisesRegex(ValueError, "timed out observing writable"):
            self.run_capture("no-journal", timeout=0.5)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_image_tamper_after_capture_refused_on_first_replay(self):
        original_capture = joint_runner.capture
        def tamper(*args, **kwargs):
            receipt = original_capture(*args, **kwargs)
            filename = self.output / "process-frame.bgr555"
            with filename.open("r+b") as stream:
                stream.write(b"\xff\xff")
            return receipt
        with patch.object(joint_runner, "capture", side_effect=tamper):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.run_capture()

    def test_same_byte_gpu_log_inode_replacement_between_replays_refused(self):
        original_replay = joint_runner.replay
        calls = [0]
        def replace_after_first(*args, **kwargs):
            report = original_replay(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 1:
                filename = self.journal / "gpu-native-events.jsonl"
                replacement = self.journal / "fresh-log.jsonl"
                replacement.write_bytes(filename.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, filename)
            return report
        with patch.object(joint_runner, "replay",
                          side_effect=replace_after_first):
            with self.assertRaisesRegex(ValueError, "files changed between replays"):
                self.run_capture()
        self.assertEqual(calls[0], 1)

    def test_same_byte_frame_inode_replacement_between_replays_refused(self):
        original_replay = joint_runner.replay
        calls = [0]
        def replace_after_first(*args, **kwargs):
            report = original_replay(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 1:
                filename = self.output / "process-frame.bgr555"
                replacement = self.output / "fresh-frame.bgr555"
                replacement.write_bytes(filename.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, filename)
            return report
        with patch.object(joint_runner, "replay",
                          side_effect=replace_after_first):
            with self.assertRaisesRegex(ValueError, "files changed between replays"):
                self.run_capture()
        self.assertEqual(calls[0], 1)

    def test_journal_bytes_changed_after_capture_refused(self):
        original_capture = joint_runner.capture
        def tamper(*args, **kwargs):
            receipt = original_capture(*args, **kwargs)
            filename = self.journal / "gpu-native-events.jsonl"
            with filename.open("ab") as stream:
                stream.write(b"\n")
            return receipt
        with patch.object(joint_runner, "capture", side_effect=tamper):
            with self.assertRaises(ValueError):
                self.run_capture()

    def test_changed_evidence_between_two_replays_refused(self):
        actual_replay = joint_runner.replay
        calls = [0]
        def changed(*args, **kwargs):
            report = actual_replay(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 2:
                report = {**report, "receipt_sha256": "f" * 64}
            return report
        with patch.object(joint_runner, "replay", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed between replays"):
                self.run_capture()
        self.assertEqual(calls[0], 2)


if __name__ == "__main__":
    unittest.main()
