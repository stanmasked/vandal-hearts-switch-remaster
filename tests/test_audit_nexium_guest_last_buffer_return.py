"""Stage313 original guest last page-return software-only chronology controls."""
from __future__ import annotations
import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_guest_exit_timeline import (
    ExitTimelineError, parse_exit_csv, SUBDIR,
)
from audit_nexium_guest_last_buffer_return import (
    COMPLETE,NOT_OBSERVED,audit_source,audit_guest,
)

NAMES=("page_return_count","last_page_return_guest_ns","last_page_frames",
       "tail_attempt_guest_ns","tail_success_return_guest_ns")

def csv(*values):
    return ("event,value\n"+"".join(f"{k},{n}\n" for k,n in zip(NAMES,values))).encode()

def exit_report():
    raw=("event,guest_monotonic_ns\n"
         "plus_observed,100000\nstop_requested,100700\n"
         "worker_cleanup_entered,115700\naudout_closed,126700\n"
         "worker_joined,130700\n").encode()
    return parse_exit_csv(raw)

class OriginalLastPageSynthetic(unittest.TestCase):
    def setUp(self):
        self.exit=exit_report()

    def test_last_page_before_plus_is_only_guest_software_evidence(self):
        r=audit_source(csv(300,99000,128,0,0),self.exit)
        self.assertEqual(r["result"],COMPLETE)
        self.assertEqual(r["last_page_position_relative_to_guest_exit"],
                         "last_page_returned_before_Plus_observed")
        self.assertEqual(r["last_page_relative_to_Plus_ns"],-1000)
        self.assertFalse(r["audible_dropout_verified"])

    def test_last_page_after_plus_before_stop_is_distinct(self):
        r=audit_source(csv(310,100350,139,0,0),self.exit)
        self.assertEqual(r["last_page_position_relative_to_guest_exit"],
                         "last_page_returned_after_Plus_before_stop")
        self.assertEqual(r["last_page_relative_to_Plus_ns"],350)

    def test_last_page_after_stop_before_cleanup_not_dac_delivery(self):
        r=audit_source(csv(330,101000,132,0,0),self.exit)
        self.assertEqual(r["last_page_position_relative_to_guest_exit"],
                         "last_page_returned_after_stop_before_cleanup")
        self.assertTrue(r["last_page_return_is_not_DAC_or_speaker_output"])

    def test_exit_tail_bounded_success_timestamp_during_cleanup(self):
        r=audit_source(csv(350,115600,256,118000,119000),self.exit)
        self.assertTrue(r["tail_bounded_attempt_observed"])
        self.assertTrue(r["tail_release_confirmed"])
        self.assertTrue(r["normal_exit_taper_is_not_PS1_SPU_rendered_music"])

    def test_zero_pages_and_failed_tail_are_explicit(self):
        r=audit_source(csv(0,0,0,118000,0),self.exit)
        self.assertEqual(r["last_page_position_relative_to_guest_exit"],
                         "no_successfully_returned_PCM_page_observed")
        self.assertIsNone(r["last_page_return_guest_ns"])
        self.assertFalse(r["tail_release_confirmed"])

    def test_corrupt_csv_fails_closed(self):
        raw=csv(3,100350,128,0,0)
        for broken in (
            raw[:-1],raw.replace(b"\n",b"\r\n"),
            raw.replace(b"last_page_frames",b"other_name"),
            raw+b"last_page_frames,128\n",
            raw.replace(b",3\n",b",03\n"),
            raw.replace(b",3\n",b",-3\n"),
            raw.replace(b",3\n",b",18446744073709551616\n"),
        ):
            with self.subTest(broken=broken[:30]),self.assertRaises(ExitTimelineError):
                audit_source(broken,self.exit)

    def test_counter_and_page_frame_conservation(self):
        for values in (
            (0,100350,128,0,0),
            (1,0,128,0,0),
            (1,100350,0,0,0),
            (1,100350,4097,0,0),
        ):
            with self.subTest(values=values),self.assertRaises(ExitTimelineError):
                audit_source(csv(*values),self.exit)

    def test_reversed_or_late_guest_events_rejected(self):
        for vals in (
            (300,126701,128,0,0),
            (300,100350,128,127000,0),
            (300,100350,128,118000,127000),
            (300,100350,128,0,118000),
            (300,100350,128,118000,117999),
        ):
            with self.subTest(vals=vals),self.assertRaises(ExitTimelineError):
                audit_source(csv(*vals),self.exit)

    def test_missing_real_source_is_not_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            r=audit_guest(root)
            self.assertEqual(r["result"],NOT_OBSERVED)
            self.assertFalse(r["original_guest_page_witness_observed"])

    def test_original_guest_sd_source_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/SUBDIR
            path.mkdir(parents=True)
            (path/"audio-exit-timeline-000.csv").write_bytes(
                ("event,guest_monotonic_ns\n"
                 "plus_observed,100000\nstop_requested,100700\n"
                 "worker_cleanup_entered,115700\naudout_closed,126700\n"
                 "worker_joined,130700\n").encode())
            (path/"audio-exit-output-000.csv").write_bytes(csv(310,100350,128,0,0))
            report=audit_guest(root)
            self.assertEqual(report["result"],COMPLETE)
            self.assertTrue(report["original_guest_page_witness_observed"])
            (path/"audio-exit-output-001.csv").write_bytes(csv(310,100350,128,0,0))
            with self.assertRaises(ExitTimelineError):
                audit_guest(root)

    def test_determinism(self):
        r=audit_source(csv(310,100350,128,0,0),self.exit)
        self.assertEqual(r,audit_source(csv(310,100350,128,0,0),self.exit))
        self.assertIs(r["hardware_Nintendo_Switch_audio_tested"],False)

if __name__=="__main__":
    unittest.main()
