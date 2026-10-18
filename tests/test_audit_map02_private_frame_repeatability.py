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
from tools import run_map02_private_two_live_captures as two_live


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
        # Modify valid JSONL metadata inside the actual child process,
        # keeping the same compiled ELF and replaying both source captures.
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
                raise RuntimeError("MAP02 synthetic GPU event anchor drift")
            updated = updated.replace(old_c, new_c)
        before = 'if (!write_image(dir, "gpu-0000-vram.bin")) return 43;'
        if updated.count(before) != 1:
            raise RuntimeError("MAP02 C11 before-snapshot anchor drift")
        updated = updated.replace(
            before,
            'if (argc > 1 && (!strcmp(argv[1], "alternate-before") || '
            '!strcmp(argv[1], "alternate-event-before"))) '
            'native_vram[0][0] = 0x1234;\n        '
            'if (argc > 1 && !strcmp(argv[1], "alternate-before-stp")) '
            'native_vram[0][0] = 0x8000;\n        ' + before)
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
        self.assertTrue(result["repeated_gpu_event_records_identical"])
        self.assertEqual(result["different_gpu_event_records_in_common_prefix"], 0)
        self.assertIsNone(result["first_different_gpu_event_record_index"])
        self.assertIsNone(result["first_joint_gpu_divergence_index"])
        self.assertIsNone(result["first_joint_gpu_divergence_kind"])
        self.assertEqual(result["gpu_event_records_compared"], 2)
        # The strict acceptance function sees the independently replayed
        # two-child report, not a hand-authored boolean-only fixture.
        two_live._require_bit_exact_gpu_timeline(result)
        self.assertTrue(result["two_full_replays_per_capture_verified"])
        self.assertTrue(result["four_private_file_inventories_stable_through_replays"])
        self.assertTrue(result["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertTrue(result["gpu_vram_timeline_commitments_identical"])
        self.assertEqual(result["first_gpu_vram_timeline_sha256"],
                         result["second_gpu_vram_timeline_sha256"])
        self.assertEqual(len(result["first_gpu_vram_timeline_sha256"]), 64)
        self.assertEqual(result["first_gpu_vram_snapshot_count"], 2)
        self.assertEqual(result["second_gpu_vram_snapshot_count"], 2)
        self.assertEqual(result["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(result["different_gpu_vram_snapshots_in_common_prefix"], 0)
        self.assertEqual(result["different_gpu_before_vram_snapshots"], 0)
        self.assertEqual(result["different_gpu_after_vram_snapshots"], 0)
        self.assertIsNone(result["first_different_gpu_vram_snapshot_index"])
        self.assertIsNone(result["last_different_gpu_vram_snapshot_index"])
        self.assertIsNone(result["first_reconverged_gpu_vram_snapshot_index"])
        self.assertEqual(result["gpu_vram_equal_different_state_transitions"], 0)
        self.assertFalse(result["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertFalse(result["gpu_vram_divergence_reappeared_after_reconvergence"])
        self.assertIsNone(result["first_different_gpu_draw_pair_index"])
        self.assertIsNone(result["first_different_gpu_snapshot_phase"])
        self.assertIsNone(result["first_different_gpu_snapshot_changed_pixels"])
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
        self.assertEqual(out["last_different_gpu_vram_snapshot_index"], 1)
        self.assertIsNone(out["first_reconverged_gpu_vram_snapshot_index"])
        self.assertEqual(out["gpu_vram_equal_different_state_transitions"], 1)
        self.assertFalse(out["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertFalse(out["gpu_vram_divergence_reappeared_after_reconvergence"])
        self.assertEqual(out["first_different_gpu_draw_pair_index"], 0)
        self.assertEqual(out["first_different_gpu_snapshot_phase"], "after")
        self.assertEqual(out["first_different_gpu_snapshot_changed_pixels"], 1)
        self.assertEqual(out["first_different_gpu_snapshot_changed_scanlines"], 1)
        self.assertEqual(out["first_different_gpu_snapshot_stp_bit_differences"], 0)
        self.assertEqual(out["different_gpu_before_vram_snapshots"], 0)
        self.assertEqual(out["different_gpu_after_vram_snapshots"], 1)
        self.assertFalse(out["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertFalse(out["gpu_vram_timeline_commitments_identical"])
        self.assertNotEqual(out["first_gpu_vram_timeline_sha256"],
                            out["second_gpu_vram_timeline_sha256"])
        # Event JSONL captures draw order and attributes, but NOT raw
        # post-draw VRAM pixels. The same two events can write different
        # pixels while the JSONL digest stays byte-identical.
        self.assertTrue(out["repeated_gpu_event_journal_identical"])
        self.assertTrue(out["repeated_gpu_event_records_identical"])
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "vram-only")
        self.assertEqual(out["first_joint_gpu_divergence_index"], 1)
        self.assertEqual(out["first_joint_gpu_divergence_phase"], "after")

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
        self.assertFalse(result["gpu_vram_timeline_commitments_identical"])
        self.assertNotEqual(result["first_gpu_vram_timeline_sha256"],
                            result["second_gpu_vram_timeline_sha256"])
        self.assertEqual(result["different_bgr555_pixels"], 0)
        self.assertEqual(result["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(result["different_gpu_vram_snapshots_in_common_prefix"], 1)
        self.assertEqual(result["first_different_gpu_vram_snapshot_index"], 0)
        self.assertEqual(result["last_different_gpu_vram_snapshot_index"], 0)
        self.assertEqual(result["first_reconverged_gpu_vram_snapshot_index"], 1)
        self.assertEqual(result["gpu_vram_equal_different_state_transitions"], 1)
        self.assertTrue(result["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertFalse(result["gpu_vram_divergence_reappeared_after_reconvergence"])
        self.assertEqual(result["first_different_gpu_draw_pair_index"], 0)
        self.assertEqual(result["first_different_gpu_snapshot_phase"], "before")
        self.assertEqual(result["first_different_gpu_snapshot_changed_pixels"], 1)
        self.assertEqual(result["first_different_gpu_snapshot_changed_scanlines"], 1)
        self.assertEqual(result["first_different_gpu_snapshot_stp_bit_differences"], 0)
        self.assertEqual(result["different_gpu_before_vram_snapshots"], 1)
        self.assertEqual(result["different_gpu_after_vram_snapshots"], 0)
        self.assertEqual(result["unmatched_gpu_vram_snapshots"], 0)

    def test_transient_before_vram_stp_only_difference_is_counted(self):
        # A single semitransparency-bit difference in *intermediate* VRAM
        # must not be hidden by the identical terminal image or event log.
        for folder in (self.f2, self.j2):
            for path in folder.iterdir():
                path.unlink()
        self.capture(self.f2, self.j2, "alternate-before-stp")
        result = self.run_repeat()
        self.assertTrue(result["repeated_native_frame_pixels_identical"])
        self.assertTrue(result["repeated_gpu_event_journal_identical"])
        self.assertEqual(result["different_bgr555_pixels"], 0)
        self.assertEqual(result["first_different_gpu_snapshot_phase"], "before")
        self.assertEqual(result["first_reconverged_gpu_vram_snapshot_index"], 1)
        self.assertTrue(result["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertEqual(result["first_different_gpu_snapshot_changed_pixels"], 1)
        self.assertEqual(result["first_different_gpu_snapshot_changed_scanlines"], 1)
        self.assertEqual(result["first_different_gpu_snapshot_stp_bit_differences"], 1)
        self.assertEqual(result["different_gpu_before_vram_snapshots"], 1)
        self.assertEqual(result["different_gpu_after_vram_snapshots"], 0)

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
            diagnostics = repeat._gpu_snapshot_differences(
                1, 2, 1, 2, lambda: None)
        self.assertEqual(diagnostics["gpu_vram_snapshots_compared"], 2)
        self.assertEqual(diagnostics["unmatched_gpu_vram_snapshots"], 2)
        self.assertFalse(diagnostics["gpu_vram_timeline_commitments_identical"])
        self.assertNotEqual(diagnostics["first_gpu_vram_timeline_sha256"],
                            diagnostics["second_gpu_vram_timeline_sha256"])
        self.assertFalse(
            diagnostics["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertEqual(diagnostics["different_gpu_vram_snapshots_in_common_prefix"], 0)
        self.assertIsNone(diagnostics["first_different_gpu_vram_snapshot_index"])
        self.assertIsNone(diagnostics["last_different_gpu_vram_snapshot_index"])
        self.assertIsNone(diagnostics["first_reconverged_gpu_vram_snapshot_index"])
        self.assertEqual(diagnostics["gpu_vram_equal_different_state_transitions"], 0)
        self.assertFalse(diagnostics["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertIsNone(diagnostics["first_different_gpu_snapshot_phase"])
        self.assertIsNone(diagnostics["first_different_gpu_snapshot_changed_pixels"])

    def test_two_draw_pairs_show_recovery_then_repeat_divergence(self):
        # Four synthetic snapshots: different, equal, different, equal.
        # The index is an ordinal GPU snapshot, never a pixel coordinate.
        pixel_count = 1024 * 512 * 2
        clean = b"\x00" * pixel_count
        one_pixel = b"\x01" + clean[1:]
        def source(fd, name):
            index = int(name[4:8])
            raw = (one_pixel if fd == 2 and index in (0, 2) else clean)
            return raw, ("synthetic", index)
        checked = []
        with patch.object(repeat, "_private_raw", side_effect=source):
            report = repeat._gpu_snapshot_differences(
                1, 2, 2, 2, lambda: checked.append(True))
        self.assertEqual(len(checked), 4)
        self.assertEqual(report["different_gpu_vram_snapshots_in_common_prefix"], 2)
        self.assertEqual(report["first_different_gpu_vram_snapshot_index"], 0)
        self.assertEqual(report["last_different_gpu_vram_snapshot_index"], 2)
        self.assertEqual(report["first_reconverged_gpu_vram_snapshot_index"], 1)
        self.assertEqual(report["gpu_vram_equal_different_state_transitions"], 3)
        self.assertTrue(report["gpu_vram_divergence_reappeared_after_reconvergence"])
        self.assertTrue(report["gpu_vram_reconverged_at_common_prefix_end"])
        self.assertFalse(report["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertEqual(report["first_different_gpu_snapshot_changed_pixels"], 1)

    def test_two_draw_pairs_can_diverge_and_never_reconverge(self):
        count = 1024 * 512 * 2
        clean = b"\x00" * count
        altered = b"\x01" + clean[1:]
        def source(fd, name):
            return (altered if fd == 2 else clean), ("synthetic", name)
        with patch.object(repeat, "_private_raw", side_effect=source):
            report = repeat._gpu_snapshot_differences(
                1, 2, 2, 2, lambda: None)
        self.assertEqual(report["different_gpu_vram_snapshots_in_common_prefix"], 4)
        self.assertEqual(report["last_different_gpu_vram_snapshot_index"], 3)
        self.assertIsNone(report["first_reconverged_gpu_vram_snapshot_index"])
        self.assertEqual(report["gpu_vram_equal_different_state_transitions"], 0)
        self.assertFalse(report["gpu_vram_divergence_reappeared_after_reconvergence"])
        self.assertFalse(report["gpu_vram_reconverged_at_common_prefix_end"])

    def test_vram_snapshot_aggregate_rejects_inconsistent_phase_and_recovery(self):
        # Four fully synthetic VRAM buffers yield this timeline:
        # different, equal, different, equal. The public aggregate must
        # remain arithmetically coherent even after a future refactor.
        clean = b"\x00" * (1024 * 512 * 2)
        changed = b"\x01" + clean[1:]
        def source(fd, name):
            index = int(name[4:8])
            value = changed if fd == 2 and index in (0, 2) else clean
            return value, ("synthetic", index)
        with patch.object(repeat, "_private_raw", side_effect=source):
            good = repeat._gpu_snapshot_differences(
                1, 2, 2, 2, lambda: None)
        repeat._require_gpu_snapshot_aggregate_consistency(good)
        mutations = (
            ("different_gpu_before_vram_snapshots", 1),
            ("different_gpu_after_vram_snapshots", 1),
            ("different_gpu_vram_snapshots_in_common_prefix", True),
            ("gpu_vram_equal_different_state_transitions", 4),
            ("first_different_gpu_vram_snapshot_index", None),
            ("last_different_gpu_vram_snapshot_index", 0),
            ("first_reconverged_gpu_vram_snapshot_index", 0),
            ("gpu_vram_divergence_reappeared_after_reconvergence", False),
            ("gpu_vram_reconverged_at_common_prefix_end", False),
            ("first_gpu_vram_timeline_sha256", "X" * 64),
            ("gpu_vram_timeline_commitments_identical", True),
            ("repeated_full_gpu_vram_snapshot_sequence_identical", True),
            ("first_different_gpu_snapshot_changed_pixels", 0),
            ("first_different_gpu_snapshot_changed_scanlines", True),
            ("first_different_gpu_snapshot_stp_bit_differences", 2),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, "aggregate inconsistent"):
                    repeat._require_gpu_snapshot_aggregate_consistency(
                        {**good, field: value})

    def test_vram_ordered_commitment_must_match_actual_differences(self):
        # The raw VRAM bytes were independently replayed before this
        # aggregate is constructed. Even mutually self-consistent boolean
        # and digest-field edits must not reverse the measured equality.
        matching = self.run_repeat()
        repeat._require_gpu_snapshot_aggregate_consistency(matching)
        self.assertEqual(
            matching["first_gpu_vram_timeline_sha256"],
            matching["second_gpu_vram_timeline_sha256"])
        forged_mismatch = {
            **matching,
            "second_gpu_vram_timeline_sha256": "0" * 64,
            "gpu_vram_timeline_commitments_identical": False,
            "repeated_full_gpu_vram_snapshot_sequence_identical": False,
        }
        with self.assertRaisesRegex(ValueError, "aggregate inconsistent"):
            repeat._require_gpu_snapshot_aggregate_consistency(forged_mismatch)
        for changed in (
            {"second_gpu_vram_snapshot_count": 4},
            {"first_gpu_vram_snapshot_count": 3},
            {"unmatched_gpu_vram_snapshots": 2},
            {"gpu_vram_snapshots_compared": 4},
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "aggregate inconsistent"):
                    repeat._require_gpu_snapshot_aggregate_consistency(
                        {**matching, **changed})

        # Different BEFORE DrawOTag VRAM, followed by convergence to
        # identical terminal frames: the timeline digests must differ.
        for folder in (self.f2, self.j2):
            for file in folder.iterdir():
                file.unlink()
        self.capture(self.f2, self.j2, "alternate-before")
        different = self.run_repeat()
        repeat._require_gpu_snapshot_aggregate_consistency(different)
        self.assertEqual(different["different_bgr555_pixels"], 0)
        self.assertEqual(
            different["different_gpu_vram_snapshots_in_common_prefix"], 1)
        forged_equality = {
            **different,
            "second_gpu_vram_timeline_sha256":
                different["first_gpu_vram_timeline_sha256"],
            "gpu_vram_timeline_commitments_identical": True,
        }
        with self.assertRaisesRegex(ValueError, "aggregate inconsistent"):
            repeat._require_gpu_snapshot_aggregate_consistency(forged_equality)

    def test_vram_recovery_history_matches_all_synthetic_two_pair_masks(self):
        # Independent 4-position boolean timeline oracle: each GPU pair
        # has a before and after VRAM snapshot, with all 16 possible
        # equal/different histories. No private game bytes enter this test.
        clean = b"\x00" * (1024 * 512 * 2)
        changed = b"\x01" + clean[1:]
        for mask in range(16):
            with self.subTest(mask=mask):
                different = tuple(bool(mask & (1 << n)) for n in range(4))
                def source(fd, name):
                    ordinal = int(name[4:8])
                    raw = changed if fd == 2 and different[ordinal] else clean
                    return raw, ("synthetic", ordinal)
                with (patch.object(repeat, "_private_raw", side_effect=source),
                      patch.object(repeat, "_private_difference",
                                   return_value=(1, 1, 0))):
                    report = repeat._gpu_snapshot_differences(
                        1, 2, 2, 2, lambda: None)
                repeat._require_gpu_snapshot_aggregate_consistency(report)
                differing_ordinals = [i for i, value in enumerate(different)
                                      if value]
                first = differing_ordinals[0] if differing_ordinals else None
                last = differing_ordinals[-1] if differing_ordinals else None
                restored = (
                    next((i for i in range(first + 1, 4)
                          if not different[i]), None)
                    if first is not None else None)
                transitions = sum(different[i] != different[i - 1]
                                  for i in range(1, 4))
                self.assertEqual(
                    report["different_gpu_vram_snapshots_in_common_prefix"],
                    len(differing_ordinals))
                self.assertEqual(report["first_different_gpu_vram_snapshot_index"],
                                 first)
                self.assertEqual(report["last_different_gpu_vram_snapshot_index"],
                                 last)
                self.assertEqual(report["first_reconverged_gpu_vram_snapshot_index"],
                                 restored)
                self.assertEqual(
                    report["gpu_vram_equal_different_state_transitions"],
                    transitions)
                self.assertEqual(
                    report["gpu_vram_divergence_reappeared_after_reconvergence"],
                    restored is not None and last > restored)
                self.assertEqual(
                    report["gpu_vram_reconverged_at_common_prefix_end"],
                    last is not None and last < 3)

    def test_vram_recovery_transitions_cannot_fake_historical_reappearance(self):
        # A valid difference/equality/difference/equality sequence has
        # three transitions and a first recovery at ordinal one.
        clean = b"\x00" * (1024 * 512 * 2)
        changed = b"\x01" + clean[1:]
        def source(fd, name):
            ordinal = int(name[4:8])
            return (changed if fd == 2 and ordinal in (0, 2) else clean), (
                "synthetic", ordinal)
        with (patch.object(repeat, "_private_raw", side_effect=source),
              patch.object(repeat, "_private_difference",
                           return_value=(1, 1, 0))):
            good = repeat._gpu_snapshot_differences(
                1, 2, 2, 2, lambda: None)
        repeat._require_gpu_snapshot_aggregate_consistency(good)
        for changed_report in (
            {"gpu_vram_equal_different_state_transitions": 1},
            {"gpu_vram_equal_different_state_transitions": 2},
            {"first_reconverged_gpu_vram_snapshot_index": None,
             "gpu_vram_divergence_reappeared_after_reconvergence": False},
            {"first_different_gpu_vram_snapshot_index": 1},
        ):
            with self.subTest(changed_report=changed_report):
                with self.assertRaisesRegex(ValueError, "aggregate inconsistent"):
                    repeat._require_gpu_snapshot_aggregate_consistency(
                        {**good, **changed_report})

    def test_two_replay_audit_rejects_corrupted_vram_phase_aggregate(self):
        # Verify the strict aggregate validator is actually applied during
        # the full independent two-run replay and not just in its own test.
        real = repeat._gpu_snapshot_differences
        def falsify_one_phase(*args, **kwargs):
            result = real(*args, **kwargs)
            return {**result, "different_gpu_after_vram_snapshots": 1}
        with patch.object(repeat, "_gpu_snapshot_differences",
                          side_effect=falsify_one_phase):
            with self.assertRaisesRegex(ValueError, "aggregate inconsistent"):
                self.run_repeat()

    def test_first_changed_gpu_event_record_phase_is_aggregate_only(self):
        first = (b'{"record":"a"}', b'{"record":"b"}',
                 b'{"record":"c"}', b'{"record":"d"}')
        second = (b'{"record":"a"}', b'{"record":"b"}',
                  b'{"record":"c"}', b'{"record":"DIFFERENT"}')
        def fake_lines(fd, digest):
            return first if fd == 1 else second
        checked = []
        with patch.object(repeat, "_private_gpu_event_lines",
                          side_effect=fake_lines):
            report = repeat._gpu_event_differences(
                1, 2, "a" * 64, "b" * 64, 2, 2,
                lambda: checked.append(True))
        self.assertEqual(len(checked), 1)
        self.assertEqual(report["first_different_gpu_event_record_index"], 3)
        self.assertEqual(report["first_different_gpu_event_pair_index"], 1)
        self.assertEqual(report["first_different_gpu_event_phase"], "after")
        self.assertEqual(report["different_gpu_event_records_in_common_prefix"], 1)
        self.assertFalse(report["repeated_gpu_event_records_identical"])
        self.assertNotIn("DIFFERENT", str(report))
        # The public aggregate field names legitimately include "records";
        # only private JSONL payload keys/values must stay unpublished.
        self.assertNotIn('"record":', json.dumps(report))

    def test_gpu_event_records_with_unmatched_tail_cannot_claim_equality(self):
        first = (b"a", b"b")
        second = (b"a", b"b", b"c", b"d")
        with patch.object(repeat, "_private_gpu_event_lines",
                          side_effect=lambda fd, digest: first if fd == 1 else second):
            report = repeat._gpu_event_differences(
                1, 2, "a" * 64, "b" * 64, 1, 2, lambda: None)
        self.assertEqual(report["gpu_event_records_compared"], 2)
        self.assertEqual(report["unmatched_gpu_event_records"], 2)
        self.assertEqual(report["different_gpu_event_records_in_common_prefix"], 0)
        self.assertIsNone(report["first_different_gpu_event_record_index"])
        self.assertFalse(report["repeated_gpu_event_records_identical"])

    def test_gpu_event_count_disagrees_with_verified_capture_refused(self):
        with patch.object(repeat, "_private_gpu_event_lines",
                          return_value=[b"a", b"b"]):
            with self.assertRaisesRegex(ValueError, "count disagrees"):
                repeat._gpu_event_differences(
                    1, 2, "a" * 64, "b" * 64, 2, 1, lambda: None)

    def test_two_real_c11_captures_event_only_change_without_vram_change(self):
        for folder in (self.f2, self.j2):
            for path in folder.iterdir():
                path.unlink()
        self.capture(self.f2, self.j2, "alternate-event")
        out = self.run_repeat()
        self.assertTrue(out["repeated_native_frame_pixels_identical"])
        self.assertTrue(out["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertFalse(out["repeated_gpu_event_journal_identical"])
        self.assertFalse(out["repeated_gpu_event_records_identical"])
        self.assertEqual(out["different_gpu_event_records_in_common_prefix"], 2)
        self.assertEqual(out["first_different_gpu_event_record_index"], 0)
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "event-only")
        self.assertEqual(out["first_joint_gpu_divergence_index"], 0)
        self.assertEqual(out["first_joint_gpu_divergence_phase"], "before")
        self.assertEqual(out["different_gpu_vram_snapshots_in_common_prefix"], 0)
        self.assertNotIn('"semi":', json.dumps(out))
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(out)

    def test_two_real_c11_captures_event_and_before_vram_change(self):
        for folder in (self.f2, self.j2):
            for path in folder.iterdir():
                path.unlink()
        self.capture(self.f2, self.j2, "alternate-event-before")
        out = self.run_repeat()
        self.assertTrue(out["repeated_native_frame_pixels_identical"])
        self.assertFalse(out["repeated_full_gpu_vram_snapshot_sequence_identical"])
        self.assertFalse(out["repeated_gpu_event_records_identical"])
        self.assertEqual(out["first_different_gpu_event_record_index"], 0)
        self.assertEqual(out["first_different_gpu_vram_snapshot_index"], 0)
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "event-and-vram")
        self.assertEqual(out["first_joint_gpu_divergence_index"], 0)
        self.assertEqual(out["first_joint_gpu_divergence_pair_index"], 0)
        self.assertEqual(out["first_joint_gpu_divergence_phase"], "before")
        self.assertFalse(out["ps1_hardware_pixel_equivalence_verified"])
        with self.assertRaisesRegex(ValueError, "not bit-exact"):
            two_live._require_bit_exact_gpu_timeline(out)

    def test_first_joint_gpu_divergence_classifies_events_and_vram(self):
        # All indices are ordinal event/snapshot positions (two per pair).
        cases = (
            (None, None, 0, None, None, None),
            (1, 3, 0, "event-only", 1, "after"),
            (3, 0, 0, "vram-only", 0, "before"),
            (2, 2, 0, "event-and-vram", 2, "before"),
            (None, None, 2, "unmatched-tail", 4, "before"),
            (3, None, 2, "event-only", 3, "after"),
        )
        for event_index, vram_index, tail, kind, index, phase in cases:
            with self.subTest(kind=kind, event=event_index, vram=vram_index):
                events = {
                    "first_gpu_event_count": 4,
                    "second_gpu_event_count": 4 + tail,
                    "gpu_event_records_compared": 4,
                    "unmatched_gpu_event_records": tail,
                    "different_gpu_event_records_in_common_prefix":
                        0 if event_index is None else 1,
                    "first_different_gpu_event_record_index": event_index,
                    "first_different_gpu_event_pair_index":
                        None if event_index is None else event_index // 2,
                    "first_different_gpu_event_phase":
                        None if event_index is None else
                        ("before" if event_index % 2 == 0 else "after"),
                }
                snapshots = {
                    "first_gpu_vram_snapshot_count": 4,
                    "second_gpu_vram_snapshot_count": 4 + tail,
                    "gpu_vram_snapshots_compared": 4,
                    "unmatched_gpu_vram_snapshots": tail,
                    "different_gpu_vram_snapshots_in_common_prefix":
                        0 if vram_index is None else 1,
                    "first_different_gpu_vram_snapshot_index": vram_index,
                    "first_different_gpu_draw_pair_index":
                        None if vram_index is None else vram_index // 2,
                    "first_different_gpu_snapshot_phase":
                        None if vram_index is None else
                        ("before" if vram_index % 2 == 0 else "after"),
                }
                out = repeat._joint_gpu_vram_first_divergence(snapshots, events)
                self.assertEqual(out["first_joint_gpu_divergence_kind"], kind)
                self.assertEqual(out["first_joint_gpu_divergence_index"], index)
                self.assertEqual(out["first_joint_gpu_divergence_phase"], phase)
                self.assertEqual(out["first_joint_gpu_divergence_pair_index"],
                                 None if index is None else index // 2)

    def test_first_joint_gpu_divergence_rejects_unpaired_evidence(self):
        events = {
            "first_gpu_event_count": 2,
            "second_gpu_event_count": 4,
            "gpu_event_records_compared": 2,
            "unmatched_gpu_event_records": 2,
            "different_gpu_event_records_in_common_prefix": 0,
            "first_different_gpu_event_record_index": None,
            "first_different_gpu_event_pair_index": None,
            "first_different_gpu_event_phase": None,
        }
        snapshots = {
            "first_gpu_vram_snapshot_count": 2,
            "second_gpu_vram_snapshot_count": 2,
            "gpu_vram_snapshots_compared": 2,
            "unmatched_gpu_vram_snapshots": 0,
            "different_gpu_vram_snapshots_in_common_prefix": 0,
            "first_different_gpu_vram_snapshot_index": None,
            "first_different_gpu_draw_pair_index": None,
            "first_different_gpu_snapshot_phase": None,
        }
        with self.assertRaisesRegex(ValueError, "timeline counts disagree"):
            repeat._joint_gpu_vram_first_divergence(snapshots, events)

    def test_joint_gpu_divergence_rejects_malformed_aggregate_counts(self):
        events = {
            "first_gpu_event_count": 4,
            "second_gpu_event_count": 4,
            "gpu_event_records_compared": 4,
            "unmatched_gpu_event_records": 0,
            "different_gpu_event_records_in_common_prefix": 0,
            "first_different_gpu_event_record_index": None,
            "first_different_gpu_event_pair_index": None,
            "first_different_gpu_event_phase": None,
        }
        snapshots = {
            "first_gpu_vram_snapshot_count": 4,
            "second_gpu_vram_snapshot_count": 4,
            "gpu_vram_snapshots_compared": 4,
            "unmatched_gpu_vram_snapshots": 0,
            "different_gpu_vram_snapshots_in_common_prefix": 0,
            "first_different_gpu_vram_snapshot_index": None,
            "first_different_gpu_draw_pair_index": None,
            "first_different_gpu_snapshot_phase": None,
        }
        self.assertIsNone(repeat._joint_gpu_vram_first_divergence(
            snapshots, events)["first_joint_gpu_divergence_index"])
        invalid = (
            (events, "first_gpu_event_count", True),
            (events, "second_gpu_event_count", 3),
            (events, "gpu_event_records_compared", 0),
            (events, "unmatched_gpu_event_records", -2),
            (snapshots, "first_gpu_vram_snapshot_count", 65),
            (snapshots, "second_gpu_vram_snapshot_count", None),
            (snapshots, "gpu_vram_snapshots_compared", 3),
            (snapshots, "unmatched_gpu_vram_snapshots", 1),
        )
        for source, field, value in invalid:
            with self.subTest(field=field, value=value):
                copy = dict(source)
                copy[field] = value
                observed = repeat._joint_gpu_vram_first_divergence
                with self.assertRaisesRegex(ValueError, "counts invalid"):
                    if source is events:
                        observed(snapshots, copy)
                    else:
                        observed(copy, events)

    def test_joint_gpu_divergence_requires_count_first_index_coherence(self):
        events = {
            "first_gpu_event_count": 4,
            "second_gpu_event_count": 4,
            "gpu_event_records_compared": 4,
            "unmatched_gpu_event_records": 0,
            "different_gpu_event_records_in_common_prefix": 0,
            "first_different_gpu_event_record_index": None,
            "first_different_gpu_event_pair_index": None,
            "first_different_gpu_event_phase": None,
        }
        snapshots = {
            "first_gpu_vram_snapshot_count": 4,
            "second_gpu_vram_snapshot_count": 4,
            "gpu_vram_snapshots_compared": 4,
            "unmatched_gpu_vram_snapshots": 0,
            "different_gpu_vram_snapshots_in_common_prefix": 0,
            "first_different_gpu_vram_snapshot_index": None,
            "first_different_gpu_draw_pair_index": None,
            "first_different_gpu_snapshot_phase": None,
        }
        inconsistent = (
            (events, "different_gpu_event_records_in_common_prefix", 1),
            (events, "different_gpu_event_records_in_common_prefix", True),
            (events, "different_gpu_event_records_in_common_prefix", 5),
            (events, "first_different_gpu_event_record_index", 0),
            (snapshots, "different_gpu_vram_snapshots_in_common_prefix", 1),
            (snapshots, "different_gpu_vram_snapshots_in_common_prefix", -1),
            (snapshots, "different_gpu_vram_snapshots_in_common_prefix", 5),
            (snapshots, "first_different_gpu_vram_snapshot_index", 0),
        )
        for source, field, value in inconsistent:
            with self.subTest(field=field, value=value):
                copy = dict(source)
                copy[field] = value
                with self.assertRaisesRegex(
                        ValueError, "count/first index disagree"):
                    if source is events:
                        repeat._joint_gpu_vram_first_divergence(
                            snapshots, copy)
                    else:
                        repeat._joint_gpu_vram_first_divergence(
                            copy, events)

    def test_joint_gpu_first_position_metadata_and_suffix_are_consistent(self):
        events = {
            "first_gpu_event_count": 4,
            "second_gpu_event_count": 4,
            "gpu_event_records_compared": 4,
            "unmatched_gpu_event_records": 0,
            "different_gpu_event_records_in_common_prefix": 1,
            "first_different_gpu_event_record_index": 3,
            "first_different_gpu_event_pair_index": 1,
            "first_different_gpu_event_phase": "after",
        }
        snapshots = {
            "first_gpu_vram_snapshot_count": 4,
            "second_gpu_vram_snapshot_count": 4,
            "gpu_vram_snapshots_compared": 4,
            "unmatched_gpu_vram_snapshots": 0,
            "different_gpu_vram_snapshots_in_common_prefix": 1,
            "first_different_gpu_vram_snapshot_index": 3,
            "first_different_gpu_draw_pair_index": 1,
            "first_different_gpu_snapshot_phase": "after",
        }
        out = repeat._joint_gpu_vram_first_divergence(snapshots, events)
        self.assertEqual(out["first_joint_gpu_divergence_kind"], "event-and-vram")
        self.assertEqual(out["first_joint_gpu_divergence_index"], 3)
        for source, key, wrong, message in (
            (events, "different_gpu_event_records_in_common_prefix", 2,
             "count/first index disagree"),
            (snapshots, "different_gpu_vram_snapshots_in_common_prefix", 2,
             "count/first index disagree"),
            (events, "first_different_gpu_event_pair_index", 0,
             "first position metadata disagree"),
            (events, "first_different_gpu_event_pair_index", True,
             "first position metadata disagree"),
            (events, "first_different_gpu_event_phase", "before",
             "first position metadata disagree"),
            (snapshots, "first_different_gpu_draw_pair_index", None,
             "first position metadata disagree"),
            (snapshots, "first_different_gpu_snapshot_phase", "before",
             "first position metadata disagree"),
        ):
            with self.subTest(key=key, wrong=wrong):
                broken = dict(source)
                broken[key] = wrong
                with self.assertRaisesRegex(ValueError, message):
                    if source is events:
                        repeat._joint_gpu_vram_first_divergence(snapshots, broken)
                    else:
                        repeat._joint_gpu_vram_first_divergence(broken, events)
        for source, name in (
            (events, "first_different_gpu_event_phase"),
            (snapshots, "first_different_gpu_draw_pair_index"),
        ):
            with self.subTest(missing=name):
                broken = dict(source)
                del broken[name]
                with self.assertRaisesRegex(ValueError, "first position metadata disagree"):
                    if source is events:
                        repeat._joint_gpu_vram_first_divergence(snapshots, broken)
                    else:
                        repeat._joint_gpu_vram_first_divergence(broken, events)

    def test_joint_gpu_divergence_matches_exhaustive_small_timeline_oracle(self):
        # Enumerate all event/VRAM difference masks for 1..3 GPU pairs per
        # independent capture. This is a pure synthetic aggregate model:
        # no private event JSONL, frame pixels, coordinates or game bytes.
        # The reference checks *each chronological ordinal* rather than
        # inferring the first difference from the audit's reported indices.
        tested = 0
        for first_pairs in (1, 2, 3):
            for second_pairs in (1, 2, 3):
                left_count, right_count = 2 * first_pairs, 2 * second_pairs
                common = min(left_count, right_count)
                for event_mask in range(1 << common):
                    for vram_mask in range(1 << common):
                        event_first = next((
                            i for i in range(common)
                            if event_mask & (1 << i)), None)
                        vram_first = next((
                            i for i in range(common)
                            if vram_mask & (1 << i)), None)
                        def position(index):
                            return (None, None) if index is None else (
                                index // 2,
                                "before" if index % 2 == 0 else "after")
                        event_pair, event_phase = position(event_first)
                        vram_pair, vram_phase = position(vram_first)
                        events = {
                            "first_gpu_event_count": left_count,
                            "second_gpu_event_count": right_count,
                            "gpu_event_records_compared": common,
                            "unmatched_gpu_event_records":
                                abs(left_count - right_count),
                            "different_gpu_event_records_in_common_prefix":
                                event_mask.bit_count(),
                            "first_different_gpu_event_record_index": event_first,
                            "first_different_gpu_event_pair_index": event_pair,
                            "first_different_gpu_event_phase": event_phase,
                        }
                        snapshots = {
                            "first_gpu_vram_snapshot_count": left_count,
                            "second_gpu_vram_snapshot_count": right_count,
                            "gpu_vram_snapshots_compared": common,
                            "unmatched_gpu_vram_snapshots":
                                abs(left_count - right_count),
                            "different_gpu_vram_snapshots_in_common_prefix":
                                vram_mask.bit_count(),
                            "first_different_gpu_vram_snapshot_index": vram_first,
                            "first_different_gpu_draw_pair_index": vram_pair,
                            "first_different_gpu_snapshot_phase": vram_phase,
                        }
                        expected_index = expected_kind = None
                        for step in range(max(left_count, right_count)):
                            if step >= common:
                                expected_index = step
                                expected_kind = "unmatched-tail"
                                break
                            event_diff = bool(event_mask & (1 << step))
                            vram_diff = bool(vram_mask & (1 << step))
                            if event_diff or vram_diff:
                                expected_index = step
                                expected_kind = (
                                    "event-and-vram" if event_diff and vram_diff
                                    else "event-only" if event_diff else "vram-only")
                                break
                        expected_pair, expected_phase = position(expected_index)
                        actual = repeat._joint_gpu_vram_first_divergence(
                            snapshots, events)
                        self.assertEqual(
                            (
                                actual["first_joint_gpu_divergence_index"],
                                actual["first_joint_gpu_divergence_pair_index"],
                                actual["first_joint_gpu_divergence_phase"],
                                actual["first_joint_gpu_divergence_kind"],
                            ),
                            (expected_index, expected_pair,
                             expected_phase, expected_kind),
                            msg=(f"pairs={first_pairs}/{second_pairs}, "
                                 f"event_mask={event_mask}, "
                                 f"vram_mask={vram_mask}"))
                        tested += 1
        # (1,2,3) paired captures and all possible 2/4/6-event masks.
        self.assertEqual(tested, 5 * 4**2 + 3 * 4**4 + 4**6)

    def test_independent_native_gpu_audit_is_symmetric_under_capture_order(self):
        # Swap the two *real* replay-verified synthetic native captures, not
        # manually authored report dictionaries. Difference classification
        # and pixel counts must be invariant, while source-labelled hashes
        # and ordered commitments must swap.
        invariant = (
            "first_joint_gpu_divergence_kind",
            "first_joint_gpu_divergence_index",
            "first_joint_gpu_divergence_pair_index",
            "first_joint_gpu_divergence_phase",
            "first_different_gpu_event_record_index",
            "first_different_gpu_vram_snapshot_index",
            "different_gpu_event_records_in_common_prefix",
            "different_gpu_vram_snapshots_in_common_prefix",
            "different_bgr555_pixels",
            "changed_scanlines",
            "stp_bit_differences",
            "repeated_native_frame_pixels_identical",
            "repeated_gpu_event_records_identical",
            "repeated_full_gpu_vram_snapshot_sequence_identical",
        )
        swapped = (
            ("first_image_sha256", "second_image_sha256"),
            ("first_gpu_journal_sha256", "second_gpu_journal_sha256"),
            ("first_gpu_vram_timeline_sha256",
             "second_gpu_vram_timeline_sha256"),
            ("first_gpu_event_count", "second_gpu_event_count"),
            ("first_gpu_vram_snapshot_count",
             "second_gpu_vram_snapshot_count"),
        )
        cases = (
            ("alternate-event", "event-only", 0),
            ("alternate-before", "vram-only", 0),
            ("alternate", "vram-only", 1),
            ("alternate-event-before", "event-and-vram", 0),
        )
        for variant, kind, first_index in cases:
            with self.subTest(variant=variant):
                for folder in (self.f2, self.j2):
                    for file in folder.iterdir():
                        file.unlink()
                self.capture(self.f2, self.j2, variant)
                forward = self.run_repeat()
                reverse = repeat.audit(
                    self.f2, self.j2, self.f1, self.j1, self.executable)
                self.assertEqual(
                    forward["first_joint_gpu_divergence_kind"], kind)
                self.assertEqual(
                    forward["first_joint_gpu_divergence_index"], first_index)
                for key in invariant:
                    self.assertEqual(
                        forward[key], reverse[key], msg=(variant, key))
                for first_key, second_key in swapped:
                    self.assertEqual(
                        forward[first_key], reverse[second_key],
                        msg=(variant, first_key, second_key))
                    self.assertEqual(
                        forward[second_key], reverse[first_key],
                        msg=(variant, second_key, first_key))
                for folder in (self.f1, self.j1, self.f2, self.j2):
                    self.assertNotIn(str(folder), json.dumps(forward))
                    self.assertNotIn(str(folder), json.dumps(reverse))
                self.assertFalse(forward["hd_replacement_authorized"])
                self.assertFalse(reverse["hd_replacement_authorized"])

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
