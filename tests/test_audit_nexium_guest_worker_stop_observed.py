"""Stage317 guest worker-observed mailbox stop against source-audited page."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_exit_timeline import (
    SUBDIR,ExitTimelineError,parse_exit_csv,
)
from audit_nexium_guest_last_buffer_return import audit_source
from audit_nexium_guest_worker_stop_observed import (
    VERIFIED,NOT_OBSERVED,audit_worker_stop_csv,
    audit_worker_source_root,
)


def sources():
    original_exit=("event,guest_monotonic_ns\n"
                   "plus_observed,100000\n"
                   "stop_requested,100700\n"
                   "worker_cleanup_entered,115700\n"
                   "audout_closed,126700\n"
                   "worker_joined,130700\n").encode()
    original_page=("event,value\n"
                   "page_return_count,380\n"
                   "last_page_return_guest_ns,103000\n"
                   "last_page_frames,128\n"
                   "tail_attempt_guest_ns,118000\n"
                   "tail_success_return_guest_ns,118100\n").encode()
    return original_exit,original_page,parse_exit_csv(original_exit),audit_source(
        original_page,parse_exit_csv(original_exit))


class StopObservedTests(unittest.TestCase):
    def setUp(self):
        self.exit_bytes,self.page_bytes,self.exit,self.page=sources()

    def test_worker_observed_stop_after_last_page_before_cleanup(self):
        r=audit_worker_stop_csv(
            b"event,guest_monotonic_ns\nworker_stop_observed,114000\n",
            self.exit,self.page)
        self.assertEqual(r["result"],VERIFIED)
        self.assertEqual(r["stop_request_to_worker_observation_ns"],13300)
        self.assertEqual(r["last_page_return_to_worker_observation_ns"],11000)
        self.assertEqual(r["worker_observation_to_cleanup_ns"],1700)
        self.assertTrue(r["last_buffer_return_not_speaker_playback"])
        self.assertIs(r["guest_to_host_PCM_sample_clock_calibrated"],False)

    def test_unobserved_stop_is_not_a_verified_shutdown(self):
        r=audit_worker_stop_csv(
            b"event,guest_monotonic_ns\nworker_stop_observed,0\n",
            self.exit,self.page)
        self.assertEqual(r["result"],NOT_OBSERVED)
        self.assertIsNone(r["worker_stop_observation_guest_ns"])
        self.assertIsNone(r["last_page_return_to_worker_observation_ns"])

    def test_before_stop_or_before_last_page_rejected(self):
        for ns in (100699,100700,101000,102999):
            with self.subTest(ns=ns),self.assertRaises(ExitTimelineError):
                audit_worker_stop_csv(
                    f"event,guest_monotonic_ns\nworker_stop_observed,{ns}\n".encode(),
                    self.exit,self.page)

    def test_after_cleanup_is_invalid(self):
        with self.assertRaises(ExitTimelineError):
            audit_worker_stop_csv(
                b"event,guest_monotonic_ns\nworker_stop_observed,115701\n",
                self.exit,self.page)

    def test_stop_equal_page_or_cleanup_accepts_nondecreasing_clock(self):
        for ns in (103000,115700):
            r=audit_worker_stop_csv(
                f"event,guest_monotonic_ns\nworker_stop_observed,{ns}\n".encode(),
                self.exit,self.page)
            self.assertEqual(r["result"],VERIFIED)

    def test_noncanonical_csv_is_fatal(self):
        original=b"event,guest_monotonic_ns\nworker_stop_observed,114000\n"
        for raw in (
            original[:-1],original.replace(b"\n",b"\r\n"),
            original.replace(b"worker_stop_observed",b"other_name"),
            original+b"worker_stop_observed,114001\n",
            original.replace(b"114000",b"0114000"),
            original.replace(b"114000",b"-114000"),
            original.replace(b"114000",b"18446744073709551616"),
            original+b"\x00",
        ):
            with self.subTest(raw=raw[:60]),self.assertRaises(ExitTimelineError):
                audit_worker_stop_csv(raw,self.exit,self.page)

    def test_wrong_original_exit_hash_rejected(self):
        guest=dict(self.page)
        guest["original_guest_exit_csv_sha256"]="a"*64
        with self.assertRaises(ExitTimelineError):
            audit_worker_stop_csv(
                b"event,guest_monotonic_ns\nworker_stop_observed,114000\n",
                self.exit,guest)

    def test_missing_guest_SD_original_is_unobserved(self):
        with tempfile.TemporaryDirectory() as folder:
            r,raw=audit_worker_source_root(Path(folder))
            self.assertEqual(r["result"],"GUEST_WORKER_STOP_SD_NOT_OBSERVED")
            self.assertIsNone(raw)
            self.assertFalse(r["original_worker_stop_source_observed"])

    def test_real_guest_original_SD_bytes_and_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            sub=root/SUBDIR
            sub.mkdir(parents=True)
            (sub/"audio-exit-timeline-000.csv").write_bytes(self.exit_bytes)
            (sub/"audio-exit-output-000.csv").write_bytes(self.page_bytes)
            raw=b"event,guest_monotonic_ns\nworker_stop_observed,114000\n"
            (sub/"audio-exit-worker-stop-000.csv").write_bytes(raw)
            result,received=audit_worker_source_root(root)
            self.assertEqual(result["result"],VERIFIED)
            self.assertEqual(received,raw)
            self.assertEqual(result["original_guest_worker_stop_csv_sha256"],
                             hashlib.sha256(raw).hexdigest())

    def test_duplicate_or_symlink_source_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            sub=root/SUBDIR
            sub.mkdir(parents=True)
            (sub/"audio-exit-timeline-000.csv").write_bytes(self.exit_bytes)
            (sub/"audio-exit-output-000.csv").write_bytes(self.page_bytes)
            original=sub/"audio-exit-worker-stop-000.csv"
            raw=b"event,guest_monotonic_ns\nworker_stop_observed,114000\n"
            original.write_bytes(raw)
            (sub/"audio-exit-worker-stop-001.csv").write_bytes(raw)
            with self.assertRaises(ExitTimelineError):
                audit_worker_source_root(root)
            (sub/"audio-exit-worker-stop-001.csv").unlink()
            original.unlink()
            copy=root/"target"
            copy.write_bytes(raw)
            original.symlink_to(copy)
            with self.assertRaises(ExitTimelineError):
                audit_worker_source_root(root)

    def test_repeated_original_source_audit_is_deterministic(self):
        raw=b"event,guest_monotonic_ns\nworker_stop_observed,114000\n"
        self.assertEqual(audit_worker_stop_csv(raw,self.exit,self.page),
                         audit_worker_stop_csv(raw,self.exit,self.page))


if __name__=="__main__":
    unittest.main()
