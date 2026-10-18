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
from tools import compare_map02_private_bgr555_frames as frame_compare


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

    def make_claimed_private_frame_pair(self, *, different_reference=False,
                                        different_candidate=False,
                                        frame=123):
        pair = Path(self.temp.name) / "private-claimed-frame-pair"
        pair.mkdir(mode=0o700)
        # The source-pinned C11 synthetic producer writes 0x7fff at
        # VRAM pixel (0,0) and zero into all other words. This local
        # fixture makes no claims of PS1 provenance or real game capture.
        raw = b"\xff\x7f" + b"\x00" * (1024 * 512 * 2 - 2)
        reference = ((b"\x00\x80" + raw[2:]) if different_reference else raw)
        candidate = ((b"\x11\x22" + raw[2:]) if different_candidate else raw)
        images = {}
        for name, pixels, origin in (
            ("reference.bgr555", reference, "ps1_reference_claimed"),
            ("candidate.bgr555", candidate, "pc_port_candidate_claimed"),
        ):
            (pair / name).write_bytes(pixels)
            (pair / name).chmod(0o600)
            images[name] = {
                "sha256": hashlib.sha256(pixels).hexdigest(),
                "frame": frame, "origin": origin}
        (pair / "frames.json").write_text(json.dumps({
            "schema": frame_compare.SCHEMA,
            "frame": frame, "width": 1024, "height": 512,
            "pixel_format": "bgr555_le", "images": images
        }, sort_keys=True), encoding="utf-8")
        (pair / "frames.json").chmod(0o600)
        return pair

    def test_claimed_reference_and_same_launch_candidate_byte_equal(self):
        pair = self.make_claimed_private_frame_pair()
        result = self.run_capture(frame_pair_dir=pair)
        self.assertTrue(result["claimed_reference_raw_bgr555_equal_to_live_candidate"])
        self.assertFalse(result["claimed_reference_ps1_hardware_authenticated"])
        self.assertEqual(result["claimed_reference_different_bgr555_pixels"], 0)
        self.assertEqual(result["claimed_reference_exact_pixel_matches"], 1024 * 512)
        self.assertNotIn(str(pair), json.dumps(result))

    def test_claimed_reference_has_one_pixel_stp_and_color_mismatch(self):
        pair = self.make_claimed_private_frame_pair(different_reference=True)
        result = self.run_capture(frame_pair_dir=pair)
        self.assertFalse(result["claimed_reference_raw_bgr555_equal_to_live_candidate"])
        self.assertEqual(result["claimed_reference_different_bgr555_pixels"], 1)
        self.assertEqual(result["claimed_reference_stp_bit_differences"], 1)
        self.assertEqual(result["claimed_reference_changed_scanlines"], 1)
        self.assertFalse(result["claimed_reference_ps1_hardware_authenticated"])

    def test_self_consistent_forged_claimed_candidate_rejected(self):
        pair = self.make_claimed_private_frame_pair(different_candidate=True)
        with self.assertRaisesRegex(ValueError, "claimed candidate differs"):
            self.run_capture(frame_pair_dir=pair)

    def test_same_byte_claimed_reference_inode_swap_during_capture_rejected(self):
        pair = self.make_claimed_private_frame_pair()
        real_capture = joint_runner.capture
        def swap(*args, **kwargs):
            receipt = real_capture(*args, **kwargs)
            path = pair / "reference.bgr555"
            new_path = pair / "same-byte-reference.bgr555"
            new_path.write_bytes(path.read_bytes())
            # The test isolates inode substitution, not file-mode refusal:
            # the new inode must itself satisfy the strict 0600 preflight.
            new_path.chmod(0o600)
            os.replace(new_path, path)
            return receipt
        with patch.object(joint_runner, "capture", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "frame pair changed during capture"):
                self.run_capture(frame_pair_dir=pair)

    def test_claimed_pair_frame_label_mismatch_fails_before_executing_elf(self):
        pair = self.make_claimed_private_frame_pair(frame=124)
        with self.assertRaisesRegex(ValueError, "wrong labels"):
            self.run_capture(frame_pair_dir=pair)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.journal.iterdir()), [])

    def test_cli_claimed_reference_compare_returns_only_digests_and_counts(self):
        pair = self.make_claimed_private_frame_pair(different_reference=True)
        finished = subprocess.run([
            sys.executable, "-m", "tools.run_map02_private_joint_capture_audit",
            "--executable", str(self.executable),
            "--executable-sha256", self.digest,
            "--output-dir", str(self.output),
            "--gpu-journal-dir", str(self.journal),
            "--frame-pair-dir", str(pair),
            "--frame", "123", "--timeout", "5",
        ], capture_output=True, text=True, timeout=12)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        result = json.loads(finished.stdout)
        self.assertEqual(result["claimed_reference_different_bgr555_pixels"], 1)
        self.assertFalse(result["claimed_reference_ps1_hardware_authenticated"])
        self.assertNotIn(str(pair), finished.stdout)
        self.assertNotIn(str(self.executable), finished.stdout)

    def test_claimed_frame_pair_shared_directory_refused_before_elf(self):
        pair = self.make_claimed_private_frame_pair()
        pair.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "directory must be owner-private"):
            self.run_capture(frame_pair_dir=pair)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.journal.iterdir()), [])

    def test_claimed_pair_world_readable_reference_refused_before_elf(self):
        pair = self.make_claimed_private_frame_pair()
        (pair / "reference.bgr555").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "file must be owner-private"):
            self.run_capture(frame_pair_dir=pair)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_claimed_pair_symlinked_reference_refused_before_elf(self):
        pair = self.make_claimed_private_frame_pair()
        ref = pair / "reference.bgr555"
        ref.unlink()
        ref.symlink_to(pair / "candidate.bgr555")
        with self.assertRaisesRegex(ValueError, "file must be owner-private"):
            self.run_capture(frame_pair_dir=pair)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_claimed_pair_hardlinked_reference_refused_before_elf(self):
        pair = self.make_claimed_private_frame_pair()
        ref = pair / "reference.bgr555"
        ref.unlink()
        os.link(pair / "candidate.bgr555", ref)
        with self.assertRaisesRegex(ValueError, "singly linked"):
            self.run_capture(frame_pair_dir=pair)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_claimed_pair_extra_file_refused_before_elf(self):
        pair = self.make_claimed_private_frame_pair()
        (pair / "notes.txt").write_text("not part of the pair", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected file inventory"):
            self.run_capture(frame_pair_dir=pair)
        self.assertEqual(list(self.output.iterdir()), [])

    def prepare_two_pass_inventory(self):
        # Minimal local on-disk inventory: no ELF execution necessary to
        # exercise the owner and stability checks on actual held dir FDs.
        for name in ("process-frame.bgr555", "process-frame.json"):
            path = self.output / name
            path.write_bytes(b"local-only-inventory")
            path.chmod(0o600)
        journal_file = self.journal / "gpu-native-events.jsonl"
        journal_file.write_bytes(b"local-only-inventory")
        journal_file.chmod(0o600)

    def test_two_pass_inventory_requires_owner_directory(self):
        self.prepare_two_pass_inventory()
        with patch.object(joint_runner.os, "getuid",
                          return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ValueError, "directory is not owner-private"):
                joint_runner._session_inode_witness(self.output, self.journal)

    def test_two_pass_inventory_requires_owner_file(self):
        self.prepare_two_pass_inventory()
        real_getuid = os.getuid
        real_stat = os.stat
        def simulate_other_owner(name, *args, **kwargs):
            info = real_stat(name, *args, **kwargs)
            if (name == "process-frame.bgr555"
                    and kwargs.get("dir_fd") is not None):
                values = list(info)
                # os.stat_result positional tuples contain the uid at 4.
                values[4] = real_getuid() + 1
                return os.stat_result(values)
            return info
        with patch.object(joint_runner.os, "stat",
                          side_effect=simulate_other_owner):
            with self.assertRaisesRegex(ValueError, "file not owner-private"):
                joint_runner._session_inode_witness(self.output, self.journal)

    def test_two_pass_inventory_detects_metadata_change_mid_scan(self):
        self.prepare_two_pass_inventory()
        real_stat = os.stat
        mutated = []
        def alter_after_read(name, *args, **kwargs):
            info = real_stat(name, *args, **kwargs)
            if (not mutated and name == "process-frame.bgr555"
                    and kwargs.get("dir_fd") is not None):
                mutated.append(True)
                # Keep the contents/inode/0600 unchanged; update only the
                # file timestamp between the first and second FD scans.
                os.utime(self.output / name,
                         ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
            return info
        with patch.object(joint_runner.os, "stat", side_effect=alter_after_read):
            with self.assertRaisesRegex(ValueError, "changed during inventory"):
                joint_runner._session_inode_witness(self.output, self.journal)
        self.assertEqual(mutated, [True])

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

    def test_cli_runs_native_one_shot_and_prints_digests_not_private_paths(self):
        result = subprocess.run([
            sys.executable, "-m", "tools.run_map02_private_joint_capture_audit",
            "--executable", str(self.executable),
            "--executable-sha256", self.digest,
            "--output-dir", str(self.output),
            "--gpu-journal-dir", str(self.journal),
            "--frame", "123", "--timeout", "5",
        ], capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = json.loads(result.stdout)
        self.assertEqual(meta["schema"], joint_runner.SCHEMA)
        self.assertEqual(meta["gpu_journal_pairs_verified"], 1)
        self.assertTrue(meta["two_full_independent_private_replays_equal"])
        self.assertFalse(meta["retail_gameplay_or_ps1_pixels_authenticated"])
        self.assertNotIn(str(self.executable), result.stdout)
        self.assertNotIn(str(self.output), result.stdout)
        self.assertNotIn(str(self.journal), result.stdout)

    def test_cli_wrong_elf_digest_fails_without_publication(self):
        result = subprocess.run([
            sys.executable, "-m", "tools.run_map02_private_joint_capture_audit",
            "--executable", str(self.executable),
            "--executable-sha256", "0" * 64,
            "--output-dir", str(self.output),
            "--gpu-journal-dir", str(self.journal),
            "--frame", "123", "--timeout", "5",
        ], capture_output=True, text=True, timeout=12)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.journal.iterdir()), [])

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
            with self.assertRaisesRegex(ValueError, "changed after publication"):
                self.run_capture()

    def test_same_byte_gpu_journal_inode_swap_after_publication_refused(self):
        # Identity was captured while BOTH directory FDs remained open in
        # the original launcher; no replay starts after this inode change.
        original_capture = joint_runner.capture
        called = []
        def tamper(*args, **kwargs):
            receipt = original_capture(*args, **kwargs)
            original = self.journal / "gpu-native-events.jsonl"
            replacement = self.journal / "identical-events.jsonl"
            replacement.write_bytes(original.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, original)
            called.append(1)
            return receipt
        with patch.object(joint_runner, "capture", side_effect=tamper):
            with self.assertRaisesRegex(ValueError, "changed after publication"):
                self.run_capture()
        self.assertEqual(called, [1])

    def test_same_byte_frame_inode_swap_after_publication_refused(self):
        original_capture = joint_runner.capture
        def tamper(*args, **kwargs):
            receipt = original_capture(*args, **kwargs)
            original = self.output / "process-frame.bgr555"
            replacement = self.output / "identical-frame.bgr555"
            replacement.write_bytes(original.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, original)
            return receipt
        with patch.object(joint_runner, "capture", side_effect=tamper):
            with self.assertRaisesRegex(ValueError, "changed after publication"):
                self.run_capture()

    def test_same_byte_receipt_inode_swap_after_publication_refused(self):
        original_capture = joint_runner.capture
        def tamper(*args, **kwargs):
            receipt = original_capture(*args, **kwargs)
            original = self.output / "process-frame.json"
            replacement = self.output / "identical-receipt.json"
            replacement.write_bytes(original.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, original)
            return receipt
        with patch.object(joint_runner, "capture", side_effect=tamper):
            with self.assertRaisesRegex(ValueError, "changed after publication"):
                self.run_capture()

    def test_failed_capture_publication_callback_rolls_back_frame(self):
        from tools.capture_map02_live_frame_pipe import capture as native_capture
        witnesses = []
        def reject(output_fd, journal_fd):
            self.assertTrue(os.fstat(output_fd).st_ino)
            self.assertTrue(os.fstat(journal_fd).st_ino)
            witnesses.append(True)
            raise ValueError("intentional post-publication witness refusal")
        with self.assertRaisesRegex(ValueError, "intentional post-publication"):
            native_capture(
                self.executable, self.output,
                frame=123, width=1024, height=512,
                executable_sha256=self.digest, timeout=4,
                gpu_journal_dir=self.journal,
                post_publish_witness=reject)
        self.assertEqual(witnesses, [True])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_same_launch_fd_witness_rejected(self):
        actual_capture = joint_runner.capture
        def skip_witness(*args, **kwargs):
            kwargs.pop("post_publish_witness", None)
            return actual_capture(*args, **kwargs)
        with patch.object(joint_runner, "capture", side_effect=skip_witness):
            with self.assertRaisesRegex(ValueError, "missing same-launch"):
                self.run_capture()

    def test_same_launch_publication_callback_receives_pinned_fds(self):
        # Exercise held directory inodes directly, not a second path lookup.
        original_capture = joint_runner.capture
        observed = []
        def wrapped(*args, **kwargs):
            original = kwargs["post_publish_witness"]
            def record(output_fd, journal_fd):
                self.assertEqual(
                    os.fstat(output_fd).st_ino, self.output.stat().st_ino)
                self.assertEqual(
                    os.fstat(journal_fd).st_ino, self.journal.stat().st_ino)
                observed.append((output_fd, journal_fd))
                original(output_fd, journal_fd)
            kwargs["post_publish_witness"] = record
            return original_capture(*args, **kwargs)
        with patch.object(joint_runner, "capture", side_effect=wrapped):
            report = self.run_capture()
        self.assertTrue(report["two_full_independent_private_replays_equal"])
        self.assertEqual(len(observed), 1)

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
