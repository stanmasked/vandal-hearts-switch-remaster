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
from test_verify_native_av_nro_manifest import NRO_NAMES, tiny_nro
from verify_native_av_nro_manifest import MANIFEST, COMMIT_FILE
from verify_native_av_guest_witness import (
    MAX_PNG_BYTES, MAX_WITNESS_BYTES, verify,
)

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

    def published_bundle(self):
        folder = Path(self.temp.name) / "published-nros"
        folder.mkdir()
        files = {}
        for i, name in enumerate(NRO_NAMES):
            files[name] = tiny_nro(i)
            (folder / name).write_bytes(files[name])
        (folder / MANIFEST).write_text(
            "".join(hashlib.sha256(files[name]).hexdigest() +
                    "  " + name + chr(10) for name in NRO_NAMES),
            encoding="ascii")
        (folder / COMMIT_FILE).write_text(REVISION + chr(10),
                                          encoding="ascii")
        return folder

    def test_published_variant_matches_resume_retry_scenario(self):
        bundle = self.published_bundle()
        self.nro = bundle / "libnx-ps1-music-av-resume-retry.nro"
        # The witness writer intentionally refuses an existing output.
        # Each test discards only its own synthetic setup fixture before
        # binding a different NRO; production overwrite protection stays.
        self.witness.unlink()
        self.build_witness()
        observed = verify(
            self.witness, self.before, self.after, self.nro,
            REVISION, "resume_retry", GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT,
            published_nro_dir=bundle)
        self.assertEqual(observed["guest_resume_retry_after_fake_open_failure"],
                         "confirmed")
        self.assertFalse(observed["audible_audio_verified"])

    def test_other_valid_published_nro_cannot_masquerade_as_resume_retry(self):
        bundle = self.published_bundle()
        self.nro = bundle / "libnx-ps1-music-av-resume.nro"
        # The witness writer intentionally refuses an existing output.
        # Each test discards only its own synthetic setup fixture before
        # binding a different NRO; production overwrite protection stays.
        self.witness.unlink()
        self.build_witness()
        # Exact NRO and PNG digests in the witness still agree. Only
        # external binding to the scenario makes this fail.
        self.verify()
        with self.assertRaisesRegex(ValueError, "variant digest does not match"):
            verify(self.witness, self.before, self.after, self.nro,
                   REVISION, "resume_retry", GITHUB_RUN_ID,
                   GITHUB_RUN_ATTEMPT, published_nro_dir=bundle)

    def test_published_bundle_tampering_and_commit_mismatch_rejected(self):
        bundle = self.published_bundle()
        self.nro = bundle / "libnx-ps1-music-av-resume-retry.nro"
        # The witness writer intentionally refuses an existing output.
        # Each test discards only its own synthetic setup fixture before
        # binding a different NRO; production overwrite protection stays.
        self.witness.unlink()
        self.build_witness()
        (bundle / COMMIT_FILE).write_text("f" * 40 + chr(10), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "independently expected commit"):
            verify(self.witness, self.before, self.after, self.nro,
                   REVISION, "resume_retry", GITHUB_RUN_ID,
                   GITHUB_RUN_ATTEMPT, published_nro_dir=bundle)
        (bundle / COMMIT_FILE).write_text(REVISION + chr(10),
                                          encoding="ascii")
        (bundle / "rogue.nro").write_bytes(tiny_nro(25))
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            verify(self.witness, self.before, self.after, self.nro,
                   REVISION, "resume_retry", GITHUB_RUN_ID,
                   GITHUB_RUN_ATTEMPT, published_nro_dir=bundle)

    def test_unexpected_root_field_fails_closed(self):
        data = json.loads(self.witness.read_text())
        data["physical_console_verified"] = True
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "unexpected top-level fields"):
            self.verify()

    def test_duplicate_json_members_are_rejected_at_every_level(self):
        original = self.witness.read_text()
        try:
            duplicate_root = original.replace(
                '"format": ', '"format": "vh-native-av-guest-witness-v1", "format": ',
                1)
            self.assertNotEqual(duplicate_root, original)
            self.witness.write_text(duplicate_root)
            with self.assertRaisesRegex(ValueError, "duplicate JSON member: format"):
                self.verify()

            duplicate_nested = original.replace(
                '"resume_retry": true',
                '"resume_retry": true, "resume_retry": true', 1)
            self.assertNotEqual(duplicate_nested, original)
            self.witness.write_text(duplicate_nested)
            with self.assertRaisesRegex(ValueError, "duplicate JSON member: resume_retry"):
                self.verify()
        finally:
            self.witness.write_text(original)
        self.verify()

    def test_non_finite_json_number_is_rejected(self):
        data = json.loads(self.witness.read_text())
        data["github_run_id"] = float("nan")
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "non-finite JSON number rejected"):
            self.verify()

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

    def test_oversized_standalone_witness_rejected_before_json_parse(self):
        with self.witness.open("r+b") as stream:
            stream.truncate(MAX_WITNESS_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "guest witness exceeds size limit"):
            self.verify()

    def test_oversized_standalone_png_rejected_before_decode(self):
        with self.before.open("r+b") as stream:
            stream.truncate(MAX_PNG_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "first PNG exceeds size limit"):
            self.verify()

    def test_symlinked_standalone_evidence_inputs_rejected(self):
        for path, label in ((self.witness, "guest witness"),
                            (self.before, "first PNG"),
                            (self.after, "second PNG"),
                            (self.nro, "guest NRO")):
            with self.subTest(path=path.name):
                backup = path.with_suffix(path.suffix + ".original")
                path.rename(backup)
                path.symlink_to(backup)
                try:
                    with self.assertRaisesRegex(ValueError,
                                                "non-regular or symlinked " + label):
                        self.verify()
                finally:
                    path.unlink()
                    backup.rename(path)
        self.verify()

    def test_invalid_utf8_witness_is_rejected(self):
        self.witness.write_bytes(bytes((0xff, 0xfe)))
        with self.assertRaisesRegex(ValueError, "guest witness is not valid UTF-8"):
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

    def test_boolean_observation_cannot_be_replaced_with_integer(self):
        data = json.loads(self.witness.read_text())
        # Ordinary Python dict comparison would accept true == 1.
        self.assertIs(data["observation"]["guest_resume_is_not_home_event"], True)
        data["observation"]["guest_resume_is_not_home_event"] = 1
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "stale or forged observation"):
            self.verify()

    def test_false_observation_disclaimer_cannot_be_replaced_with_zero(self):
        data = json.loads(self.witness.read_text())
        self.assertIs(data["observation"]["audible_audio_verified"], False)
        data["observation"]["audible_audio_verified"] = 0
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "stale or forged observation"):
            self.verify()
        self.assertEqual(self.witness.read_text().count('"audible_audio_verified"'), 2)

    def test_integer_heartbeat_rejects_equivalent_float(self):
        data = json.loads(self.witness.read_text())
        frames = data["observation"]["heartbeat_changed_pixels"]
        self.assertIs(type(frames), int)
        data["observation"]["heartbeat_changed_pixels"] = float(frames)
        self.witness.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "stale or forged observation"):
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
