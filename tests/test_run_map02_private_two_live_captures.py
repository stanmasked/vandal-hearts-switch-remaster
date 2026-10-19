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
        # Emit a valid altered JSONL event directly from the second
        # synthetic child, leaving the final BGR555 output untouched.
        # The test harness alters the *second launch only* to exercise
        # diagnostic and strict mismatch handling for a pinned ELF.
        updated = PRODUCER.replace(needle, replacement)
        changes = (
            ('static int log_event(FILE *stream, unsigned step, const char *phase, unsigned frame) {',
             'static int log_event(FILE *stream, unsigned step, const char *phase, unsigned frame, int semi) {'),
            (r'\"primitive_type\":4,\"semi\":0,\"window\"',
             r'\"primitive_type\":4,\"semi\":%d,\"window\"'),
            ('step, frame, phase, step) > 0;',
             'step, frame, phase, step, semi) > 0;'),
            ('int bad_vram = argc > 1 && !strcmp(argv[1], "bad-vram");',
             'int bad_vram = argc > 1 && !strcmp(argv[1], "bad-vram");\n'
             '    int alternate_event = argc > 1 && '
             '(!strcmp(argv[1], "alternate-event") || '
             '!strcmp(argv[1], "alternate-event-before"));'),
            ('!log_event(events, 0, "before", wrong_frame ? 124 : 123)',
             '!log_event(events, 0, "before", wrong_frame ? 124 : 123, alternate_event)'),
            ('!log_event(events, 1, "after", wrong_frame ? 124 : 123)',
             '!log_event(events, 1, "after", wrong_frame ? 124 : 123, alternate_event)'),
        )
        for old_c, new_c in changes:
            if updated.count(old_c) != 1:
                raise RuntimeError("MAP02 two-launch GPU event C11 anchor drift")
            updated = updated.replace(old_c, new_c)
        before = 'if (!write_image(dir, "gpu-0000-vram.bin")) return 43;'
        if updated.count(before) != 1:
            raise RuntimeError("MAP02 two-launch before-VRAM C11 anchor drift")
        updated = updated.replace(
            before,
            'if (argc > 1 && !strcmp(argv[1], "alternate-event-before")) '
            'native_vram[0][0] = 0x1234;\n        ' + before)
        # Extend only explicitly requested synthetic captures with a
        # SECOND real DrawOTag pair. This exercises later event ordinals
        # while preserving the original single-pair test expectations.
        anchor = 'if (snprintf(logfile, sizeof(logfile), "%s/gpu-native-events.jsonl", dir) >='
        if updated.count(anchor) != 1:
            raise RuntimeError("MAP02 two-pair journal anchor drift")
        extra = (
            'int two_pair = argc > 1 && '
            '(!strcmp(argv[1], "two-pair") || '
            '!strcmp(argv[1], "two-pair-alternate-event") || '
            '!strcmp(argv[1], "two-pair-alternate-vram") || '
            '!strcmp(argv[1], "two-pair-alternate-both") || '
            '!strcmp(argv[1], "two-pair-extra-terminal"));\n'
            '        int second_event = argc > 1 && '
            '(!strcmp(argv[1], "two-pair-alternate-event") || '
            '!strcmp(argv[1], "two-pair-alternate-both"));\n'
            '        int second_vram = argc > 1 && '
            '(!strcmp(argv[1], "two-pair-alternate-vram") || '
            '!strcmp(argv[1], "two-pair-alternate-both") || '
            '!strcmp(argv[1], "two-pair-extra-terminal"));\n'
            '        if (two_pair) {\n'
            '            if (!write_image(dir, "gpu-0002-vram.bin")) return 63;\n'
            '            if (second_vram) native_vram[0][0] = 0x7ffe;\n'
            '            if (!write_image(dir, "gpu-0003-vram.bin")) return 64;\n'
            '        }\n        '
        )
        updated = updated.replace(anchor, extra + anchor)
        log_anchor = (
            '!log_event(events, 1, "after", wrong_frame ? 124 : 123, alternate_event) ||\n'
            '            fflush(events) != 0'
        )
        if updated.count(log_anchor) != 1:
            raise RuntimeError("MAP02 two-pair log emission anchor drift")
        updated = updated.replace(log_anchor, (
            '!log_event(events, 1, "after", wrong_frame ? 124 : 123, alternate_event) ||\n'
            '            (two_pair && '
            '(!log_event(events, 2, "before", 123, second_event) ||\n'
            '             !log_event(events, 3, "after", 123, second_event))) ||\n'
            '            fflush(events) != 0'
        ))
        source.write_text(updated, encoding="utf-8")
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
        self.assertTrue(result["repeated_gpu_event_records_identical"])
        self.assertEqual(result["different_gpu_event_records_in_common_prefix"], 0)
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
        self.assertIsNone(result["first_joint_gpu_divergence_index"])
        self.assertIsNone(result["first_joint_gpu_divergence_kind"])

    def test_mutated_caller_argument_list_cannot_change_second_elf_launch(self):
        # The same compiled C11 ELF supports both a plain two-pair GPU
        # run and an alternate second-pair VRAM image. A caller can mutate
        # its original argv LIST during the first child capture; neither
        # the second launch nor the bit-exact strict receipt may change.
        supplied_args = ["two-pair"]
        actual_args = []
        real_capture = two_live.capture
        def mutate_after_first_child(*args, **kwargs):
            actual_args.append(tuple(kwargs["args"]))
            receipt = real_capture(*args, **kwargs)
            if len(actual_args) == 1:
                supplied_args[:] = ["two-pair-alternate-vram"]
            return receipt
        with patch.object(two_live, "capture",
                          side_effect=mutate_after_first_child):
            report = self.run_two(
                args=supplied_args, require_identical_gpu_timeline=True)
        self.assertEqual(supplied_args, ["two-pair-alternate-vram"])
        self.assertEqual(actual_args, [("two-pair",), ("two-pair",)])
        self.assertEqual(report["gpu_event_records_compared"], 4)
        self.assertEqual(report["gpu_vram_snapshots_compared"], 4)
        self.assertTrue(report["strict_gpu_timeline_match_verified"])
        self.assertTrue(report["same_elf_arguments_used_for_both_launches"])
        self.assertTrue(report["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertEqual(report["different_bgr555_pixels"], 0)
        self.assertFalse(report["hd_replacement_authorized"])
        for folder in self.dirs:
            self.assertNotIn(str(folder), json.dumps(report))

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

    def _launch_with_different_second_gpu_event(self, variant, *, strict):
        """Inject alternate arguments only after the first real C11 launch."""
        real_capture = two_live.capture
        calls = []
        def change_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                kwargs["args"] = (variant,)
            return real_capture(*args, **kwargs)
        with patch.object(two_live, "capture", side_effect=change_second):
            if strict:
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    self.run_two(require_identical_gpu_timeline=True)
                result = None
            else:
                result = self.run_two()
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
        self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
        return result

    def test_two_launch_diagnostic_event_only_does_not_claim_strict_equality(self):
        report = self._launch_with_different_second_gpu_event(
            "alternate-event", strict=False)
        self.assertTrue(report["repeated_native_frame_pixels_identical"])
        self.assertTrue(report["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertFalse(report["repeated_gpu_event_journal_identical"])
        self.assertFalse(report["repeated_gpu_event_records_identical"])
        self.assertEqual(report["first_joint_gpu_divergence_kind"], "event-only")
        self.assertEqual(report["first_joint_gpu_divergence_index"], 0)
        self.assertEqual(report["first_joint_gpu_divergence_phase"], "before")
        self.assertFalse(report["strict_gpu_timeline_match_verified"])
        self.assertFalse(report["hd_replacement_authorized"])
        for folder in self.dirs:
            self.assertNotIn(str(folder), json.dumps(report))

    def test_two_launch_strict_rejects_event_only_difference(self):
        self._launch_with_different_second_gpu_event(
            "alternate-event", strict=True)

    def test_two_launch_diagnostic_joint_difference_reconverges(self):
        report = self._launch_with_different_second_gpu_event(
            "alternate-event-before", strict=False)
        self.assertTrue(report["repeated_native_frame_pixels_identical"])
        self.assertFalse(report["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertFalse(report["repeated_gpu_event_records_identical"])
        self.assertEqual(report["first_joint_gpu_divergence_kind"], "event-and-vram")
        self.assertEqual(report["first_joint_gpu_divergence_index"], 0)
        self.assertEqual(report["first_different_gpu_vram_snapshot_index"], 0)
        self.assertTrue(report["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertFalse(report["strict_gpu_timeline_match_verified"])

    def test_two_launch_strict_rejects_joint_difference(self):
        self._launch_with_different_second_gpu_event(
            "alternate-event-before", strict=True)

    def test_two_draw_pairs_strict_same_elf_captures_bit_exact(self):
        report = self.run_two(args=("two-pair",),
                              require_identical_gpu_timeline=True)
        self.assertTrue(report["strict_gpu_timeline_match_verified"])
        self.assertEqual(report["first_gpu_pairs_verified"], 2)
        self.assertEqual(report["second_gpu_pairs_verified"], 2)
        self.assertEqual(report["gpu_event_records_compared"], 4)
        self.assertEqual(report["gpu_vram_snapshots_compared"], 4)
        self.assertIsNone(report["first_joint_gpu_divergence_index"])
        self.assertTrue(report["repeated_native_frame_pixels_identical"])

    def _launch_with_second_pair_difference(self, second_variant, *, strict):
        original = two_live.capture
        calls = []
        def replace_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                kwargs["args"] = (second_variant,)
            return original(*args, **kwargs)
        with patch.object(two_live, "capture", side_effect=replace_second):
            if strict:
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    self.run_two(args=("two-pair",),
                                 require_identical_gpu_timeline=True)
                result = None
            else:
                result = self.run_two(args=("two-pair",))
        self.assertEqual(len(calls), 2)
        return result

    def test_second_draw_pair_event_only_divergence(self):
        out = self._launch_with_second_pair_difference(
            "two-pair-alternate-event", strict=False)
        self.assertEqual(out["gpu_event_records_compared"], 4)
        self.assertEqual(out["different_gpu_event_records_in_common_prefix"], 2)
        self.assertEqual(out["first_different_gpu_event_record_index"], 2)
        self.assertEqual(out["first_joint_gpu_divergence_index"], 2)
        self.assertEqual(out["first_joint_gpu_divergence_pair_index"], 1)
        self.assertEqual(out["first_joint_gpu_divergence_phase"], "before")
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "event-only")
        self.assertTrue(out["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertTrue(out["repeated_native_frame_pixels_identical"])
        self.assertFalse(out["strict_gpu_timeline_match_verified"])

    def test_second_draw_pair_vram_only_divergence(self):
        out = self._launch_with_second_pair_difference(
            "two-pair-alternate-vram", strict=False)
        self.assertEqual(out["first_different_gpu_vram_snapshot_index"], 3)
        self.assertEqual(out["first_joint_gpu_divergence_index"], 3)
        self.assertEqual(out["first_joint_gpu_divergence_pair_index"], 1)
        self.assertEqual(out["first_joint_gpu_divergence_phase"], "after")
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "vram-only")
        self.assertTrue(out["repeated_gpu_event_records_identical"])
        self.assertEqual(out["different_bgr555_pixels"], 1)
        self.assertFalse(out["strict_gpu_timeline_match_verified"])

    def test_second_draw_pair_event_precedes_vram_divergence(self):
        out = self._launch_with_second_pair_difference(
            "two-pair-alternate-both", strict=False)
        self.assertEqual(out["first_different_gpu_event_record_index"], 2)
        self.assertEqual(out["first_different_gpu_vram_snapshot_index"], 3)
        self.assertEqual(out["first_joint_gpu_divergence_index"], 2)
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "event-only")
        self.assertEqual(out["different_bgr555_pixels"], 1)
        self.assertFalse(out["strict_gpu_timeline_match_verified"])

    def test_second_draw_pair_strict_mode_rejects_all_divergences(self):
        for variant in ("two-pair-alternate-event",
                        "two-pair-alternate-vram",
                        "two-pair-alternate-both"):
            with self.subTest(variant=variant):
                # Each strict attempt requires four new empty output
                # directories; the first failed attempt keeps its evidence.
                if variant != "two-pair-alternate-event":
                    for folder in self.dirs:
                        for target in folder.iterdir():
                            target.unlink()
                self._launch_with_second_pair_difference(variant, strict=True)

    def _launch_with_unmatched_gpu_pair(self, *, longer_second, strict):
        # Both children use the exact same pinned ELF. Only this test's
        # capture shim varies arguments, yielding a real extra GPU pair
        # in one child with no changed prefix events or terminal pixels.
        original = two_live.capture
        calls = []
        first_args = () if longer_second else ("two-pair",)
        second_args = ("two-pair",) if longer_second else ()
        def change_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                kwargs["args"] = second_args
            return original(*args, **kwargs)
        with patch.object(two_live, "capture", side_effect=change_second):
            if strict:
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    self.run_two(args=first_args,
                                 require_identical_gpu_timeline=True)
                result = None
            else:
                result = self.run_two(args=first_args)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(self.dirs[1].iterdir())),
                         3 if longer_second else 5)
        self.assertEqual(len(list(self.dirs[3].iterdir())),
                         5 if longer_second else 3)
        return result

    def test_unmatched_second_draw_pair_is_not_bit_exact_in_diagnostic_mode(self):
        for longer_second in (True, False):
            with self.subTest(longer_second=longer_second):
                if not longer_second:
                    for folder in self.dirs:
                        for path in folder.iterdir():
                            path.unlink()
                report = self._launch_with_unmatched_gpu_pair(
                    longer_second=longer_second, strict=False)
                self.assertEqual(report["first_gpu_event_count"],
                                 2 if longer_second else 4)
                self.assertEqual(report["second_gpu_event_count"],
                                 4 if longer_second else 2)
                self.assertEqual(report["gpu_event_records_compared"], 2)
                self.assertEqual(report["gpu_vram_snapshots_compared"], 2)
                self.assertEqual(report["unmatched_gpu_event_records"], 2)
                self.assertEqual(report["unmatched_gpu_vram_snapshots"], 2)
                self.assertEqual(report["different_gpu_event_records_in_common_prefix"], 0)
                self.assertEqual(report["different_gpu_vram_snapshots_in_common_prefix"], 0)
                self.assertIsNone(report["first_different_gpu_event_record_index"])
                self.assertIsNone(report["first_different_gpu_vram_snapshot_index"])
                self.assertEqual(report["first_joint_gpu_divergence_kind"],
                                 "unmatched-tail")
                self.assertEqual(report["first_joint_gpu_divergence_index"], 2)
                self.assertEqual(report["first_joint_gpu_divergence_pair_index"], 1)
                self.assertEqual(report["first_joint_gpu_divergence_phase"], "before")
                self.assertTrue(report["repeated_native_frame_pixels_identical"])
                self.assertEqual(report["different_bgr555_pixels"], 0)
                self.assertFalse(report["strict_gpu_timeline_match_verified"])
                self.assertFalse(report["hd_replacement_authorized"])

    def test_unmatched_gpu_tail_is_symmetric_for_same_replayed_captures(self):
        # Each case uses the exact same two independently published C11
        # children for BOTH comparisons, reversing roles in the auditor
        # rather than launching any replacement producer.
        symmetric = (
            "first_joint_gpu_divergence_index",
            "first_joint_gpu_divergence_pair_index",
            "first_joint_gpu_divergence_phase",
            "first_joint_gpu_divergence_kind",
            "gpu_event_records_compared",
            "gpu_vram_snapshots_compared",
            "unmatched_gpu_event_records",
            "unmatched_gpu_vram_snapshots",
            "different_gpu_event_records_in_common_prefix",
            "different_gpu_vram_snapshots_in_common_prefix",
            "different_bgr555_pixels",
            "repeated_native_frame_pixels_identical",
        )
        paired = (
            ("first_gpu_pairs_verified", "second_gpu_pairs_verified"),
            ("first_gpu_event_count", "second_gpu_event_count"),
            ("first_gpu_vram_snapshot_count",
             "second_gpu_vram_snapshot_count"),
            ("first_image_sha256", "second_image_sha256"),
            ("first_gpu_journal_sha256", "second_gpu_journal_sha256"),
            ("first_gpu_vram_timeline_sha256",
             "second_gpu_vram_timeline_sha256"),
        )
        for longer_second in (True, False):
            with self.subTest(longer_second=longer_second):
                if not longer_second:
                    for folder in self.dirs:
                        for file in folder.iterdir():
                            file.unlink()
                forward = self._launch_with_unmatched_gpu_pair(
                    longer_second=longer_second, strict=False)
                reverse = two_live.audit(
                    self.dirs[2], self.dirs[3],
                    self.dirs[0], self.dirs[1], self.executable)
                self.assertEqual(
                    forward["first_joint_gpu_divergence_kind"],
                    "unmatched-tail")
                self.assertEqual(forward["first_joint_gpu_divergence_index"], 2)
                self.assertTrue(forward["repeated_native_frame_pixels_identical"])
                for key in symmetric:
                    self.assertEqual(
                        forward[key], reverse[key],
                        msg=(longer_second, key))
                for first, second in paired:
                    self.assertEqual(forward[first], reverse[second])
                    self.assertEqual(forward[second], reverse[first])
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    two_live._require_bit_exact_gpu_timeline(reverse)
                for folder in self.dirs:
                    self.assertNotIn(str(folder), json.dumps(forward))
                    self.assertNotIn(str(folder), json.dumps(reverse))
                self.assertFalse(reverse["hd_replacement_authorized"])

    def test_unmatched_second_draw_pair_strict_mode_rejects_both_directions(self):
        for longer_second in (True, False):
            with self.subTest(longer_second=longer_second):
                if not longer_second:
                    for folder in self.dirs:
                        for path in folder.iterdir():
                            path.unlink()
                self._launch_with_unmatched_gpu_pair(
                    longer_second=longer_second, strict=True)

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
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "repeated_gpu_event_records_identical": False})
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(
                {**good, "unmatched_gpu_event_records": 2})
        # Reports that silently omit or falsify joint-localization fields
        # must fail closed, even if the legacy digest/equality bits say yes.
        for changed in (
            {"first_joint_gpu_divergence_kind": "event-only"},
            {"first_joint_gpu_divergence_index": 0},
            {"first_joint_gpu_divergence_pair_index": 0},
            {"first_joint_gpu_divergence_phase": "before"},
            {"first_gpu_event_count": True},
            {"second_gpu_event_count": good["first_gpu_event_count"] + 2},
            {"second_gpu_vram_snapshot_count":
                 good["first_gpu_vram_snapshot_count"] + 2},
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    two_live._require_bit_exact_gpu_timeline({**good, **changed})
        without_field = dict(good)
        del without_field["first_joint_gpu_divergence_kind"]
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(without_field)

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
