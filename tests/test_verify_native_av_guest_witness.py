"""Independent integrity and negative tests for AV guest evidence."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_native_av_screenshot import AUDIO_OK
from test_check_native_av_screenshot import make_frames
from verify_native_av_guest_witness import verify

REVISION = "a" * 40
GITHUB_RUN_ID = 39081974011
GITHUB_RUN_ATTEMPT = 1


class GuestWitnessVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.before = base / "before.png"
        self.after = base / "after.png"
        self.nro = base / "guest.nro"
        self.witness = base / "guest-witness.json"
        first, second = make_frames(synthetic_switches=AUDIO_OK)
        for img in (first, second):
            img.putpixel((1050, 545), AUDIO_OK)
            img.putpixel((1180, 545), AUDIO_OK)
        first.save(self.before)
        second.save(self.after)
        self.nro.write_bytes(b"NRO0 synthetic fixture; not a real binary")
        self.build_witness()

    def build_witness(self):
        cmd = [
            sys.executable, "tests/check_native_av_screenshot.py",
            str(self.before), str(self.after),
            "--require-audio-source", "synthetic",
            "--require-audout-status", "initialized",
            "--require-audio-pipeline", "buffers_returned",
            "--require-synthetic-scene-switches",
            "--require-guest-resume-continuation",
            "--require-guest-resume-retry",
            "--witness-out", str(self.witness),
            "--nro-file", str(self.nro),
            "--source-revision", REVISION,
            "--github-run-id", str(GITHUB_RUN_ID),
            "--github-run-attempt", str(GITHUB_RUN_ATTEMPT),
        ]
        done = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def verify(self, scenario="resume_retry"):
        return verify(self.witness, self.before, self.after, self.nro,
                      REVISION, scenario,
                      GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT)

    def test_valid_bound_witness_and_cli(self):
        report = self.verify()
        self.assertEqual(report["guest_resume_retry_after_fake_open_failure"],
                         "confirmed")
        completed = subprocess.run(
            [sys.executable, "tests/verify_native_av_guest_witness.py",
             "--witness", str(self.witness),
             "--before", str(self.before),
             "--after", str(self.after),
             "--nro", str(self.nro),
             "--revision", REVISION,
             "--scenario", "resume_retry",
             "--github-run-id", str(GITHUB_RUN_ID),
             "--github-run-attempt", str(GITHUB_RUN_ATTEMPT)],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        verified = json.loads(completed.stdout)
        self.assertEqual(verified["verification"], "passed")
        self.assertFalse(verified["hardware_attested"])
        self.assertFalse(verified["audible_audio_attested"])

    def test_run_and_attempt_mismatch_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "GitHub run ID mismatch"):
            verify(self.witness, self.before, self.after, self.nro,
                   REVISION, "resume_retry",
                   GITHUB_RUN_ID + 1, GITHUB_RUN_ATTEMPT)
        with self.assertRaisesRegex(ValueError, "GitHub attempt mismatch"):
            verify(self.witness, self.before, self.after, self.nro,
                   REVISION, "resume_retry",
                   GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT + 1)
        data = json.loads(self.witness.read_text())
        data["github_run_id"] = True
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "GitHub run ID mismatch"):
            self.verify()

    def test_modified_nro_and_each_png_are_rejected(self):
        for path in (self.nro, self.before, self.after):
            original = path.read_bytes()
            try:
                path.write_bytes(original + b"\x00")
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    self.verify()
            finally:
                path.write_bytes(original)
        self.verify()

    def test_wrong_case_commit_and_required_checks_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "source revision mismatch"):
            verify(self.witness, self.before, self.after, self.nro,
                   "b"*40, "resume_retry",
                   GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT)
        with self.assertRaisesRegex(ValueError, "required check mismatch"):
            self.verify("resume")
        data = json.loads(self.witness.read_text())
        data["required_checks"]["resume_retry"] = False
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "required check mismatch"):
            self.verify()

    def test_recomputed_observation_and_scope_fail_closed(self):
        data = json.loads(self.witness.read_text())
        data["observation"]["guest_resume_retry_after_fake_open_failure"] = "error"
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "stale or forged observation"):
            self.verify()
        data["observation"]["guest_resume_retry_after_fake_open_failure"] = "confirmed"
        data["physical_switch_verified"] = True
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "hardware evidence incorrectly claimed"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
