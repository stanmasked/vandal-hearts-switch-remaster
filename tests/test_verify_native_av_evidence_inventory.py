"""Synthetic directory fixtures for published NeXium evidence inventory."""
from pathlib import Path
import json
import zlib
import subprocess
import sys
import tempfile
import unittest

from verify_native_av_evidence_inventory import (
    FILES, PREFIX, SCENARIOS, SUFFIX, SD_MODE_BY_SCENARIO,
    expected_manifest, validate_inventory, MAX_BYTES, PNG_PREFIX,
)


def synthetic_ihdr(width=1280, height=720, *, depth=8, color_type=2,
                   compression=0, filtering=0, interlace=0):
    # A CRC-correct IHDR only. No IDAT or pixel payload is generated:
    # inventory checks structure; the downstream verifier decodes frames.
    fields = (width.to_bytes(4, "big") + height.to_bytes(4, "big") +
              bytes((depth, color_type, compression, filtering, interlace)))
    chunk = b"IHDR" + fields
    return PNG_PREFIX + fields + zlib.crc32(chunk).to_bytes(4, "big")


class NeXiumPublishedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "published"
        self.root.mkdir()
        for scenario in SCENARIOS:
            folder = self.root / (PREFIX + scenario + SUFFIX)
            folder.mkdir()
            for name in FILES:
                if name == "sd-fixture-manifest.json":
                    (folder / name).write_text(
                        json.dumps(expected_manifest(SD_MODE_BY_SCENARIO[scenario])),
                        encoding="utf-8")
                else:
                    if name == "nexium.log":
                        payload = b""
                    elif name in ("av-before.png", "av-after.png"):
                        # Header-valid synthetic fixture for inventory only.
                        # Downstream Pillow checks still decode real PNG.
                        payload = (synthetic_ihdr() +
                                   b"synthetic-not-a-decodable-PNG")
                    else:
                        payload = b"synthetic-not-real-proof"
                    (folder / name).write_bytes(payload)

    def folder(self, scenario="empty"):
        return self.root / (PREFIX + scenario + SUFFIX)

    def cli(self, root=None):
        return subprocess.run(
            [sys.executable, "tests/verify_native_av_evidence_inventory.py",
             str(root or self.root)], capture_output=True, text=True)

    def test_all_seven_synthetic_bundles_pass_without_hardware_claim(self):
        result = validate_inventory(self.root)
        self.assertEqual(result["scenario_count"], 7)
        self.assertEqual(result["files_per_scenario"], 5)
        self.assertFalse(result["audible_audio_verified"])
        output = self.cli()
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(json.loads(output.stdout)["verification"],
                         "exact_published_evidence_inventory")

    def test_missing_scenario_is_rejected(self):
        import shutil
        shutil.rmtree(self.folder("zl"))
        with self.assertRaisesRegex(ValueError, "case directory inventory mismatch"):
            validate_inventory(self.root)

    def test_unexpected_scenario_is_rejected(self):
        (self.root / "native-ps1-music-av-nexium-rogue-evidence").mkdir()
        with self.assertRaisesRegex(ValueError, "case directory inventory mismatch"):
            validate_inventory(self.root)

    def test_unexpected_root_metadata_rejected(self):
        (self.root / ".DS_Store").write_bytes(b"x")
        self.assertNotEqual(self.cli().returncode, 0)

    def test_missing_required_file_rejected(self):
        (self.folder("resume") / "av-after.png").unlink()
        with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
            validate_inventory(self.root)

    def test_extra_file_or_subdirectory_rejected(self):
        (self.folder("zr") / "untrusted.png").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
            validate_inventory(self.root)
        (self.folder("zr") / "untrusted.png").unlink()
        (self.folder("zr") / "nested").mkdir()
        self.assertNotEqual(self.cli().returncode, 0)

    def test_symlinked_evidence_file_rejected(self):
        path = self.folder("full") / "av-before.png"
        path.unlink()
        path.symlink_to(self.folder("full") / "av-after.png")
        with self.assertRaisesRegex(ValueError, "symlinked evidence file"):
            validate_inventory(self.root)

    def test_symlinked_scenario_directory_rejected(self):
        import shutil
        old = self.folder("partial")
        target = self.folder("empty")
        shutil.rmtree(old)
        old.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "invalid published scenario"):
            validate_inventory(self.root)

    def test_zero_length_png_and_witness_rejected_but_log_optional(self):
        (self.folder("empty") / "av-before.png").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty required evidence"):
            validate_inventory(self.root)
        (self.folder("empty") / "av-before.png").write_bytes(b"x")
        (self.folder("empty") / "native-av-guest-witness.json").write_bytes(b"")
        self.assertNotEqual(self.cli().returncode, 0)

    def test_swapped_full_and_partial_sd_fixture_manifests_rejected(self):
        full = self.folder("full") / "sd-fixture-manifest.json"
        partial = self.folder("partial") / "sd-fixture-manifest.json"
        before_full, before_partial = full.read_bytes(), partial.read_bytes()
        full.write_bytes(before_partial)
        partial.write_bytes(before_full)
        with self.assertRaisesRegex(ValueError, "does not match scenario"):
            validate_inventory(self.root)

    def test_wrong_empty_fixture_for_resume_retry_rejected(self):
        manifest = self.folder("resume_retry") / "sd-fixture-manifest.json"
        data = expected_manifest("partial")
        manifest.write_text(json.dumps(data))
        self.assertNotEqual(self.cli().returncode, 0)

    def test_fake_original_music_verified_claim_rejected(self):
        manifest = self.folder("empty") / "sd-fixture-manifest.json"
        data = expected_manifest("empty")
        data["original_audio_verified"] = True
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "does not match scenario"):
            validate_inventory(self.root)

    def test_unexpected_sd_fixture_field_or_wrong_type_rejected(self):
        manifest = self.folder("full") / "sd-fixture-manifest.json"
        expected = expected_manifest("full")
        expected["fixture_source"] = "unknown"
        manifest.write_text(json.dumps(expected))
        self.assertNotEqual(self.cli().returncode, 0)
        del expected["fixture_source"]
        expected["synthetic_only"] = 1
        manifest.write_text(json.dumps(expected))
        self.assertNotEqual(self.cli().returncode, 0)

    def test_duplicate_sd_fixture_json_field_and_nan_rejected(self):
        manifest = self.folder("full") / "sd-fixture-manifest.json"
        original = manifest.read_text()
        duplicate = original.replace('"fixture_mode":', '"fixture_mode": "full", "fixture_mode":', 1)
        manifest.write_text(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate SD fixture JSON"):
            validate_inventory(self.root)
        manifest.write_text(original.replace('"synthetic_only": true',
                                              '"synthetic_only": NaN'))
        with self.assertRaisesRegex(ValueError, "non-finite SD fixture JSON"):
            validate_inventory(self.root)

    def test_oversized_or_malformed_sd_fixture_rejected(self):
        manifest = self.folder("empty") / "sd-fixture-manifest.json"
        manifest.write_bytes(b" " * 16385)
        with self.assertRaisesRegex(ValueError, "exceeds 16 KiB"):
            validate_inventory(self.root)
        manifest.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "not valid UTF-8 JSON"):
            validate_inventory(self.root)

    def test_png_signature_and_ihdr_must_be_present(self):
        png = self.folder("full") / "av-before.png"
        png.write_bytes(b"not-a-png")
        with self.assertRaisesRegex(ValueError, "invalid PNG signature or IHDR"):
            validate_inventory(self.root)
        png.write_bytes(PNG_PREFIX[:12])
        self.assertNotEqual(self.cli().returncode, 0)

    def test_png_framebuffer_dimensions_must_be_1280_by_720(self):
        png = self.folder("partial") / "av-after.png"
        original = png.read_bytes()
        png.write_bytes(original[:16] + (4096).to_bytes(4, "big") +
                        original[20:])
        with self.assertRaisesRegex(ValueError, "unexpected PNG framebuffer dimensions"):
            validate_inventory(self.root)
        png.write_bytes(original[:20] + (4096).to_bytes(4, "big") +
                        original[24:])
        self.assertNotEqual(self.cli().returncode, 0)

    def test_png_ihdr_crc_mismatch_is_rejected(self):
        png = self.folder("zr") / "av-before.png"
        original = bytearray(png.read_bytes())
        original[30] ^= 1  # Only the stored IHDR CRC changes.
        png.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "invalid PNG IHDR CRC-32"):
            validate_inventory(self.root)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_reject_illegal_png_bit_depth_and_color_type(self):
        png = self.folder("full") / "av-after.png"
        for params in ({"depth": 4, "color_type": 2},
                       {"depth": 16, "color_type": 3},
                       {"depth": 8, "color_type": 1}):
            with self.subTest(params=params):
                png.write_bytes(synthetic_ihdr(**params))
                with self.assertRaisesRegex(ValueError, "invalid PNG IHDR bit depth"):
                    validate_inventory(self.root)

    def test_reject_invalid_png_compression_filter_and_interlace(self):
        png = self.folder("partial") / "av-before.png"
        for params in ({"compression": 1}, {"filtering": 1},
                       {"interlace": 2}):
            with self.subTest(params=params):
                png.write_bytes(synthetic_ihdr(**params))
                with self.assertRaisesRegex(ValueError, "invalid PNG IHDR bit depth"):
                    validate_inventory(self.root)

    def test_legal_interlaced_indexed_png_ihdr_is_accepted(self):
        png = self.folder("empty") / "av-after.png"
        png.write_bytes(synthetic_ihdr(depth=4, color_type=3, interlace=1))
        result = validate_inventory(self.root)
        self.assertEqual(result["scenario_count"], 7)
        self.assertFalse(result["physical_hardware_verified"])

    def test_oversized_png_rejected_before_decoder(self):
        png = self.folder("zr") / "av-before.png"
        with png.open("r+b") as out:
            out.truncate(MAX_BYTES["av-before.png"] + 1)
        with self.assertRaisesRegex(ValueError, "exceeds size limit"):
            validate_inventory(self.root)

    def test_oversized_witness_or_log_rejected(self):
        witness = self.folder("empty") / "native-av-guest-witness.json"
        with witness.open("r+b") as out:
            out.truncate(MAX_BYTES["native-av-guest-witness.json"] + 1)
        with self.assertRaisesRegex(ValueError, "exceeds size limit"):
            validate_inventory(self.root)
        witness.write_bytes(b"synthetic-witness")
        log = self.folder("empty") / "nexium.log"
        with log.open("r+b") as out:
            out.truncate(MAX_BYTES["nexium.log"] + 1)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_reject_missing_or_symlinked_root(self):
        with self.assertRaisesRegex(ValueError, "non-symlink directory"):
            validate_inventory(self.root / "absent")
        link = Path(self.temp.name) / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symlink directory"):
            validate_inventory(link)


if __name__ == "__main__":
    unittest.main()
