#!/usr/bin/env python3
"""Stage362 simulated evidence checks. Real guest/hardware claims are prohibited."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_recorder_stop_dual_clock_stage362 import (
    audit,parse,load_regular,LEGACY,PAIRED,RESULT,RecorderClocksError
)

ORIGINAL=(b"event,pcm_bytes,host_epoch_ms,signal_success\n"
          b"before_sigint,8732688,1792449461974,1\n"
          b"after_wait,8732688,1792449461203,1\n")

def make_pair(wall_second=1792449461203,mono_second=1100000000,
              bytes_second=8732688,signal_second=1):
    return (
        b"event,pcm_bytes,host_epoch_ms,host_monotonic_ns,signal_success\n"
        b"before_sigint,8732688,1792449461974,1000000000,1\n" +
        f"after_wait,{bytes_second},{wall_second},{mono_second},{signal_second}\n".encode()
    )

class Stage362Tests(unittest.TestCase):
    def test_original_nonmonotone_wall_is_never_waived(self):
        p=make_pair()
        doc=audit(ORIGINAL,p)
        self.assertEqual(doc["result"],RESULT)
        self.assertEqual(doc["host_wall_elapsed_ms"],-771)
        self.assertEqual(doc["host_monotonic_elapsed_ns"],100_000_000)
        self.assertTrue(doc["host_wall_clock_moved_backwards"])
        self.assertFalse(doc["strict_stage303_chronology_compatible"])
        self.assertTrue(doc["strict_stage303_source_audit_not_waived"])
        self.assertEqual(doc["legacy_stop_csv_sha256"],hashlib.sha256(ORIGINAL).hexdigest())
    def test_normal_wall_has_only_chronology_compatible_not_full_stage303_claim(self):
        old=ORIGINAL.replace(b"1792449461203",b"1792449462203")
        doc=audit(old,make_pair(wall_second=1792449462203))
        self.assertTrue(doc["strict_stage303_chronology_compatible"])
        self.assertFalse(doc["real_DAC_or_speaker_audio_verified"])
    def test_pcm_size_regression_remains_strict_failure(self):
        old=ORIGINAL.replace(b"after_wait,8732688",b"after_wait,8732600")
        doc=audit(old,make_pair(bytes_second=8732600))
        self.assertEqual(doc["pcm_file_size_delta_bytes"],-88)
        self.assertFalse(doc["strict_stage303_chronology_compatible"])
    def test_failed_signal_preserves_strict_failure(self):
        old=ORIGINAL.replace(b"after_wait,8732688,1792449461203,1",
                             b"after_wait,8732688,1792449461203,0")
        doc=audit(old,make_pair(signal_second=0))
        self.assertFalse(doc["strict_stage303_chronology_compatible"])
    def test_capture_script_preserves_old_csv_and_produces_companion(self):
        script=(Path(__file__).resolve().parents[1]/
                "tools/capture_nexium_scene_audio.sh").read_text()
        self.assertIn("SCENE_RECORDER_STOP_DUAL=",script)
        self.assertIn("scene-recorder-stop-monotonic.csv",script)
        self.assertIn("printf 'event,pcm_bytes,host_epoch_ms,signal_success",script)
        self.assertIn(
            "printf 'event,pcm_bytes,host_epoch_ms,host_monotonic_ns,signal_success",
            script)
        self.assertEqual(script.count("time.monotonic_ns()"),2)
        self.assertEqual(script.count('> "$SCENE_RECORDER_STOP"'),1)
        self.assertEqual(script.count('> "$SCENE_RECORDER_STOP_DUAL"'),1)
    def test_strict_stage303_precedes_diagnostic_stage362(self):
        workflow=(Path(__file__).resolve().parents[1]/
                  ".github/workflows/emulator-smoke.yml").read_text()
        old="name: Stage303 original host recorder SIGINT snapshots versus exact terminal PCM"
        new="name: Stage362 independent recorder stop wall/monotonic companion audit"
        self.assertIn(old,workflow)
        self.assertIn(new,workflow)
        self.assertLess(workflow.index(old),workflow.index(new))
        self.assertIn("python3 tools/audit_nexium_pcm_recorder_stop.py",workflow)
        self.assertIn("always() && steps.scene_capture.outcome == 'success'",workflow)
    def test_reject_mismatched_legacy_wall_time(self):
        with self.assertRaises(RecorderClocksError):
            audit(ORIGINAL,make_pair(wall_second=1792449461204))
    def test_reject_mismatched_pcm_length(self):
        with self.assertRaises(RecorderClocksError):
            audit(ORIGINAL,make_pair(bytes_second=8732692))
    def test_reject_missing_sigint_proof_when_pair_mismatched(self):
        with self.assertRaises(RecorderClocksError):
            audit(ORIGINAL,make_pair(signal_second=0))
    def test_reject_stalled_monotonic_clock(self):
        with self.assertRaises(RecorderClocksError):
            audit(ORIGINAL,make_pair(mono_second=1000000000))
    def test_reject_reverse_monotonic_clock(self):
        with self.assertRaises(RecorderClocksError):
            audit(ORIGINAL,make_pair(mono_second=999999999))
    def test_reject_noncanonical_leading_zeros(self):
        with self.assertRaises(RecorderClocksError):
            parse(ORIGINAL.replace(b"8732688",b"08732688"),LEGACY)
    def test_reject_wrong_header(self):
        with self.assertRaises(RecorderClocksError):
            parse(make_pair().replace(b"host_monotonic_ns",b"guest_time_ns"),PAIRED)
    def test_reject_crlf(self):
        with self.assertRaises(RecorderClocksError):
            parse(make_pair().replace(b"\n",b"\r\n"),PAIRED)
    def test_reject_missing_event(self):
        with self.assertRaises(RecorderClocksError):
            parse(ORIGINAL.split(b"after_wait")[0],LEGACY)
    def test_reject_extra_event(self):
        with self.assertRaises(RecorderClocksError):
            parse(ORIGINAL+ORIGINAL.splitlines(keepends=True)[-1],LEGACY)
    def test_reject_symlinked_companion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"stop.csv"
            source.write_bytes(make_pair())
            link=root/"stop-linked.csv"
            link.symlink_to(source)
            with self.assertRaises(RecorderClocksError):
                load_regular(link)
    def test_reject_bool_literal_as_numerical_status(self):
        with self.assertRaises(RecorderClocksError):
            parse(ORIGINAL.replace(b",1\n",b",true\n"),LEGACY)

if __name__=="__main__":
    unittest.main()
