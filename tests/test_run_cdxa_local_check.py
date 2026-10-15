"""End-to-end tests for the one-command local CD-XA verification workflow."""
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.run_cdxa_local_check import run_local_check


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
        self.assertTrue(result["comparison"]["exact_match"])
        self.assertTrue((output / "decoded.wav").is_file())
        self.assertTrue((output / "extraction.json").is_file())
        saved = json.loads((output / "audit-result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
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

    def test_without_reference_reports_verified_decode_only(self):
        output = self.root / "without-reference"
        result = run_local_check(
            self.source, output, file_number=1, channel=0,
            start_lba=1, sector_count=3,
        )
        self.assertEqual(result["status"], "decoded_and_source_verified")
        self.assertNotIn("comparison", result)
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
