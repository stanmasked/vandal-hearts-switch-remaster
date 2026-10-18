"""Real synthetic C11 Linux joint frame/journal -> real native bridge contract.

Uses no private game binaries, patches ONLY the unavailable original-source
FT4/VRAM witness. The frame comparator, Linux ELF pipe, journal audit,
independent replay, bridge and final join are genuine implementations.
"""
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
from tools import bridge_map02_private_frame_native as bridge_module
from tools import compare_map02_private_bgr555_frames as frame_module
from tools import join_map02_live_frame_native as live_join


class FullLiveGpuJournalNativeBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
            raise unittest.SkipTest("private Linux ELF fd journal observation required")
        cls.temp_class = tempfile.TemporaryDirectory(prefix="vh-map02-full-join-")
        root = Path(cls.temp_class.name)
        src = root / "producer.c"
        cls.executable = root / "producer"
        src.write_text(PRODUCER, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise RuntimeError("MAP02 test compiler missing")
        subprocess.run([
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1", "-Itools",
            str(src), "tools/map02_native_frame_pipe.c",
            "-o", str(cls.executable)
        ], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp_class.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-joined-journal-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.live = self.root / "live"
        self.journal = self.root / "journal"
        self.pair = self.root / "pair"
        for folder in (self.live, self.journal, self.pair):
            folder.mkdir(mode=0o700)
        self.capture = capture(
            self.executable, self.live, frame=123,
            width=1024, height=512, executable_sha256=self.digest,
            gpu_journal_dir=self.journal, timeout=8)
        self.pixels = (self.live / "process-frame.bgr555").read_bytes()
        self.write_pair(self.pixels)

    def write_pair(self, candidate):
        files = {}
        for name, raw, origin in (
            ("reference.bgr555", self.pixels, "ps1_reference_claimed"),
            ("candidate.bgr555", candidate, "pc_port_candidate_claimed"),
        ):
            (self.pair / name).write_bytes(raw)
            files[name] = {"sha256": hashlib.sha256(raw).hexdigest(),
                           "frame": 123, "origin": origin}
        (self.pair / "frames.json").write_text(
            json.dumps({
                "schema": frame_module.SCHEMA,
                "frame": 123, "width": 1024, "height": 512,
                "pixel_format": "bgr555_le", "images": files
            }, sort_keys=True) + "\n", encoding="utf-8")

    def original_native_witness(self, *args, **kwargs):
        self.assertIs(kwargs["require_native_elf_image"], True)
        self.assertIs(kwargs["require_native_probe_symbols"], True)
        return {
            "schema": "vh.map02.private-launch-two-word-join.v1",
            "source_frame": 123,
            "native_gpu_frame": 123,
            "source_keyed_ft4_draws_checked": 1,
            "original_launch_receipt_sha256": "a" * 64,
            "two_word_manifest_sha256": "b" * 64,
            "native_gpu_event_log_sha256": "c" * 64,
            **{f: True for f in bridge_module.TRUE_FIELDS},
            **{f: False for f in bridge_module.FALSE_FIELDS},
        }

    def join(self):
        with patch.object(bridge_module, "audit_launch_two_word",
                          side_effect=self.original_native_witness):
            return live_join.join(
                self.pair, self.live, self.root / "native",
                self.root / "source",
                launch_receipt=self.root / "launch.json",
                preflight_report=self.root / "preflight.json",
                executable=self.executable, gpu_journal_dir=self.journal)

    def test_real_comparator_bridge_and_joint_gpu_replay_agree_on_same_pixels(self):
        result = self.join()
        self.assertEqual(result["schema"],
                         "vh.map02.live-frame-claimed-pair-native-digest-join.v1")
        self.assertEqual(result["candidate_sha256"],
                         self.capture["image_sha256"])
        self.assertEqual(result["same_launcher_gpu_journal_sha256"],
                         self.capture["gpu_journal_sha256"])
        self.assertEqual(result["same_launcher_gpu_terminal_vram_sha256"],
                         self.capture["image_sha256"])
        self.assertEqual(result["same_launcher_gpu_journal_pairs_verified"], 1)
        self.assertTrue(result["child_writable_gpu_journal_fd_observed"])
        self.assertTrue(result["same_launcher_terminal_frame_equal_gpu_after_vram"])
        self.assertTrue(result["native_gpu_trace_independently_replayed"])
        self.assertFalse(result["same_process_gpu_event_and_frame_causality_authenticated"])
        self.assertFalse(result["gpu_journal_writer_kernel_authenticated"])
        self.assertFalse(result["retail_disc_or_ps1_reference_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        data = json.dumps(result)
        self.assertNotIn(str(self.root), data)
        self.assertNotIn(self.pixels[:12].hex(), data)

    def test_same_byte_claimed_candidate_inode_swap_during_real_native_bridge_refused(self):
        def substitute(*args, **kwargs):
            image = self.pair / "candidate.bgr555"
            replacement = self.pair / "fresh-candidate.bgr555"
            replacement.write_bytes(image.read_bytes())
            os.replace(replacement, image)
            return self.original_native_witness(*args, **kwargs)
        with patch.object(bridge_module, "audit_launch_two_word",
                          side_effect=substitute):
            with self.assertRaisesRegex(ValueError, "changed during native witness"):
                live_join.join(
                    self.pair, self.live, self.root / "native",
                    self.root / "source",
                    launch_receipt=self.root / "launch.json",
                    preflight_report=self.root / "preflight.json",
                    executable=self.executable, gpu_journal_dir=self.journal)

    def test_candidate_modified_with_self_consistent_manifest_refused(self):
        forged = bytearray(self.pixels)
        forged[-2:] = b"\x11\x22"
        self.write_pair(bytes(forged))
        with self.assertRaisesRegex(ValueError, "pixels differ"):
            self.join()

    def test_joint_receipt_without_gpu_journal_not_downgraded_to_legacy(self):
        with patch.object(bridge_module, "audit_launch_two_word",
                          side_effect=self.original_native_witness):
            with self.assertRaisesRegex(ValueError, "requires exactly one"):
                live_join.join(
                    self.pair, self.live, self.root / "native", self.root / "source",
                    launch_receipt=self.root / "launch.json",
                    preflight_report=self.root / "preflight.json",
                    executable=self.executable)

    def test_gpu_journal_modified_after_release_rejected(self):
        target = self.journal / "gpu-native-events.jsonl"
        with target.open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaises(ValueError):
            self.join()

    def test_actual_native_bridge_rejects_unproven_positive_provenance(self):
        def forbidden(*args, **kwargs):
            result = self.original_native_witness(*args, **kwargs)
            result["native_process_to_log_causality_authenticated"] = True
            return result
        with patch.object(bridge_module, "audit_launch_two_word",
                          side_effect=forbidden):
            with self.assertRaisesRegex(ValueError, "unexpectedly asserted"):
                live_join.join(
                    self.pair, self.live, self.root / "native", self.root / "source",
                    launch_receipt=self.root / "launch.json",
                    preflight_report=self.root / "preflight.json",
                    executable=self.executable, gpu_journal_dir=self.journal)


if __name__ == "__main__":
    unittest.main()
