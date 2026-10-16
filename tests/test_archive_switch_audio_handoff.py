#!/usr/bin/env python3
"""Stage 223 synthetic ZIP transfer, tamper and path traversal regressions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import archive_switch_audio_handoff as archive  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_audit_switch_audio_handoff import HardwareHandoffTests  # noqa: E402


class PortableArchiveTests(unittest.TestCase):
    def setUp(self):
        fixture = HardwareHandoffTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.destination = fixture.fixture.base / "portable-evidence-223.zip"

    def create(self, **options):
        self.fixture.fixture.write_record()
        return archive.create_archive(
            self.fixture.fixture.root, self.fixture.fixture.observations,
            self.fixture.cards, self.destination, **options)

    def contents(self):
        with zipfile.ZipFile(self.destination) as z:
            return {item.filename: z.read(item) for item in z.infolist()}

    def rewrite(self, updates=None, remove=(), extra=None):
        parts = self.contents()
        for key in remove:
            del parts[key]
        if updates:
            parts.update(updates)
        if extra:
            parts.update(extra)
        with zipfile.ZipFile(self.destination, "w") as z:
            for name, body in parts.items():
                z.writestr(archive.zip_entry(name), body)
        return bundle.digest_file(self.destination)[1]

    def test_roundtrip_copy_matches_detached_digest_no_hardware_pass(self):
        created = self.create()
        self.assertEqual(created["result"], "ARCHIVE_CREATED_AND_REVERIFIED")
        self.assertEqual(created["hardware_status"], "HARDWARE NOT TESTED")
        remote = self.destination.with_name("received-copy.zip")
        remote.write_bytes(self.destination.read_bytes())
        result = archive.verify_archive(remote, created["archive_sha256"])
        self.assertEqual(result["result"], "ARCHIVE_BYTES_AND_EVIDENCE_REVERIFIED")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["handoff_review"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertEqual(result["session_claims"]["physical_independence"], "NOT_ATTESTED")
        self.assertEqual(result["member_count"], 7)

    def test_two_identical_creation_runs_produce_same_hash(self):
        first = self.create()
        other = self.destination.with_name("copy-created-independently.zip")
        result = archive.create_archive(
            self.fixture.fixture.root, self.fixture.fixture.observations,
            self.fixture.cards, other)
        self.assertEqual(first["archive_sha256"], result["archive_sha256"])

    def test_bad_detached_anchor_fails_before_unpack(self):
        self.create()
        with self.assertRaisesRegex(archive.ArchiveError, "ARCHIVE_SHA256_MISMATCH"):
            archive.verify_archive(self.destination, "0" * 64)

    def test_truncated_or_modified_zip_fails(self):
        data = self.create()
        self.destination.write_bytes(self.destination.read_bytes()[:-20])
        with self.assertRaisesRegex(archive.ArchiveError, "ARCHIVE_SHA256_MISMATCH"):
            archive.verify_archive(self.destination, data["archive_sha256"])

    def test_missing_anchor_and_bad_anchor_format_rejected(self):
        self.create()
        for anchor in ("", "AB" * 32, "a" * 65, None):
            with self.subTest(anchor=anchor), self.assertRaisesRegex(
                    archive.ArchiveError, "independent"):
                archive.verify_archive(self.destination, anchor)

    def test_rehashed_csv_mismatch_is_detected(self):
        self.create()
        parts = self.contents()
        name = "bundle/" + self.fixture.fixture.files[0]
        self.rewrite({name: parts[name] + b"MALICIOUS"})
        with self.assertRaisesRegex(archive.ArchiveError, "ZIP declared size differs"):
            archive.verify_archive(self.destination, bundle.digest_file(self.destination)[1])

    def test_rehashed_same_size_operator_change_detected(self):
        self.create()
        parts = self.contents()
        original = parts["operator.json"]
        edited = original.replace(b'"first"', b'"xxxxx"', 1)
        self.assertEqual(len(edited), len(original))
        anchor = self.rewrite({"operator.json": edited})
        with self.assertRaisesRegex(archive.ArchiveError, "ZIP_MEMBER_SHA256_MISMATCH"):
            archive.verify_archive(self.destination, anchor)

    def test_missing_archived_csv_rejected(self):
        self.create()
        name = "bundle/" + self.fixture.fixture.files[0]
        current = self.rewrite(remove=[name])
        with self.assertRaisesRegex(archive.ArchiveError, "list disagrees"):
            archive.verify_archive(self.destination, current)

    def test_extra_unlisted_file_rejected(self):
        self.create()
        anchor = self.rewrite(extra={"bundle/untracked.csv": b"forged"})
        with self.assertRaisesRegex(archive.ArchiveError, "list disagrees"):
            archive.verify_archive(self.destination, anchor)

    def test_zip_path_traversal_rejected_even_with_updated_sha(self):
        self.create()
        anchor = self.rewrite(extra={"bundle/../../outside.txt": b"escape"})
        with self.assertRaisesRegex(archive.ArchiveError, "unsafe ZIP member"):
            archive.verify_archive(self.destination, anchor)
        self.assertFalse((self.destination.parent / "outside.txt").exists())

    def test_zip_absolute_or_windows_path_rejected(self):
        for name in ("/tmp/escape.txt", "C:/escape.txt", "bundle\\escape.csv"):
            self.create() if not self.destination.exists() else None
            anchor = self.rewrite(extra={name: b"x"})
            with self.subTest(name=name), self.assertRaises(archive.ArchiveError):
                archive.verify_archive(self.destination, anchor)
            self.destination.unlink()

    def test_duplicate_zip_members_rejected(self):
        self.create()
        with zipfile.ZipFile(self.destination, "a") as z:
            z.writestr(archive.zip_entry("operator.json"), b"duplicate!")
        with self.assertRaisesRegex(archive.ArchiveError, "duplicate ZIP member"):
            archive.verify_archive(self.destination, bundle.digest_file(self.destination)[1])

    def test_zip_symlink_rejected(self):
        self.create()
        with zipfile.ZipFile(self.destination, "a") as z:
            info = archive.zip_entry("cards/untracked.json")
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "../../outside")
        with self.assertRaisesRegex(archive.ArchiveError, "symlink"):
            archive.verify_archive(self.destination, bundle.digest_file(self.destination)[1])

    def test_archive_index_change_rejected_even_when_zip_sha_recomputed(self):
        self.create()
        parts = self.contents()
        index = json.loads(parts[archive.INDEX_NAME].decode())
        index["hardware_status"] = "PASS"
        anchor = self.rewrite({archive.INDEX_NAME: archive.json_bytes(index)})
        with self.assertRaisesRegex(archive.ArchiveError, "hardware PASS"):
            archive.verify_archive(self.destination, anchor)

    def test_index_duplicate_json_keys_rejected(self):
        self.create()
        anchor = self.rewrite({archive.INDEX_NAME:
                               b'{"schema":"first","schema":"second"}'})
        with self.assertRaises(bundle.BundleError):
            archive.verify_archive(self.destination, anchor)

    def test_archive_output_cannot_overwrite_an_existing_file(self):
        self.create()
        original = self.destination.read_bytes()
        with self.assertRaisesRegex(archive.ArchiveError, "already exists"):
            self.create()
        self.assertEqual(self.destination.read_bytes(), original)

    def test_refuses_archive_output_inside_evidence_or_cards(self):
        for target in (self.fixture.fixture.root / "new.zip",
                       self.fixture.cards / "new.zip"):
            self.fixture.fixture.write_record()
            with self.subTest(path=target), self.assertRaisesRegex(
                    archive.ArchiveError, "outside source"):
                archive.create_archive(
                    self.fixture.fixture.root, self.fixture.fixture.observations,
                    self.fixture.cards, target)
            self.assertFalse(target.exists())

    def test_missing_operator_card_retained_as_incomplete(self):
        (self.fixture.cards / "second.json").unlink()
        result = self.create()
        self.assertEqual(result["handoff_review"], "INCONCLUSIVE")
        checked = archive.verify_archive(self.destination, result["archive_sha256"])
        self.assertEqual(checked["handoff_review"], "INCONCLUSIVE")

    def test_option_flags_remain_incomplete_after_transfer(self):
        result = self.create(require_h06=True, compare_builds=True)
        self.assertEqual(result["handoff_review"], "INCONCLUSIVE")
        checked = archive.verify_archive(self.destination, result["archive_sha256"])
        self.assertEqual(checked["handoff_review"], "INCONCLUSIVE")

    def test_changed_original_csv_does_not_create_archive(self):
        self.fixture.fixture.write_record()
        path = self.fixture.fixture.root / self.fixture.fixture.files[0]
        path.write_bytes(path.read_bytes() + b"damage")
        with self.assertRaisesRegex(bundle.BundleError, "SHA-256 mismatch"):
            self.create()
        self.assertFalse(self.destination.exists())

    def test_cli_create_verify_and_no_archiving_of_personal_path(self):
        self.fixture.fixture.write_record()
        cmd = [sys.executable, str(ROOT / "tools" / "archive_switch_audio_handoff.py")]
        create = subprocess.run([
            *cmd, "create", str(self.fixture.fixture.root), "--observations",
            str(self.fixture.fixture.observations), "--cards-dir",
            str(self.fixture.cards), "--output", str(self.destination)
        ], capture_output=True, text=True, check=False)
        self.assertEqual(create.returncode, 0, create.stdout + create.stderr)
        metadata = json.loads(create.stdout)
        self.assertEqual(metadata["hardware_status"], "HARDWARE NOT TESTED")
        verify = subprocess.run([
            *cmd, "verify", str(self.destination), "--expected-sha256",
            metadata["archive_sha256"]
        ], capture_output=True, text=True, check=False)
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        self.assertEqual(json.loads(verify.stdout)["manual_signoff"],
                         "REQUIRED_NOT_AUTOMATED")
        failed = subprocess.run([
            *cmd, "verify", str(self.destination), "--expected-sha256", "0" * 64
        ], capture_output=True, text=True, check=False)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(json.loads(failed.stdout)["result"], "INVALID_EVIDENCE")

    def test_source_and_cards_remain_read_only(self):
        self.fixture.fixture.write_record()
        evidence = {str(p.relative_to(self.fixture.fixture.root)): p.read_bytes()
                    for p in self.fixture.fixture.root.rglob("*") if p.is_file()}
        operator = self.fixture.fixture.observations.read_bytes()
        cards = {p.name: p.read_bytes() for p in self.fixture.cards.iterdir()}
        self.create()
        self.assertEqual(evidence,
                         {str(p.relative_to(self.fixture.fixture.root)): p.read_bytes()
                          for p in self.fixture.fixture.root.rglob("*") if p.is_file()})
        self.assertEqual(operator, self.fixture.fixture.observations.read_bytes())
        self.assertEqual(cards, {p.name: p.read_bytes() for p in self.fixture.cards.iterdir()})


if __name__ == "__main__":
    unittest.main()
