"""Stage307: optional guest SD trace, not host PCM or audible evidence."""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_nexium_guest_exit_timeline import (
    ExitTimelineError, EVENTS, OBSERVED, UNOBSERVED, SUBDIR,
    parse_exit_csv, audit_guest_root,
)


def csv(*times):
    return ("event,guest_monotonic_ns\n" +
            "".join(f"{k},{v}\n" for k, v in zip(EVENTS, times))).encode("ascii")


class ExitMilestoneSynthetic(unittest.TestCase):
    def setUp(self):
        self.values = (1000, 1050, 1080, 1100, 1150)

    def test_strict_guest_software_order(self):
        r = parse_exit_csv(csv(*self.values))
        self.assertEqual(r["result"], OBSERVED)
        self.assertEqual(r["plus_observed_to_stop_requested_ns"], 50)
        self.assertEqual(r["stop_request_to_worker_cleanup_ns"], 30)
        self.assertEqual(r["worker_cleanup_to_audout_close_ns"], 20)
        self.assertEqual(r["audout_close_to_worker_join_ns"], 50)
        self.assertIs(r["host_PCM_to_guest_timestamp_mapping_verified"], False)

    def test_missing_milestone_distinct_from_ordered_exit(self):
        r = parse_exit_csv(csv(0, 0, 700, 720, 740))
        self.assertEqual(r["result"], "GUEST_EXIT_EVENTS_INCOMPLETE")
        self.assertEqual(r["missing_guest_milestones"],
                         ["plus_observed", "stop_requested"])
        self.assertIsNone(r["stop_request_to_worker_cleanup_ns"])

    def test_incomplete_trace_does_not_hide_reverse_observed_events(self):
        with self.assertRaises(ExitTimelineError):
            parse_exit_csv(csv(0, 0, 800, 750, 900))
        with self.assertRaises(ExitTimelineError):
            parse_exit_csv(csv(0, 0, 800, 800, 900))

    def test_order_reversal_and_equal_time_are_rejected(self):
        for stamps in ((1000, 1050, 1049, 1100, 1150),
                       (1000, 1050, 1050, 1100, 1150)):
            with self.subTest(stamps=stamps), self.assertRaises(ExitTimelineError):
                parse_exit_csv(csv(*stamps))

    def test_invalid_csv_and_overflow_rejected(self):
        original = csv(*self.values)
        for raw in (
            original[:-1],
            original.replace(b"\n", b"\r\n"),
            original.replace(b"plus_observed", b"other", 1),
            original + b"worker_joined,1150\n",
            original.replace(b",1000", b",01000"),
            original.replace(b",1000", b",-1000"),
            original.replace(b",1000", b",18446744073709551616"),
            original.replace(b"event,guest_monotonic_ns", b"kind,ticks"),
        ):
            with self.subTest(raw=raw[:45]), self.assertRaises(ExitTimelineError):
                parse_exit_csv(raw)

    def test_missing_guest_transport_is_explicitly_unobserved(self):
        with tempfile.TemporaryDirectory() as t:
            r = audit_guest_root(Path(t))
            self.assertEqual(r["result"], UNOBSERVED)
            self.assertIs(r["guest_sd_receipt_observed"], False)

    def test_real_guest_file_observed_from_exact_isolated_sd_path(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            folder = root / SUBDIR
            folder.mkdir(parents=True)
            p = folder / "audio-exit-timeline-000.csv"
            p.write_bytes(csv(*self.values))
            r = audit_guest_root(root)
            self.assertEqual(r["result"], OBSERVED)
            self.assertIs(r["guest_sd_receipt_observed"], True)
            self.assertEqual(r["guest_csv_path"],
                             str(SUBDIR / "audio-exit-timeline-000.csv"))
            self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_ambiguous_or_unexpected_numbering_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            folder = root / SUBDIR
            folder.mkdir(parents=True)
            p = folder / "audio-exit-timeline-001.csv"
            p.write_bytes(csv(*self.values))
            with self.assertRaises(ExitTimelineError):
                audit_guest_root(root)
            (folder / "audio-exit-timeline-000.csv").write_bytes(csv(*self.values))
            with self.assertRaises(ExitTimelineError):
                audit_guest_root(root)

    def test_symlink_guest_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            folder = root / SUBDIR
            folder.mkdir(parents=True)
            raw = root / "original.csv"
            raw.write_bytes(csv(*self.values))
            (folder / "audio-exit-timeline-000.csv").symlink_to(raw)
            with self.assertRaises(ExitTimelineError):
                audit_guest_root(root)


if __name__ == "__main__":
    unittest.main()
