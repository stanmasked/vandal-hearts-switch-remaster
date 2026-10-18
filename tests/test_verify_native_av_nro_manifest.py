"""Synthetic seven-NRO bundles for strict AV artifact manifest verification."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verify_native_av_nro_manifest import (
    COMMIT_FILE, COMMIT_MARKER_BYTES, MANIFEST, MANIFEST_BYTES,
    NRO_NAMES, verify_bundle,
)

COMMIT = "0123456789abcdef" * 2 + "01234567"


def tiny_nro(seed):
    data = bytearray(0x100)
    data[0x10:0x14] = b"NRO0"
    data[0x18:0x1c] = (0x100).to_bytes(4, "little")
    for header, segment in ((0x20, 0x80), (0x28, 0x90), (0x30, 0xA0)):
        data[header:header+4] = segment.to_bytes(4, "little")
        data[header+4:header+8] = (0x10).to_bytes(4, "little")
    data[0xF0] = seed
    return bytes(data)


class AvNroManifestTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.files = {name: tiny_nro(i) for i, name in enumerate(NRO_NAMES)}
        for name, content in self.files.items():
            (self.root / name).write_bytes(content)
        self.set_manifest()
        (self.root / COMMIT_FILE).write_text(COMMIT + "\n", encoding="ascii")

    def set_manifest(self, names=NRO_NAMES):
        self.root.joinpath(MANIFEST).write_text(
            "".join(hashlib.sha256(self.files[name]).hexdigest() +
                    "  " + name + "\n" for name in names),
            encoding="ascii")

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "tests/verify_native_av_nro_manifest.py",
             str(self.root), *arguments], capture_output=True, text=True)

    def test_complete_bundle_and_independent_commit(self):
        report = verify_bundle(self.root, COMMIT)
        self.assertEqual(report["nro_count"], 7)
        self.assertEqual(report["source_commit"], COMMIT)
        self.assertFalse(report["audible_audio_verified"])
        self.assertEqual(self.cli("--expected-commit", COMMIT.upper()).returncode, 0)

    def test_exact_published_inventory_accepts_only_nine_files(self):
        accepted = verify_bundle(self.root, COMMIT, exact_inventory=True)
        self.assertEqual(accepted["nro_count"], 7)
        self.assertEqual(
            self.cli("--expected-commit", COMMIT, "--exact-inventory").returncode, 0)

    def test_unknown_extra_nro_rejected_in_published_bundle(self):
        (self.root / "unexpected-variant.nro").write_bytes(tiny_nro(200))
        # Normal build/ staging directories may contain other output.
        self.assertEqual(verify_bundle(self.root, COMMIT)["nro_count"], 7)
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            verify_bundle(self.root, COMMIT, exact_inventory=True)
        self.assertNotEqual(self.cli("--exact-inventory").returncode, 0)

    def test_unknown_extra_metadata_or_directory_rejected(self):
        unexpected = self.root / "extra-metadata.json"
        unexpected.write_text("{}")
        with self.assertRaisesRegex(ValueError, "extra-metadata.json"):
            verify_bundle(self.root, exact_inventory=True)
        unexpected.unlink()
        (self.root / "unlisted-subdir").mkdir()
        with self.assertRaisesRegex(ValueError, "unlisted-subdir"):
            verify_bundle(self.root, exact_inventory=True)

    def test_exact_inventory_rejects_absent_or_symlinked_expected_files(self):
        target = self.root / NRO_NAMES[-1]
        target.unlink()
        with self.assertRaisesRegex(ValueError, "missing="):
            verify_bundle(self.root, exact_inventory=True)
        target.symlink_to(self.root / NRO_NAMES[0])
        with self.assertRaisesRegex(ValueError, "symlinked AV artifact"):
            verify_bundle(self.root, exact_inventory=True)

    def test_duplicate_nro_bytes_rejected_even_with_recomputed_manifest(self):
        # Substituting a valid file for another and updating the
        # checksums must not certify seven distinct diagnostic variants.
        first, second = NRO_NAMES[0], NRO_NAMES[1]
        self.files[second] = self.files[first]
        (self.root / second).write_bytes(self.files[first])
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "duplicate NRO payload"):
            verify_bundle(self.root, COMMIT, exact_inventory=True)
        self.assertNotEqual(
            self.cli("--expected-commit", COMMIT, "--exact-inventory").returncode, 0)

    def test_hardlinked_distinct_names_rejected_even_with_updated_digest(self):
        first, second = NRO_NAMES[-2], NRO_NAMES[-1]
        (self.root / second).unlink()
        (self.root / second).hardlink_to(self.root / first)
        self.files[second] = self.files[first]
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "duplicate NRO payload"):
            verify_bundle(self.root, exact_inventory=True)
        self.assertEqual(len(set(self.files.values())), len(NRO_NAMES) - 1)

    def test_missing_manifest_record_rejected(self):
        self.set_manifest(names=NRO_NAMES[:-1])
        with self.assertRaisesRegex(ValueError, "exactly seven"):
            verify_bundle(self.root)

    def test_duplicate_entry_or_wrong_order_rejected(self):
        original = (self.root / MANIFEST).read_text()
        rows = original.splitlines(keepends=True)
        rows[1] = rows[0]
        (self.root / MANIFEST).write_text("".join(rows))
        with self.assertRaisesRegex(ValueError, "unexpected, duplicated or missing"):
            verify_bundle(self.root)
        rows = original.splitlines(keepends=True)
        rows[0], rows[1] = rows[1], rows[0]
        (self.root / MANIFEST).write_text("".join(rows))
        self.assertNotEqual(self.cli().returncode, 0)

    def test_tampered_nro_digest_rejected(self):
        path = self.root / NRO_NAMES[-1]
        content = bytearray(path.read_bytes())
        content[-1] ^= 1
        path.write_bytes(content)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify_bundle(self.root)

    def test_missing_or_symlinked_binary_rejected(self):
        name = NRO_NAMES[0]
        (self.root / name).unlink()
        with self.assertRaisesRegex(ValueError, "missing, non-regular"):
            verify_bundle(self.root)
        (self.root / name).symlink_to(self.root / NRO_NAMES[1])
        self.assertNotEqual(self.cli().returncode, 0)

    def test_invalid_nro_header_even_when_digest_matches(self):
        name = NRO_NAMES[2]
        broken = b"not-an-nro" + b"\0" * 260
        self.files[name] = broken
        (self.root / name).write_bytes(broken)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "invalid NRO0 header"):
            verify_bundle(self.root)

    def test_invalid_nro_segment_even_when_digest_matches(self):
        name = NRO_NAMES[3]
        data = bytearray(self.files[name])
        data[0x24:0x28] = (0xFF).to_bytes(4, "little")
        self.files[name] = bytes(data)
        (self.root / name).write_bytes(data)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "invalid NRO segment bounds"):
            verify_bundle(self.root)

    def test_overlapping_nro_sections_rejected_with_valid_digest(self):
        name=NRO_NAMES[4]
        data=bytearray(self.files[name])
        # Text covers [0x80,0x90). Force rodata to overlap it while
        # preserving all bounds and recomputing the manifest hash.
        data[0x28:0x2c]=(0x88).to_bytes(4,"little")
        self.files[name]=bytes(data)
        (self.root/name).write_bytes(data)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError,"overlapping or out-of-order"):
            verify_bundle(self.root,COMMIT,exact_inventory=True)
        self.assertNotEqual(self.cli("--exact-inventory").returncode,0)

    def test_out_of_order_disjoint_nro_sections_rejected(self):
        name=NRO_NAMES[5]
        data=bytearray(self.files[name])
        # Reorder text and rodata into disjoint intervals. Neither
        # individual segment exceeds the NRO length.
        data[0x20:0x24]=(0x90).to_bytes(4,"little")
        data[0x28:0x2c]=(0x80).to_bytes(4,"little")
        self.files[name]=bytes(data)
        (self.root/name).write_bytes(data)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError,"overlapping or out-of-order"):
            verify_bundle(self.root,COMMIT)
        self.assertNotEqual(self.cli().returncode,0)

    def test_nro_text_must_start_after_full_header(self):
        name = NRO_NAMES[2]
        data = bytearray(self.files[name])
        data[0x20:0x24] = (0x70).to_bytes(4, "little")
        # All three segments remain disjoint and within declared size,
        # but the first one overwrites the NRO's 0x80-byte header.
        self.files[name] = bytes(data)
        (self.root / name).write_bytes(data)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "NRO segment overlaps header"):
            verify_bundle(self.root, COMMIT, exact_inventory=True)
        self.assertNotEqual(self.cli("--exact-inventory").returncode, 0)

    def test_unaligned_data_offset_with_updated_hash_rejected(self):
        name = NRO_NAMES[4]
        data = bytearray(self.files[name])
        data[0x30:0x34] = (0xA1).to_bytes(4, "little")
        self.files[name] = bytes(data)
        (self.root / name).write_bytes(data)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "unaligned NRO segment offset"):
            verify_bundle(self.root, COMMIT)
        self.assertNotEqual(self.cli().returncode, 0)

    def test_unaligned_rodata_offset_in_nonoverlapping_gap_rejected(self):
        name = NRO_NAMES[5]
        data = bytearray(self.files[name])
        data[0x28:0x2c] = (0x91).to_bytes(4, "little")
        data[0x2c:0x30] = (0x0f).to_bytes(4, "little")
        self.files[name] = bytes(data)
        (self.root / name).write_bytes(data)
        self.set_manifest()
        with self.assertRaisesRegex(ValueError, "unaligned NRO segment offset"):
            verify_bundle(self.root)

    def test_aligned_nonoverlapping_gaps_are_accepted(self):
        name = NRO_NAMES[1]
        data = bytearray(self.files[name])
        data[0x28:0x2c] = (0xA0).to_bytes(4, "little")
        data[0x30:0x34] = (0xC0).to_bytes(4, "little")
        self.files[name] = bytes(data)
        (self.root / name).write_bytes(data)
        self.set_manifest()
        self.assertEqual(verify_bundle(self.root, COMMIT)["nro_count"], 7)

    def test_metadata_limits_match_valid_exact_fixture_sizes(self):
        self.assertEqual((self.root / COMMIT_FILE).stat().st_size,
                         COMMIT_MARKER_BYTES)
        self.assertEqual((self.root / MANIFEST).stat().st_size,
                         MANIFEST_BYTES)
        self.assertEqual(verify_bundle(self.root, COMMIT)["nro_count"], 7)

    def test_oversized_source_marker_fails_before_unbounded_read(self):
        path = self.root / COMMIT_FILE
        with path.open("r+b") as stream:
            stream.truncate(8 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "source commit marker exceeds exact size limit"):
            verify_bundle(self.root, COMMIT, exact_inventory=True)
        self.assertNotEqual(self.cli("--expected-commit", COMMIT).returncode, 0)

    def test_oversized_manifest_fails_before_unbounded_read(self):
        path = self.root / MANIFEST
        with path.open("r+b") as stream:
            stream.truncate(8 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "NRO digest manifest exceeds exact size limit"):
            verify_bundle(self.root, COMMIT, exact_inventory=True)
        self.assertNotEqual(self.cli("--exact-inventory").returncode, 0)

    def test_mismatched_or_nonhex_source_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, "independently expected commit"):
            verify_bundle(self.root, "f" * 40)
        with self.assertRaisesRegex(ValueError, "40 hexadecimal"):
            verify_bundle(self.root, "not-a-sha")
        (self.root / COMMIT_FILE).write_text("f" * 40 + "\n")
        self.assertNotEqual(self.cli("--expected-commit", COMMIT).returncode, 0)

    def test_source_commit_marker_extra_lines_rejected(self):
        (self.root / COMMIT_FILE).write_text(COMMIT + "\n" + COMMIT + "\n")
        self.assertNotEqual(self.cli().returncode, 0)

    def test_malformed_manifest_trailing_data_rejected(self):
        manifest = self.root / MANIFEST
        manifest.write_text(manifest.read_text() + "# comment\n")
        self.assertNotEqual(self.cli().returncode, 0)
        self.set_manifest()
        manifest.write_text(manifest.read_text().rstrip("\n"))
        self.assertNotEqual(self.cli().returncode, 0)


if __name__ == "__main__":
    unittest.main()
