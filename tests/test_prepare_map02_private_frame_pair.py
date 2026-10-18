"""Asset-free real Linux C11 GPU capture to private PS1-claimed pair preparation."""
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
from tools import prepare_map02_private_frame_pair as pair
from tools.compare_map02_private_bgr555_frames import compare


class VerifiedNativeFramePairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
            raise unittest.SkipTest("Linux procfs required")
        cls.work = tempfile.TemporaryDirectory(prefix="vh-map02-pair-c11-")
        folder = Path(cls.work.name)
        cls.executable = folder / "producer"
        code = folder / "producer.c"
        code.write_text(PRODUCER, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise unittest.SkipTest("C11 compiler missing")
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1", "-Itools",
                        str(code), "tools/map02_native_frame_pipe.c", "-o",
                        str(cls.executable)], check=True)
        cls.exe_sha = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory(prefix="vh-map02-pair-real-")
        self.addCleanup(self.workdir.cleanup)
        root = Path(self.workdir.name)
        self.live = root / "live"
        self.journal = root / "journal"
        self.destination = root / "pair"
        self.reference_dir = root / "independent-claim"
        for folder in (self.live, self.journal, self.destination,
                       self.reference_dir):
            folder.mkdir(mode=0o700)
        self.capture = capture(
            self.executable, self.live, frame=123,
            width=1024, height=512, executable_sha256=self.exe_sha,
            gpu_journal_dir=self.journal, timeout=8)
        self.reference = self.reference_dir / "reference.bgr555"
        self.reference.write_bytes((self.live / "process-frame.bgr555").read_bytes())
        self.reference.chmod(0o600)

    def prepare(self):
        return pair.prepare(self.reference, self.live, self.journal,
                            self.executable, self.destination)

    def test_real_child_replay_produces_claimed_pair_and_digest_report(self):
        out = self.prepare()
        self.assertEqual(out["verified_live_candidate_sha256"],
                         self.capture["image_sha256"])
        self.assertEqual(out["same_launch_gpu_journal_sha256"],
                         self.capture["gpu_journal_sha256"])
        self.assertTrue(out["verified_live_frame_twice_replayed"])
        self.assertFalse(out["original_reference_ps1_hardware_authenticated"])
        self.assertFalse(out["hd_replacement_authorized"])
        self.assertEqual(out["different_bgr555_pixels"], 0)
        self.assertEqual(set(p.name for p in self.destination.iterdir()),
                         set(pair.NAMES))
        self.assertEqual(compare(self.destination)["different_bgr555_pixels"], 0)
        for name in pair.NAMES:
            self.assertEqual((self.destination / name).stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.reference), json.dumps(out))
        self.assertNotIn(str(self.live), json.dumps(out))

    def test_independent_reference_one_stp_pixel_is_reported_not_rejected(self):
        raw = bytearray(self.reference.read_bytes())
        raw[1] ^= 0x80
        self.reference.write_bytes(raw)
        out = self.prepare()
        self.assertEqual(out["different_bgr555_pixels"], 1)
        self.assertFalse(out["original_reference_ps1_hardware_authenticated"])

    def test_insecure_independent_reference_refused_without_publication(self):
        self.reference.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "raw BGR555 invalid"):
            self.prepare()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_truncated_reference_refused_without_publication(self):
        self.reference.write_bytes(b"\x00\x00")
        with self.assertRaisesRegex(ValueError, "raw BGR555 invalid"):
            self.prepare()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_nonempty_output_refused_without_modifying_existing_file(self):
        existing = self.destination / "preserve.txt"
        existing.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.prepare()
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

    def test_reference_path_symlink_refused_before_publication(self):
        actual = self.reference_dir / "actual.bgr555"
        self.reference.rename(actual)
        self.reference.symlink_to(actual)
        with self.assertRaises(OSError):
            self.prepare()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_same_byte_reference_inode_replacement_rolls_back(self):
        real_compare = pair.compare
        def substitute(folder):
            report = real_compare(folder)
            replacement = self.reference_dir / "new.bgr555"
            replacement.write_bytes(self.reference.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, self.reference)
            return report
        with patch.object(pair, "compare", side_effect=substitute):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.prepare()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_changed_live_frame_after_first_replay_rolls_back(self):
        original_replay = pair.replay
        called = []
        def tamper(*args, **kwargs):
            result = original_replay(*args, **kwargs)
            called.append(1)
            if len(called) == 1:
                pixels = self.live / "process-frame.bgr555"
                with pixels.open("r+b") as file:
                    file.seek(0)
                    file.write(b"\x00\x00")
            return result
        with patch.object(pair, "replay", side_effect=tamper):
            with self.assertRaises(ValueError):
                self.prepare()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cli_missing_reference_suppresses_absolute_paths(self):
        missing = self.reference_dir / "private-path-secret"
        cmd = [sys.executable, "-m", "tools.prepare_map02_private_frame_pair",
               "--reference-bgr555", str(missing),
               "--live-frame", str(self.live),
               "--gpu-journal-dir", str(self.journal),
               "--executable", str(self.executable),
               "--frame-pair-dir", str(self.destination)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("private frame pair preparation failed", proc.stderr)
        self.assertNotIn(str(missing), proc.stderr)
        self.assertNotIn(str(self.executable), proc.stderr)
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
