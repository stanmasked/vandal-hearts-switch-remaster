"""Stage314 byte-original audout release CSV preservation source controls."""
from __future__ import annotations
import copy
import hashlib
import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))

from audit_nexium_guest_exit_timeline import SUBDIR, audit_guest_root, ExitTimelineError
from audit_nexium_guest_last_buffer_return import audit_guest, ORIGINAL
from preserve_nexium_guest_last_buffer_original import preserve_original


def guest_exit():
    return ("event,guest_monotonic_ns\n"
            "plus_observed,100000\n"
            "stop_requested,100700\n"
            "worker_cleanup_entered,115700\n"
            "audout_closed,126700\n"
            "worker_joined,130700\n").encode()

def original_page():
    return ("event,value\n"
            "page_return_count,380\n"
            "last_page_return_guest_ns,100350\n"
            "last_page_frames,128\n"
            "tail_attempt_guest_ns,118000\n"
            "tail_success_return_guest_ns,118100\n").encode()

class OriginalBufferArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parent=Path(self.tmp.name)
        self.root=parent/"guest-original"
        directory=self.root/SUBDIR
        directory.mkdir(parents=True)
        self.guest_exit=guest_exit()
        self.guest_page=original_page()
        (directory/"audio-exit-timeline-000.csv").write_bytes(self.guest_exit)
        (directory/ORIGINAL).write_bytes(self.guest_page)
        self.guest307=audit_guest_root(self.root)
        self.guest313=audit_guest(self.root)
        self.s310={
            "result":"ORIGINAL_GUEST_EXIT_CSV_BYTES_PRESERVED_AND_REAUDITED",
            "original_source_csv_bytes_independently_reaudited":True,
            "guest_exit_receipt_sha256":hashlib.sha256(self.guest_exit).hexdigest(),
            "original_guest_exit_csv_size":len(self.guest_exit),
        }
        self.output=parent/"runtime-evidence"/ORIGINAL

    def audit(self, *, root=None,s307=None,s310=None,s313=None,
              prior=None,dest=None):
        return preserve_original(
            self.root if root is None else root,
            self.guest307 if s307 is None else s307,
            self.s310 if s310 is None else s310,
            self.guest313 if s313 is None else s313,
            self.guest_exit if prior is None else prior,
            self.output if dest is None else dest)

    def test_exact_original_page_bytes_and_independent_sha(self):
        r=self.audit()
        self.assertEqual(self.output.read_bytes(),self.guest_page)
        self.assertEqual(r["original_guest_output_csv_sha256"],
                         hashlib.sha256(self.guest_page).hexdigest())
        self.assertTrue(r["source_stage310_original_bytes_reproduced"])
        self.assertEqual(r["last_page_relative_to_Plus_ns"],350)
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_never_overwrite_an_existing_original_copy(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous real source")
        with self.assertRaises(ExitTimelineError):
            self.audit()
        self.assertEqual(self.output.read_bytes(),b"previous real source")

    def test_detect_mutated_original_page_source(self):
        (self.root/SUBDIR/ORIGINAL).write_bytes(
            self.guest_page.replace(b",100350",b",100400"))
        with self.assertRaises(ExitTimelineError):
            self.audit()

    def test_changed_guest_exit_source_rejected(self):
        (self.root/SUBDIR/"audio-exit-timeline-000.csv").write_bytes(
            self.guest_exit.replace(b"100700",b"100800"))
        with self.assertRaises(ExitTimelineError):
            self.audit()

    def test_forged_stage307_hash_rejected(self):
        report=copy.deepcopy(self.guest307)
        report["guest_exit_csv_sha256"]="a"*64
        with self.assertRaises(ExitTimelineError):
            self.audit(s307=report)

    def test_forged_stage310_receipt_rejected(self):
        report=dict(self.s310)
        report["original_source_csv_bytes_independently_reaudited"]=False
        with self.assertRaises(ExitTimelineError):
            self.audit(s310=report)

    def test_mismatched_earlier_stage310_copy_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(prior=self.guest_exit+b"\n")

    def test_forged_stage313_position_rejected(self):
        report=copy.deepcopy(self.guest313)
        report["last_page_relative_to_Plus_ns"]=125
        with self.assertRaises(ExitTimelineError):
            self.audit(s313=report)

    def test_missing_original_buffer_source_rejected(self):
        (self.root/SUBDIR/ORIGINAL).unlink()
        with self.assertRaises(ExitTimelineError):
            self.audit()

    def test_symlink_original_guest_source_rejected(self):
        p=self.root/SUBDIR/ORIGINAL
        relocated=self.root/"previous.csv"
        relocated.write_bytes(self.guest_page)
        p.unlink()
        p.symlink_to(relocated)
        with self.assertRaises(ExitTimelineError):
            self.audit()

    def test_ambiguous_multiple_numbered_guest_sources_rejected(self):
        (self.root/SUBDIR/"audio-exit-output-001.csv").write_bytes(self.guest_page)
        with self.assertRaises(ExitTimelineError):
            self.audit()

    def test_reproducible_report_and_refusal_of_speaker_claim(self):
        first=self.audit()
        self.output.unlink()
        self.assertEqual(first,self.audit())
        self.assertTrue(first["audout_buffer_release_not_speaker_playback"])
        self.assertIs(first["guest_to_host_PCM_clock_calibration_verified"],False)
        self.assertIs(first["original_soundtrack_verified"],False)


if __name__=="__main__":
    unittest.main()
