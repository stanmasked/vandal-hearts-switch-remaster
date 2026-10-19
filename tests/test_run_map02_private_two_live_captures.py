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

    def test_unmatched_gpu_tail_can_change_terminal_frame_in_either_direction(self):
        # This is one original SHA-pinned synthetic ELF. Only the test
        # capture shim changes argv between its actual child launches:
        # the long capture performs an extra DrawOTag that changes a real
        # BGR555 pixel, while the short capture terminates after pair one.
        # The common prefix is equal, so terminal-frame equality must not
        # be inferred from the last COMMON GPU after-snapshot.
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
            "changed_scanlines",
            "stp_bit_differences",
            "repeated_native_frame_pixels_identical",
        )
        labelled = (
            ("first_image_sha256", "second_image_sha256"),
            ("first_gpu_journal_sha256", "second_gpu_journal_sha256"),
            ("first_gpu_vram_timeline_sha256",
             "second_gpu_vram_timeline_sha256"),
            ("first_gpu_pairs_verified", "second_gpu_pairs_verified"),
        )
        for longer_second in (True, False):
            with self.subTest(longer_second=longer_second):
                if not longer_second:
                    for folder in self.dirs:
                        for entry in folder.iterdir():
                            entry.unlink()
                first_argv = () if longer_second else ("two-pair-extra-terminal",)
                second_argv = ("two-pair-extra-terminal",) if longer_second else ()
                real_capture = two_live.capture
                calls = []
                def change_second(*args, **kwargs):
                    calls.append(tuple(kwargs["args"]))
                    if len(calls) == 2:
                        kwargs["args"] = second_argv
                    return real_capture(*args, **kwargs)
                with patch.object(two_live, "capture",
                                  side_effect=change_second):
                    forward = self.run_two(args=first_argv)
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0], first_argv)
                self.assertEqual(forward["first_gpu_pairs_verified"],
                                 1 if longer_second else 2)
                self.assertEqual(forward["second_gpu_pairs_verified"],
                                 2 if longer_second else 1)
                self.assertEqual(forward["different_bgr555_pixels"], 1)
                self.assertEqual(forward["changed_scanlines"], 1)
                self.assertEqual(forward["stp_bit_differences"], 0)
                self.assertFalse(forward["repeated_native_frame_pixels_identical"])
                self.assertFalse(forward["repeated_full_gpu_vram_snapshot_sequence_identical"])
                self.assertFalse(forward["gpu_vram_timeline_commitments_identical"])
                self.assertEqual(forward["gpu_event_records_compared"], 2)
                self.assertEqual(forward["gpu_vram_snapshots_compared"], 2)
                self.assertEqual(forward["unmatched_gpu_event_records"], 2)
                self.assertEqual(forward["unmatched_gpu_vram_snapshots"], 2)
                self.assertEqual(
                    forward["different_gpu_event_records_in_common_prefix"], 0)
                self.assertEqual(
                    forward["different_gpu_vram_snapshots_in_common_prefix"], 0)
                self.assertIsNone(forward["first_different_gpu_vram_snapshot_index"])
                self.assertIsNone(forward["last_different_gpu_vram_snapshot_index"])
                self.assertEqual(forward["first_joint_gpu_divergence_index"], 2)
                self.assertEqual(forward["first_joint_gpu_divergence_pair_index"], 1)
                self.assertEqual(forward["first_joint_gpu_divergence_phase"], "before")
                self.assertEqual(forward["first_joint_gpu_divergence_kind"],
                                 "unmatched-tail")
                reverse = two_live.audit(
                    self.dirs[2], self.dirs[3],
                    self.dirs[0], self.dirs[1], self.executable)
                for key in symmetric:
                    self.assertEqual(forward[key], reverse[key], msg=key)
                for first, second in labelled:
                    self.assertEqual(forward[first], reverse[second])
                    self.assertEqual(forward[second], reverse[first])
                for report in (forward, reverse):
                    with self.assertRaisesRegex(ValueError, "not bit-exact"):
                        two_live._require_bit_exact_gpu_timeline(report)
                    self.assertFalse(report["hd_replacement_authorized"])
                    for folder in self.dirs:
                        self.assertNotIn(str(folder), json.dumps(report))

    def test_changed_terminal_extra_gpu_pair_strict_two_launch_run_refuses_both_orders(self):
        # Exercise the ACTUAL opt-in strict orchestrator, not merely its
        # post-hoc predicate. Both independent child sessions are fully
        # generated and locally replay-verified, but a second draw in
        # just one capture changes the terminal BGR555 frame.
        for longer_second in (True, False):
            with self.subTest(longer_second=longer_second):
                if not longer_second:
                    for directory in self.dirs:
                        for item in directory.iterdir():
                            item.unlink()
                first_args = () if longer_second else ("two-pair-extra-terminal",)
                second_args = ("two-pair-extra-terminal",) if longer_second else ()
                real_capture = two_live.capture
                calls = []
                def alter_only_second(*args, **kwargs):
                    calls.append(tuple(kwargs["args"]))
                    if len(calls) == 2:
                        kwargs["args"] = second_args
                    return real_capture(*args, **kwargs)
                with patch.object(two_live, "capture",
                                  side_effect=alter_only_second):
                    with self.assertRaisesRegex(ValueError, "not bit-exact"):
                        self.run_two(
                            args=first_args,
                            require_identical_gpu_timeline=True)
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0], first_args)
                self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
                # The capture files are retained only in owner-private
                # directories for diagnosis; no successful strict receipt.
                diagnostic = two_live.audit(*self.dirs, self.executable)
                self.assertEqual(diagnostic["different_bgr555_pixels"], 1)
                self.assertEqual(diagnostic["unmatched_gpu_event_records"], 2)
                self.assertEqual(diagnostic["unmatched_gpu_vram_snapshots"], 2)
                self.assertEqual(
                    diagnostic["first_joint_gpu_divergence_kind"],
                    "unmatched-tail")
                self.assertFalse(diagnostic["hd_replacement_authorized"])
                for directory in self.dirs:
                    self.assertNotIn(str(directory), json.dumps(diagnostic))

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

    def test_strict_gate_rechecks_secondary_gpu_vram_evidence_fields(self):
        # The independently replayed baseline is genuinely bit-exact, but
        # its reported secondary evidence can be falsified after audit.
        # Checking only legacy digest and zero-difference booleans used
        # to accept some of these internally contradictory summaries.
        good = self.run_two(require_identical_gpu_timeline=True)
        two_live._require_bit_exact_gpu_timeline(good)
        mutations = (
            {"different_gpu_before_vram_snapshots": 1},
            {"different_gpu_after_vram_snapshots": 1},
            {"first_different_gpu_vram_snapshot_index": 0},
            {"last_different_gpu_vram_snapshot_index": 1},
            {"first_reconverged_gpu_vram_snapshot_index": 1},
            {"gpu_vram_reconverged_at_common_prefix_end": True},
            {"gpu_vram_divergence_reappeared_after_reconvergence": True},
            {"first_different_gpu_event_record_index": 0},
            {"first_different_gpu_event_phase": "before"},
            {"first_different_gpu_event_pair_index": 0},
            {"changed_scanlines": 1},
            {"stp_bit_differences": 1},
            {"second_image_sha256": "0" * 64},
            {"first_gpu_vram_snapshot_count": 4},
        )
        for modified in mutations:
            with self.subTest(modified=modified):
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    two_live._require_bit_exact_gpu_timeline({
                        **good, **modified
                    })

    def test_strict_gate_rejects_mutated_native_gpu_source_commitments(self):
        # The two source journals were independently replay-verified and
        # their raw JSONL digests match. False post-audit labels may keep
        # all legacy equality flags set; the strict receipt must detect
        # the inconsistency with replayed DrawOTag pair counts and SHA.
        good = self.run_two(require_identical_gpu_timeline=True)
        two_live._require_bit_exact_gpu_timeline(good)
        modifications = (
            {"first_gpu_journal_sha256": "0" * 64},
            {"second_gpu_journal_sha256": "0" * 64},
            {"first_gpu_journal_sha256": "F" * 64},
            {"second_gpu_journal_sha256": None},
            {"first_gpu_pairs_verified": 0},
            {"second_gpu_pairs_verified": 2},
            {"first_gpu_pairs_verified": True},
            {"second_gpu_pairs_verified": "1"},
        )
        for changed in modifications:
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "not bit-exact"):
                    two_live._require_bit_exact_gpu_timeline({
                        **good, **changed})

    def test_full_strict_run_rejects_post_audit_journal_digest_tamper(self):
        # Preserve the real GPU JSONL and VRAM private files; falsify only
        # one public digest label AFTER the complete independent replays.
        # The new capture-receipt boundary refuses this inconsistency
        # BEFORE the strict bit-exact predicate. Both diagnostic and
        # strict modes must reject the forged source claim.
        real_audit = two_live.audit
        def tamper_source_digest(*args, **kwargs):
            original = real_audit(*args, **kwargs)
            return {**original, "second_gpu_journal_sha256": "0" * 64}
        for strict in (False, True):
            with self.subTest(strict=strict):
                for directory in self.dirs:
                    for entry in directory.iterdir():
                        entry.unlink()
                with patch.object(two_live, "audit",
                                  side_effect=tamper_source_digest):
                    with self.assertRaisesRegex(
                            ValueError, "pinned capture receipts"):
                        self.run_two(require_identical_gpu_timeline=strict)
                self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
                self.assertEqual(len(list(self.dirs[3].iterdir())), 3)

    def test_full_strict_run_rejects_post_audit_secondary_counter_tamper(self):
        # Do not merely unit-test the gate: run both real synthetic C11
        # children and let the independent audit replay all private files.
        # A fixture hook changes only the returned *aggregate* before the
        # orchestrator issues its strict receipt, never the native files.
        real_audit = two_live.audit
        def falsify_after_replay(*args, **kwargs):
            result = real_audit(*args, **kwargs)
            return {**result, "different_gpu_before_vram_snapshots": 1}
        with patch.object(two_live, "audit", side_effect=falsify_after_replay):
            with self.assertRaisesRegex(ValueError, "not bit-exact"):
                self.run_two(require_identical_gpu_timeline=True)
        self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
        self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
        self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
        self.assertEqual(len(list(self.dirs[3].iterdir())), 3)

    def test_capture_return_must_match_canonical_published_receipt(self):
        # The actual C11 child has already published its two native GPU
        # artifacts and frame metadata under owner-private directories.
        # A compromised callback could alter the in-memory CAPTURE
        # return object without changing the canonical on-disk receipt.
        # Refuse even if the modified metadata field was not consumed by
        # the later GPU/VRAM repeatability auditor.
        for field, forged in (
            ("gpu_journal_same_elf_launch_requested", False),
            ("terminal_after_vram_matched", False),
            ("kernel_observed_pinned_elf_before_stream", False),
            ("child_stdout_pipe_frame_received", False),
            ("retail_gameplay_authenticated", True),
            ("gpu_journal_pairs_verified", 2),
        ):
            with self.subTest(field=field):
                for directory in self.dirs:
                    for entry in directory.iterdir():
                        entry.unlink()
                calls = []
                def change_return_only(*args, **kwargs):
                    result = original_capture(*args, **kwargs)
                    calls.append(1)
                    return {**result, field: forged}
                with patch.object(two_live, "capture",
                                  side_effect=change_return_only):
                    with self.assertRaisesRegex(
                            ValueError, "differs from published receipt"):
                        self.run_two()
                # The FIRST child really did publish evidence, but a
                # mismatch at the earliest boundary blocks second launch.
                self.assertEqual(calls, [1])
                self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
                self.assertEqual(list(self.dirs[2].iterdir()), [])
                self.assertEqual(list(self.dirs[3].iterdir()), [])

    def test_public_audit_summary_refuses_private_data_and_unknown_fields(self):
        # Independently verified synthetic C11/VRAM captures produce a
        # digest-only summary, which is the ONLY approved public egress
        # schema. Neither mode may forward private paths, raw pixel bytes,
        # arbitrary new keys or malformed/overstated claim types.
        valid = self.run_two(require_identical_gpu_timeline=True)
        # Reconstruct the original auditor-shaped part (the runner adds
        # only its own small set of explicit receipt claims).
        raw = {key: valid[key] for key in two_live._AUDIT_SAFE_KEYS}
        # The two-run launcher deliberately replaces the audit schema
        # with its distinct successful-public-receipt schema. Restore
        # only that label when unit-testing the internal audit contract.
        self.assertEqual(valid["schema"], two_live.SCHEMA)
        raw["schema"] = two_live.AUDIT_SCHEMA
        two_live._require_safe_public_audit_summary(raw)
        cases = (
            ("path", {"private_raw_frame_path":
                      str(self.dirs[0] / "process-frame.bgr555")}),
            ("bytes", {"private_raw_pixels": b"\x01\x02"}),
            ("list", {"private_gpu_records": [{"hex": "abcdef"}]}),
            ("boolean-int", {"gpu_event_records_compared": True}),
            ("malformed-sha", {"first_gpu_journal_sha256": "x" * 64}),
            ("negative-index", {"first_joint_gpu_divergence_index": -1}),
            ("forged-provenance", {"private_pixel_bytes_or_paths_emitted": True}),
            ("bad-enum", {"first_joint_gpu_divergence_kind":
                          "/private/retail-game"}),
            ("missing-key", None),
        )
        for title, mutation in cases:
            with self.subTest(title=title):
                altered = dict(raw)
                if mutation is None:
                    del altered["private_pixel_bytes_or_paths_emitted"]
                else:
                    altered.update(mutation)
                with self.assertRaisesRegex(ValueError, "summary fields unsafe"):
                    two_live._require_safe_public_audit_summary(altered)

    def test_full_two_run_never_emits_unapproved_audit_fields(self):
        # Repeat two real ELF captures and independent GPU replays.
        # Falsify only the *returned* post-audit summary to simulate a
        # future accidental addition of user-private data; on-disk native
        # evidence remains intact. Test both diagnostic and strict paths.
        real_audit = two_live.audit
        for strict in (False, True):
            with self.subTest(strict=strict):
                for folder in self.dirs:
                    for entry in folder.iterdir():
                        entry.unlink()
                def leak_after_replay(*args, **kwargs):
                    actual = real_audit(*args, **kwargs)
                    return {
                        **actual,
                        "private_gpu_events_path":
                            str(self.dirs[1] / "gpu-native-events.jsonl"),
                    }
                with patch.object(two_live, "audit",
                                  side_effect=leak_after_replay):
                    with self.assertRaisesRegex(
                            ValueError, "summary fields unsafe") as caught:
                        self.run_two(
                            require_identical_gpu_timeline=strict)
                self.assertNotIn(str(self.dirs[1]), str(caught.exception))
                self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
                self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[3].iterdir())), 3)

    def test_native_launch_receipts_reject_forged_post_replay_source_labels(self):
        # Both actual Linux C11 captures and both full replays are valid.
        # Mutate ONLY the returned source-labelled audit claims, after
        # replay and before the two-run orchestrator joins its receipts.
        # Even two identical but forged SHA-256 values must be refused,
        # in strict AND ordinary diagnostic mode.
        cases = (
            ("both-journals", True, {
                "first_gpu_journal_sha256": "0" * 64,
                "second_gpu_journal_sha256": "0" * 64,
            }),
            ("both-frames", True, {
                "first_image_sha256": "0" * 64,
                "second_image_sha256": "0" * 64,
            }),
            ("one-gpu-pair-count", False, {
                "first_gpu_pairs_verified": 2,
            }),
        )
        real_audit = two_live.audit
        for title, strict, altered in cases:
            with self.subTest(title=title):
                for folder in self.dirs:
                    for entry in folder.iterdir():
                        entry.unlink()
                def forged_report(*args, **kwargs):
                    actual = real_audit(*args, **kwargs)
                    return {**actual, **altered}
                with patch.object(two_live, "audit",
                                  side_effect=forged_report):
                    with self.assertRaisesRegex(
                            ValueError, "pinned capture receipts"):
                        self.run_two(
                            require_identical_gpu_timeline=strict)
                self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
                self.assertEqual(len(list(self.dirs[3].iterdir())), 3)

    def test_dry_run_private_preflight_is_read_only_and_unattested(self):
        # The exact four 0700 paths and ELF digest can be checked without
        # running the synthetic C11 producer, creating GPU files, or issuing
        # a report that claims any live capture has been authenticated.
        args = ["two-pair"]
        with (patch.object(two_live, "capture",
                           side_effect=AssertionError("unexpected launch")),
              patch.object(two_live, "audit",
                           side_effect=AssertionError("unexpected replay"))):
            report = two_live.preflight(
                self.executable, *self.dirs, frame=123,
                executable_sha256=self.digest, args=args,
                timeout=8, require_identical_gpu_timeline=True)
        self.assertEqual(report["schema"],
                         "vh.map02.private-two-live-elf-preflight.v1")
        self.assertEqual(report["executable_sha256"], self.digest)
        self.assertTrue(report[
            "four_owner_private_empty_directory_roles_verified"])
        self.assertTrue(report["same_elf_arguments_validated"])
        self.assertTrue(report["strict_gpu_timeline_match_requested"])
        for key in ("native_elf_launched",
                    "two_native_elf_captures_and_complete_replays_verified",
                    "strict_gpu_timeline_match_verified",
                    "actual_gameplay_rendering_authenticated",
                    "ps1_hardware_pixel_equivalence_verified",
                    "hd_replacement_authorized",
                    "private_pixel_bytes_or_paths_emitted"):
            self.assertFalse(report[key], key)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))
        for folder in self.dirs:
            self.assertNotIn(str(folder), json.dumps(report))
        self.assertNotIn(str(self.executable), json.dumps(report))
        self.assertNotIn("two-pair", json.dumps(report))
        # A later real capture must still validate inputs independently.
        result = self.run_two(args=args, require_identical_gpu_timeline=True)
        self.assertTrue(result["strict_gpu_timeline_match_verified"])

    def test_dry_run_refuses_wrong_sha_aliases_and_nonempty_destinations(self):
        call = lambda *paths, **kw: two_live.preflight(
            self.executable, *paths, frame=123,
            executable_sha256=kw.pop("sha", self.digest), **kw)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            call(*self.dirs, sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "roles overlap"):
            call(self.dirs[0], self.dirs[1], self.dirs[0], self.dirs[3])
        with self.assertRaisesRegex(ValueError, "arguments invalid"):
            call(*self.dirs, args=["ok", "\x00"])
        with self.assertRaisesRegex(ValueError, "arguments invalid"):
            call(*self.dirs, require_identical_gpu_timeline="true")
        symlink = self.dirs[0].parent / "symlink-journal"
        symlink.symlink_to(self.dirs[3], target_is_directory=True)
        with self.assertRaises(OSError):
            call(self.dirs[0], self.dirs[1], self.dirs[2], symlink)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))
        (self.dirs[3] / "preexisting-private.txt").write_text(
            "must remain unchanged", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not empty"):
            call(*self.dirs)
        self.assertEqual(
            (self.dirs[3] / "preexisting-private.txt").read_text(
                encoding="utf-8"), "must remain unchanged")
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs[:3]))

    def test_private_capture_paths_inside_git_worktree_refused_before_launch(self):
        # A 0700 destination under a version-controlled source tree is
        # still one accidental git-add away from publishing original GPU
        # journals/VRAM. Reject .git directories AND linked-worktree
        # .git files in BOTH the read-only and actual capture paths.
        for git_kind in ("directory", "file"):
            with self.subTest(git_kind=git_kind):
                checkout = self.dirs[0].parent / ("checkout-" + git_kind)
                checkout.mkdir(mode=0o700)
                marker = checkout / ".git"
                if git_kind == "directory":
                    marker.mkdir(mode=0o700)
                else:
                    marker.write_text(
                        "gitdir: /private/git/worktrees/example\\n",
                        encoding="utf-8")
                outputs = [checkout / folder.name for folder in self.dirs]
                for output in outputs:
                    output.mkdir(mode=0o700)
                with patch.object(
                        two_live, "capture",
                        side_effect=AssertionError("ELF must not launch")):
                    for operation in (two_live.preflight, two_live.run):
                        with self.assertRaisesRegex(ValueError, "Git worktree"):
                            operation(
                                self.executable, *outputs, frame=123,
                                executable_sha256=self.digest)
                self.assertTrue(all(not list(p.iterdir()) for p in outputs))

    def test_owner_private_but_nonwritable_capture_dir_is_refused(self):
        # The preflight must not give a false readiness receipt for 0500:
        # owner-only is secure, but a real GPU capture cannot reliably
        # publish the required files there as an unprivileged user.
        output = self.dirs[3]
        output.chmod(0o500)
        with patch.object(two_live, "capture",
                          side_effect=AssertionError("ELF must not launch")):
            for operation in (two_live.preflight, two_live.run):
                with self.assertRaisesRegex(ValueError, "0700"):
                    operation(
                        self.executable, *self.dirs, frame=123,
                        executable_sha256=self.digest)
        self.assertTrue(all(not list(p.iterdir()) for p in self.dirs))

    def test_git_marker_created_mid_preflight_or_before_first_launch_refused(self):
        # A .git marker may appear AFTER the four initial directories
        # passed. The final dry-run check and the per-launch real guard
        # must both detect the new publication risk.
        root = self.dirs[0].parent
        original = two_live._require_held_elf_image
        for operation in (two_live.preflight, two_live.run):
            with self.subTest(operation=operation.__name__):
                marker = root / ".git"
                calls = []
                def mark_before_launch(*args, **kwargs):
                    result = original(*args, **kwargs)
                    calls.append(1)
                    if len(calls) == 1:
                        marker.mkdir(mode=0o700)
                    return result
                try:
                    with (
                        patch.object(two_live, "_require_held_elf_image",
                                     side_effect=mark_before_launch),
                        patch.object(
                            two_live, "capture",
                            side_effect=AssertionError("ELF must not launch")),
                    ):
                        with self.assertRaisesRegex(ValueError, "Git worktree"):
                            operation(
                                self.executable, *self.dirs, frame=123,
                                executable_sha256=self.digest)
                    # The real runner verifies the held ELF once before
                    # the loop and again when entering its first launch.
                    # Dry-run verifies it once before checking directories.
                    # In BOTH cases the newly created .git marker blocks
                    # capture before a child ELF can execute.
                    self.assertEqual(
                        calls, [1] if operation is two_live.preflight
                        else [1, 1])
                    self.assertTrue(all(
                        not list(p.iterdir()) for p in self.dirs))
                finally:
                    marker.rmdir()

    def test_git_worktree_initialized_between_or_after_live_captures_refused(self):
        # Original private C11 evidence is produced by real ELF children.
        # If someone initializes a Git worktree around the private output
        # after the FIRST capture, no second child may launch. If Git
        # appears after the SECOND capture, no independent replay/positive
        # receipt may proceed. Both .git directories and linked-worktree
        # .git files are hazardous even when outputs remain mode 0700.
        root = self.dirs[0].parent
        for after_launch in (1, 2):
            for git_kind in ("directory", "linked-worktree-file"):
                for strict in (False, True):
                    with self.subTest(
                            after_launch=after_launch,
                            git_kind=git_kind, strict=strict):
                        for folder in self.dirs:
                            for file in folder.iterdir():
                                file.unlink()
                        marker = root / ".git"
                        calls = []
                        def make_worktree_after_capture(*args, **kwargs):
                            receipt = original_capture(*args, **kwargs)
                            calls.append(1)
                            if len(calls) == after_launch:
                                if git_kind == "directory":
                                    marker.mkdir(mode=0o700)
                                else:
                                    marker.write_text(
                                        "gitdir: /private/other-worktree\\n",
                                        encoding="utf-8")
                            return receipt
                        try:
                            with (
                                patch.object(
                                    two_live, "capture",
                                    side_effect=make_worktree_after_capture),
                                patch.object(
                                    two_live, "audit",
                                    side_effect=AssertionError(
                                        "replay must not consume Git-published evidence")),
                            ):
                                with self.assertRaisesRegex(
                                        ValueError, "Git worktree") as error:
                                    self.run_two(
                                        require_identical_gpu_timeline=strict)
                            self.assertNotIn(str(root), str(error.exception))
                            self.assertEqual(len(calls), after_launch)
                            self.assertEqual(
                                len(list(self.dirs[0].iterdir())), 2)
                            self.assertEqual(
                                len(list(self.dirs[1].iterdir())), 3)
                            self.assertEqual(
                                len(list(self.dirs[2].iterdir())),
                                2 if after_launch == 2 else 0)
                            self.assertEqual(
                                len(list(self.dirs[3].iterdir())),
                                3 if after_launch == 2 else 0)
                        finally:
                            if marker.is_dir():
                                marker.rmdir()
                            elif marker.exists():
                                marker.unlink()

    def test_final_strict_receipt_guard_rejects_post_gate_mutations(self):
        # Both actual C11 child captures and full independent GPU/VRAM
        # replays have finished, and the strict exactness classifier has
        # returned successfully. A last-moment change must still block the
        # positive receipt: publication inside Git, byte-identical file
        # inode replacement, loss of output permissions, or ELF mutation.
        original_gate = two_live._require_bit_exact_gpu_timeline
        pristine_elf = self.executable
        root = self.dirs[0].parent
        cases = (
            ("git-marker", "Git worktree"),
            ("same-byte-frame-inode", "published files changed"),
            ("directory-mode", "0700"),
            ("elf-mtime", "ELF identity changed"),
        )
        for scenario, error in cases:
            with self.subTest(scenario=scenario):
                for folder in self.dirs:
                    for entry in folder.iterdir():
                        entry.unlink()
                marker = root / ".git"
                elf_copy = root / "local-pinned-elf"
                if scenario == "elf-mtime":
                    shutil.copy2(pristine_elf, elf_copy)
                    self.executable = elf_copy
                gate_calls = []
                def alter_after_gpu_gate(report):
                    original_gate(report)
                    gate_calls.append(1)
                    if scenario == "git-marker":
                        marker.mkdir(mode=0o700)
                    elif scenario == "same-byte-frame-inode":
                        target = self.dirs[0] / "process-frame.bgr555"
                        replacement = self.dirs[0] / "same-bytes-new-inode"
                        replacement.write_bytes(target.read_bytes())
                        replacement.chmod(0o600)
                        os.replace(replacement, target)
                    elif scenario == "directory-mode":
                        self.dirs[3].chmod(0o500)
                    elif scenario == "elf-mtime":
                        info = elf_copy.stat()
                        os.utime(elf_copy, ns=(
                            info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
                try:
                    with patch.object(
                            two_live, "_require_bit_exact_gpu_timeline",
                            side_effect=alter_after_gpu_gate):
                        with self.assertRaisesRegex(ValueError, error) as caught:
                            self.run_two(require_identical_gpu_timeline=True)
                    self.assertEqual(gate_calls, [1])
                    self.assertNotIn(str(root), str(caught.exception))
                    self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                    self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
                    self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
                    self.assertEqual(len(list(self.dirs[3].iterdir())), 3)
                finally:
                    if marker.exists():
                        marker.rmdir()
                    self.dirs[3].chmod(0o700)
                    self.executable = pristine_elf
                    if elf_copy.exists():
                        elf_copy.unlink()

    def test_dry_run_cli_prints_only_safe_readiness_fields(self):
        cmd = [
            sys.executable, "-m", "tools.run_map02_private_two_live_captures",
            "--executable", str(self.executable),
            "--executable-sha256", self.digest,
            "--first-frame", str(self.dirs[0]),
            "--first-journal", str(self.dirs[1]),
            "--second-frame", str(self.dirs[2]),
            "--second-journal", str(self.dirs[3]),
            "--frame", "123", "--dry-run",
            "--require-identical-gpu-timeline",
        ]
        completed = subprocess.run(cmd, text=True, capture_output=True,
                                   timeout=16)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertFalse(report["native_elf_launched"])
        self.assertTrue(report["strict_gpu_timeline_match_requested"])
        self.assertFalse(report["strict_gpu_timeline_match_verified"])
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))
        for folder in (*self.dirs, self.executable):
            self.assertNotIn(str(folder), completed.stdout)
            self.assertNotIn(str(folder), completed.stderr)
        cmd[cmd.index("--executable") + 1] = str(
            self.dirs[0].parent / "private-missing-game-elf")
        failed = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=12)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("failed verification", failed.stderr)
        self.assertNotIn(str(self.dirs[0].parent), failed.stderr)
        self.assertTrue(all(not list(folder.iterdir()) for folder in self.dirs))

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

    def test_identical_byte_native_gpu_file_swaps_after_second_publication_fail(self):
        # A SHA-256-only comparison could accept a newly published inode
        # containing identical GPU bytes. The two-live-run orchestrator
        # instead pins each journal's entire original inode inventory.
        # Replace only a single GPU file AFTER the second real C11 child
        # has completed, before the independent replay receives evidence.
        for name in ("gpu-native-events.jsonl", "gpu-0000-vram.bin",
                     "gpu-0001-vram.bin"):
            with self.subTest(target=name):
                for folder in self.dirs:
                    for entry in folder.iterdir():
                        entry.unlink()
                calls = []
                def swap_first_journal_after_second(*args, **kwargs):
                    receipt = original_capture(*args, **kwargs)
                    calls.append(1)
                    if len(calls) == 2:
                        target = self.dirs[1] / name
                        replacement = self.dirs[1] / "new-identical-inode"
                        replacement.write_bytes(target.read_bytes())
                        replacement.chmod(0o600)
                        os.replace(replacement, target)
                    return receipt
                with patch.object(two_live, "capture",
                                  side_effect=swap_first_journal_after_second):
                    with self.assertRaisesRegex(
                            ValueError, "published files changed"):
                        self.run_two(require_identical_gpu_timeline=True)
                self.assertEqual(calls, [1, 1])
                self.assertEqual(len(list(self.dirs[0].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[2].iterdir())), 2)
                self.assertEqual(len(list(self.dirs[1].iterdir())), 3)
                self.assertEqual(len(list(self.dirs[3].iterdir())), 3)
                # Refusal happens before any successful strict receipt.
                # The user-private capture files remain for diagnosis.

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
