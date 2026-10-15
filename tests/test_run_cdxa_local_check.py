"""End-to-end tests for the one-command local CD-XA verification workflow."""
import hashlib
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.run_cdxa_local_check import run_local_check
from tools.verify_cdxa_audit import verify_audit


def sector(file_number=1, channel=0, marker=0):
    data = bytearray(2352)
    data[:12] = bytes([0]) + bytes([255]) * 10 + bytes([0])
    data[15] = 2
    data[16:20] = data[20:24] = bytes((file_number, channel, 0x64, 0x01))
    # Zero XA sound groups are a valid synthetic silence example.
    data[24:2328] = bytes(2304)
    return bytes(data)


class LocalXaCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "disc.bin"
        self.source.write_bytes(
            sector(file_number=7, channel=3)
            + sector(file_number=1, channel=0)
            + sector(file_number=1, channel=1)
            + sector(file_number=1, channel=0)
        )

    def reference(self, name, value=0):
        dest = self.root / name
        with wave.open(str(dest), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(37800)
            wav.writeframes(bytes([value]) * (4032 * 4))
        return dest

    def test_full_pipeline_verifies_raw_source_and_exact_reference(self):
        ref = self.reference("reference.wav")
        output = self.root / "results"
        result = run_local_check(
            self.source, output, file_number=1, channel=0,
            start_lba=1, sector_count=3, reference_wav=ref,
        )
        self.assertEqual(result["status"], "exact_reference_pcm_match")
        self.assertEqual(result["selected_lbas"], [1, 3])
        self.assertEqual(result["pcm_frames"], 4032)
        self.assertEqual(result["source_verified_sectors"], 2)
        self.assertEqual(result["source_bin_bytes"], self.source.stat().st_size)
        self.assertEqual(result["source_bin_sha256"], hashlib.sha256(
            self.source.read_bytes()).hexdigest())
        self.assertTrue(result["comparison"]["exact_match"])
        self.assertTrue((output / "decoded.wav").is_file())
        self.assertTrue((output / "extraction.json").is_file())
        saved = json.loads((output / "audit-result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
        self.assertEqual(saved["payload_sha256"], hashlib.sha256(
            (output / "audio-groups.bin").read_bytes()).hexdigest())
        self.assertEqual(saved["decoded_wav_sha256"], hashlib.sha256(
            (output / "decoded.wav").read_bytes()).hexdigest())
        self.assertEqual(saved["decoded_wav_sha256"],
                         saved["comparison"]["candidate_wav_sha256"])
        self.assertTrue(saved["comparison"]["candidate_wav_sha256"])
        self.assertTrue(saved["comparison"]["reference_wav_sha256"])

    def test_reference_provenance_is_preserved_but_not_certified(self):
        ref = self.reference("independent.wav")
        result = run_local_check(
            self.source, self.root / "with-provenance",
            file_number=1, channel=0, start_lba=1, sector_count=3,
            reference_wav=ref, reference_decoder="Example Decoder 1.2",
            reference_command="example-decoder --input disc.bin --output independent.wav",
        )
        details = result["reference_provenance"]
        self.assertEqual(details["decoder"], "Example Decoder 1.2")
        self.assertIn("example-decoder", details["command"])
        self.assertEqual(details["status"], "user_supplied_not_independently_verified")
        self.assertEqual(
            json.loads((self.root / "with-provenance" / "audit-result.json").read_text())[
                "reference_provenance"
            ], details,
        )

    def test_missing_or_invalid_provenance_does_not_create_outputs(self):
        output = self.root / "invalid-provenance"
        with self.assertRaisesRegex(ValueError, "requires --reference-wav"):
            run_local_check(
                self.source, output, file_number=1, channel=0,
                reference_decoder="Example Decoder 1.2",
            )
        self.assertFalse(output.exists())
        ref = self.reference("valid-reference.wav")
        with self.assertRaisesRegex(ValueError, "nonempty string"):
            run_local_check(
                self.source, output, file_number=1, channel=0,
                reference_wav=ref, reference_decoder="   ",
            )
        self.assertFalse(output.exists())

    def test_source_bin_fingerprint_changes_with_unselected_sector(self):
        first = run_local_check(
            self.source, self.root / "fingerprint-first",
            file_number=1, channel=0, start_lba=1, sector_count=3,
        )
        raw = bytearray(self.source.read_bytes())
        # Change the first sector, which is outside the selected scan range.
        raw[24] ^= 1
        self.source.write_bytes(raw)
        second = run_local_check(
            self.source, self.root / "fingerprint-second",
            file_number=1, channel=0, start_lba=1, sector_count=3,
        )
        self.assertNotEqual(first["source_bin_sha256"], second["source_bin_sha256"])
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])
        self.assertEqual(first["decoded_wav_sha256"], second["decoded_wav_sha256"])

    def test_without_reference_reports_verified_decode_only(self):
        output = self.root / "without-reference"
        result = run_local_check(
            self.source, output, file_number=1, channel=0,
            start_lba=1, sector_count=3,
        )
        self.assertEqual(result["status"], "decoded_and_source_verified")
        self.assertNotIn("comparison", result)
        self.assertEqual(result["decoded_wav_sha256"], hashlib.sha256((output / "decoded.wav").read_bytes()).hexdigest())
        self.assertEqual(result["payload_sha256"], hashlib.sha256((output / "audio-groups.bin").read_bytes()).hexdigest())
        saved = json.loads((output / "audit-result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, result)

    def test_reference_mismatch_fails_and_keeps_diagnostics(self):
        ref = self.reference("wrong.wav", value=1)
        output = self.root / "mismatch"
        with self.assertRaisesRegex(ValueError, "differs from reference"):
            run_local_check(
                self.source, output, file_number=1, channel=0,
                start_lba=1, sector_count=3, reference_wav=ref,
            )
        self.assertTrue((output / "decoded.wav").exists())
        self.assertTrue((output / "extraction.json").exists())
        saved = json.loads((output / "audit-result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "reference_pcm_mismatch")
        self.assertFalse(saved["comparison"]["exact_match"])
        self.assertEqual(saved["comparison"]["first_different_frame"], 0)
        self.assertTrue(saved["comparison"]["candidate_wav_sha256"])
        self.assertTrue(saved["comparison"]["reference_wav_sha256"])
        self.assertEqual(
            saved["reference_provenance"]["status"],
            "user_supplied_not_independently_verified",
        )

    def test_saved_audit_recheck_detects_all_local_file_changes(self):
        ref = self.reference("recheck-reference.wav")
        directory = self.root / "audited"
        run_local_check(
            self.source, directory, file_number=1, channel=0,
            start_lba=1, sector_count=3, reference_wav=ref,
        )
        audit = directory / "audit-result.json"
        good = verify_audit(audit, self.source, ref)
        self.assertEqual(good["status"], "audit_files_verified")
        self.assertTrue(good["reference_comparison_rechecked"])
        with self.assertRaisesRegex(ValueError, "reference WAV required"):
            verify_audit(audit, self.source)
        for target, expected_error in (
            (self.source, "source_bin_sha256"),
            (directory / "audio-groups.bin", "payload_sha256"),
            (directory / "decoded.wav", "decoded_wav_sha256"),
            (ref, "saved WAV comparison differs"),
        ):
            with self.subTest(file=target.name):
                pristine = target.read_bytes()
                edited = bytearray(pristine)
                edited[-1] ^= 1
                target.write_bytes(edited)
                try:
                    with self.assertRaisesRegex(ValueError, expected_error):
                        verify_audit(audit, self.source, ref)
                finally:
                    target.write_bytes(pristine)
                self.assertEqual(verify_audit(audit, self.source, ref), good)

    def test_recheck_rejects_tampered_verdict_and_reference_provenance(self):
        ref = self.reference("verdict-reference.wav")
        exact_dir = self.root / "exact-verdict"
        run_local_check(
            self.source, exact_dir, file_number=1, channel=0,
            start_lba=1, sector_count=3, reference_wav=ref,
        )
        exact_audit = exact_dir / "audit-result.json"
        original = exact_audit.read_bytes()
        for key, value, message in (
            ("status", "reference_pcm_mismatch", "status contradicts"),
            ("reference_provenance", {}, "provenance status"),
        ):
            with self.subTest(key=key):
                tampered = json.loads(original)
                tampered[key] = value
                exact_audit.write_text(json.dumps(tampered), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    verify_audit(exact_audit, self.source, ref)
        exact_audit.write_bytes(original)
        self.assertEqual(verify_audit(exact_audit, self.source, ref)["status"],
                         "audit_files_verified")

        source_dir = self.root / "source-verdict"
        run_local_check(self.source, source_dir, file_number=1, channel=0,
                        start_lba=1, sector_count=3)
        source_audit = source_dir / "audit-result.json"
        original = source_audit.read_bytes()
        for key, value, message in (
            ("status", "exact_reference_pcm_match", "status contradicts"),
            ("reference_provenance", {"decoder": "unverified"}, "cannot claim"),
        ):
            with self.subTest(key=key):
                tampered = json.loads(original)
                tampered[key] = value
                source_audit.write_text(json.dumps(tampered), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    verify_audit(source_audit, self.source)
        source_audit.write_bytes(original)

        mismatch_dir = self.root / "mismatch-verdict"
        wrong = self.reference("mismatch-verdict-reference.wav", value=1)
        with self.assertRaisesRegex(ValueError, "differs from reference"):
            run_local_check(self.source, mismatch_dir, file_number=1, channel=0,
                            start_lba=1, sector_count=3, reference_wav=wrong)
        mismatch_audit = mismatch_dir / "audit-result.json"
        self.assertEqual(verify_audit(mismatch_audit, self.source, wrong)["status"],
                         "audit_files_verified")
        tampered = json.loads(mismatch_audit.read_text())
        tampered["status"] = "exact_reference_pcm_match"
        mismatch_audit.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "status contradicts"):
            verify_audit(mismatch_audit, self.source, wrong)

    def test_saved_audit_rejects_tampered_lbas_frames_and_stream(self):
        directory = self.root / "metadata-audit"
        run_local_check(
            self.source, directory, file_number=1, channel=0,
            start_lba=1, sector_count=3,
        )
        path = directory / "audit-result.json"
        original = path.read_bytes()
        mutations = (
            ("selected_lbas", [1, 2], "selected LBAs"),
            ("pcm_frames", 1, "PCM frame count"),
            ("file_number", 2, "file/channel selection"),
            ("channel", 1, "file/channel selection"),
        )
        for key, value, message in mutations:
            with self.subTest(field=key):
                altered = json.loads(original)
                altered[key] = value
                path.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    verify_audit(path, self.source)
        path.write_bytes(original)
        self.assertEqual(
            verify_audit(path, self.source)["status"], "audit_files_verified"
        )

    def test_source_only_audit_can_be_rechecked(self):
        directory = self.root / "source-only-recheck"
        run_local_check(
            self.source, directory, file_number=1, channel=0,
            start_lba=1, sector_count=3,
        )
        result = verify_audit(directory / "audit-result.json", self.source)
        self.assertFalse(result["reference_comparison_rechecked"])
        with self.assertRaisesRegex(ValueError, "no reference comparison"):
            verify_audit(directory / "audit-result.json", self.source, self.reference("unused.wav"))

    def test_existing_output_is_never_overwritten(self):
        output = self.root / "existing"
        output.mkdir()
        existing = output / "sentinel"
        existing.write_text("preserve")
        with self.assertRaises(FileExistsError):
            run_local_check(
                self.source, output, file_number=1, channel=0,
                start_lba=1, sector_count=3,
            )
        self.assertEqual(existing.read_text(), "preserve")

    def test_rejects_invalid_stream_options_before_writing(self):
        output = self.root / "invalid"
        with self.assertRaisesRegex(ValueError, "channel"):
            run_local_check(self.source, output, file_number=1, channel=256)
        self.assertFalse(output.exists())

    def test_missing_stream_fails_without_false_success(self):
        output = self.root / "empty"
        with self.assertRaisesRegex(ValueError, "no audio sectors"):
            run_local_check(
                self.source, output, file_number=2, channel=0,
                start_lba=1, sector_count=3,
            )
        self.assertFalse((output / "decoded.wav").exists())
        self.assertFalse((output / "audit-result.json").exists())


if __name__ == "__main__":
    unittest.main()
