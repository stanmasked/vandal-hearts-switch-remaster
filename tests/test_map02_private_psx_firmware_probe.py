"""Invented BK2 and BIOS bytes only. No licensed assets used in public CI."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.map02_private_psx_firmware_probe import (
    MAX_BIOS_FILE_BYTES, compare_firmware, main,
)

PREFIX = "tools.map02_private_psx_firmware_probe."


class PrivatePsxFirmwareProbeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.movie = self.root / "fictional-psx.bk2"
        self.bios = self.root / "fictional-bios.bin"
        self.bios.write_bytes(b"FICTIONAL_BIOS_000" * 201)
        self.sha1 = hashlib.sha1(self.bios.read_bytes()).hexdigest()
        self.make_movie("PSX_Firmware_BIOS", self.sha1)

    def make_movie(self, field=None, value=None, *, raw_header=None,
                   extra=None, duplicate=False):
        header = ("MovieVersion FakeCIOnly\nPlatform PSX\n"
                  "GameName Vandal Hearts (USA)\nCore Octoshock\n")
        if field is not None:
            header += field + " " + value + "\n"
        if duplicate:
            header += field + " " + value + "\n"
        if raw_header is not None:
            header = raw_header
        with zipfile.ZipFile(self.movie, "w",
                             compression=zipfile.ZIP_DEFLATED) as stream:
            stream.writestr("Header.txt", header)
            stream.writestr("Input Log.txt", "[Input]\nfictional\n[/Input]\n")
            stream.writestr("SyncSettings.json", "{}")
            for name, contents in (extra or {}).items():
                stream.writestr(name, contents)

    def test_matching_candidate_and_firmware_header(self):
        outcome = compare_firmware(self.movie, self.bios)
        self.assertTrue(outcome["psx_firmware_header_fields_present"])
        self.assertEqual(outcome["psx_firmware_header_entry_count"], 1)
        self.assertTrue(outcome["single_unambiguous_psx_firmware_hash_available"])
        self.assertTrue(outcome["candidate_bios_sha1_matches_movie_psx_firmware_metadata"])
        self.assertFalse(outcome["actual_emuhawk_loaded_bios_authenticated"])
        self.assertFalse(outcome["active_psx_core_authenticated"])
        self.assertFalse(outcome["source_disc_or_bk2_playback_authenticated"])
        self.assertFalse(outcome["private_assets_uploaded"])
        self.assertNotIn(self.sha1, json.dumps(outcome))
        self.assertNotIn(str(self.root), json.dumps(outcome))
        self.assertNotIn(self.bios.name, json.dumps(outcome))

    def test_uppercase_sha1_is_accepted(self):
        self.make_movie("PSX_Firmware_BIOS", self.sha1.upper())
        self.assertTrue(compare_firmware(self.movie, self.bios)[
            "candidate_bios_sha1_matches_movie_psx_firmware_metadata"])

    def test_no_psx_firmware_header_remains_unverified(self):
        self.make_movie()
        result = compare_firmware(self.movie, self.bios)
        self.assertFalse(result["psx_firmware_header_fields_present"])
        self.assertFalse(result["single_unambiguous_psx_firmware_hash_available"])
        self.assertFalse(result["candidate_bios_sha1_matches_movie_psx_firmware_metadata"])

    def test_generic_firmware_sha1_does_not_claim_psx_bios(self):
        self.make_movie("FirmwareSHA1", self.sha1)
        self.assertFalse(compare_firmware(self.movie, self.bios)[
            "candidate_bios_sha1_matches_movie_psx_firmware_metadata"])

    def test_candidate_mismatch_remains_unverified(self):
        self.bios.write_bytes(b"ANOTHER_FAKE_BIOS")
        report = compare_firmware(self.movie, self.bios)
        self.assertTrue(report["single_unambiguous_psx_firmware_hash_available"])
        self.assertFalse(report["candidate_bios_sha1_matches_movie_psx_firmware_metadata"])

    def test_two_distinct_psx_bios_hashes_are_ambiguous(self):
        raw = ("Platform PSX\nGameName Vandal Hearts (USA)\n"
               "Core Octoshock\nPSX_Firmware_EU " + self.sha1 +
               "\nPSX_Firmware_US " + "f" * 40 + "\n")
        self.make_movie(raw_header=raw)
        report = compare_firmware(self.movie, self.bios)
        self.assertEqual(report["psx_firmware_header_entry_count"], 2)
        self.assertFalse(report["single_unambiguous_psx_firmware_hash_available"])
        self.assertFalse(report["candidate_bios_sha1_matches_movie_psx_firmware_metadata"])

    def test_two_identical_psx_hash_records_can_match(self):
        raw = ("Platform PSX\nGameName Vandal Hearts (USA)\nCore Octoshock\n"
               "PSX_Firmware_EU " + self.sha1 + "\n"
               "PSX_Firmware_US " + self.sha1 + "\n")
        self.make_movie(raw_header=raw)
        report = compare_firmware(self.movie, self.bios)
        self.assertEqual(report["psx_firmware_header_entry_count"], 2)
        self.assertTrue(report["candidate_bios_sha1_matches_movie_psx_firmware_metadata"])

    def test_invalid_psx_firmware_header_field_rejected(self):
        for name in ("PSX_Firmware_", "PSX_Firmware_foo-bar",
                     "PSX_Firmware_" + "X" * 49):
            with self.subTest(name=name):
                self.make_movie(name, self.sha1)
                with self.assertRaisesRegex(ValueError, "firmware header"):
                    compare_firmware(self.movie, self.bios)

    def test_nonhex_or_injected_fingerprint_rejected(self):
        for value in ("g" * 40, "FAKE", self.sha1 + "/private/secret"):
            with self.subTest(value=value[:12]):
                self.make_movie("PSX_Firmware_BIOS", value)
                with self.assertRaisesRegex(ValueError, "firmware header"):
                    compare_firmware(self.movie, self.bios)

    def test_duplicate_firmware_fields_rejected(self):
        self.make_movie("PSX_Firmware_BIOS", self.sha1, duplicate=True)
        with self.assertRaisesRegex(ValueError, "BizHawk header"):
            compare_firmware(self.movie, self.bios)

    def test_wrong_core_declared_in_movie_rejected(self):
        self.make_movie(raw_header="Platform PSX\nGameName Vandal Hearts (USA)\n"
                        "Core Nymashock\n")
        with self.assertRaisesRegex(ValueError, "Octoshock"):
            compare_firmware(self.movie, self.bios)

    def test_unexpected_archive_member_rejected(self):
        self.make_movie("PSX_Firmware_BIOS", self.sha1,
                        extra={"Original.ROM": b"fictional"})
        with self.assertRaisesRegex(ValueError, "BK2"):
            compare_firmware(self.movie, self.bios)

    def test_bios_candidate_symlink_refused(self):
        alias = self.root / "alias-bios.bin"
        alias.symlink_to(self.bios)
        with self.assertRaisesRegex(ValueError, "nonsymlink"):
            compare_firmware(self.movie, alias)

    def test_bios_larger_than_size_cap_refused(self):
        with self.bios.open("wb") as stream:
            stream.truncate(MAX_BIOS_FILE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "bounded size"):
            compare_firmware(self.movie, self.bios)

    def test_git_checkout_paths_refused(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "Git"):
            compare_firmware(self.movie, self.bios)

    def test_changed_bios_during_read_rejected(self):
        original = Path(self.bios).stat().st_size
        with patch(PREFIX + "_assert_stable",
                   side_effect=[None, ValueError("invented BIOS mutated")]):
            with self.assertRaisesRegex(ValueError, "BIOS mutated"):
                compare_firmware(self.movie, self.bios)
        self.assertEqual(self.bios.stat().st_size, original)

    def test_cli_returns_zero_only_for_matching_declared_psx_hash(self):
        for setup, expected_code in (
            ("match", 0), ("missing", 2), ("mismatch", 2),
        ):
            with self.subTest(setup=setup):
                if setup == "match":
                    self.make_movie("PSX_Firmware_BIOS", self.sha1)
                elif setup == "missing":
                    self.make_movie()
                else:
                    self.make_movie("PSX_Firmware_BIOS", "f" * 40)
                stdout = io.StringIO()
                with patch.object(sys, "argv", [
                    "private-firmware-probe", str(self.movie), str(self.bios),
                ]), contextlib.redirect_stdout(stdout):
                    status = main()
                report = json.loads(stdout.getvalue())
                self.assertEqual(status, expected_code)
                self.assertEqual(
                    report["candidate_bios_sha1_matches_movie_psx_firmware_metadata"],
                    status == 0,
                )
                self.assertNotIn(self.sha1, stdout.getvalue())
                self.assertNotIn(str(self.root), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
