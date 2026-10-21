"""Purely invented text receipts: no BizHawk executable or game assets in CI."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_core_witness_audit import (
    MAGIC, MAX_RECEIPT_BYTES, compare_witnesses, main, read_witness,
)


def receipt(*, pid=3001, start=639000000000000001, frame=1666, **changes):
    values = dict(
        system="PSX", loaded_core="Octoshock",
        core_source="IEmulator.Attributes.CoreName",
        process_id=str(pid), process_start_utc_ticks=str(start),
        frame_count=str(frame), bios="unverified",
        disc="unverified", movie_sync="unverified",
    )
    values.update(changes)
    return "\n".join([MAGIC] + [
        k + "=" + v for k, v in values.items()
    ]) + "\n"


class RuntimeCoreWitnessTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.first = self.root / "owner-first.txt"
        self.second = self.root / "owner-second.txt"
        self.first.write_text(receipt(), encoding="ascii")
        self.second.write_text(receipt(pid=3002, start=639000000000000002),
                               encoding="ascii")

    def test_distinct_runtime_core_receipts_are_accepted_with_limits(self):
        result = compare_witnesses(self.first, self.second)
        self.assertEqual(result["runtime_iemulator_core_witnesses_read"], 2)
        self.assertTrue(result["both_witnesses_report_psx_octoshock"])
        self.assertTrue(result["reported_emuhawk_process_identities_distinct"])
        for label in (
            "process_or_witness_origin_cryptographically_authenticated",
            "witnesses_tied_to_specific_bk2_or_png_capture",
            "actual_loaded_bios_authenticated",
            "mounted_ps1_disc_authenticated",
            "original_map02_scene_authenticated",
            "private_process_ids_paths_or_game_hashes_published",
        ):
            self.assertFalse(result[label])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("3001", json.dumps(result))
        self.assertNotIn("639000000000000001", json.dumps(result))

    def test_pid_reuse_with_different_start_time_counts_distinct(self):
        self.second.write_text(receipt(pid=3001, start=639000000000000003),
                               encoding="ascii")
        self.assertTrue(compare_witnesses(self.first, self.second)[
            "reported_emuhawk_process_identities_distinct"])

    def test_identical_process_identity_is_rejected(self):
        self.second.write_text(receipt(), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "same emulator process"):
            compare_witnesses(self.first, self.second)

    def test_identical_witness_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "independent"):
            compare_witnesses(self.first, self.first)

    def test_wrong_platform_rejected(self):
        self.first.write_text(receipt(system="GEN"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            compare_witnesses(self.first, self.second)

    def test_wrong_loaded_psx_core_rejected(self):
        self.first.write_text(receipt(loaded_core="Nymashock"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            compare_witnesses(self.first, self.second)

    def test_core_preference_is_not_runtime_core_witness(self):
        self.first.write_text(receipt(
            core_source="Config.PreferredCores"
        ), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            compare_witnesses(self.first, self.second)

    def test_bios_claim_is_rejected(self):
        self.first.write_text(receipt(bios="verified"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            compare_witnesses(self.first, self.second)

    def test_disc_claim_is_rejected(self):
        self.first.write_text(receipt(disc="verified"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            compare_witnesses(self.first, self.second)

    def test_bk2_movie_sync_claim_is_rejected(self):
        self.first.write_text(receipt(movie_sync="verified"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            compare_witnesses(self.first, self.second)

    def test_unknown_extra_field_rejected(self):
        self.first.write_text(receipt() + "source_rom=/private/sensitive.iso\n",
                              encoding="ascii")
        with self.assertRaisesRegex(ValueError, "schema or field count"):
            compare_witnesses(self.first, self.second)

    def test_reordered_field_rejected(self):
        old = receipt()
        old = old.replace("system=PSX\nloaded_core=Octoshock\n",
                          "loaded_core=Octoshock\nsystem=PSX\n")
        self.first.write_text(old, encoding="ascii")
        with self.assertRaisesRegex(ValueError, "misordered"):
            compare_witnesses(self.first, self.second)

    def test_missing_final_newline_rejected(self):
        self.first.write_text(receipt().rstrip("\n"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "LF-only"):
            read_witness(self.first)

    def test_crlf_rejected(self):
        self.first.write_bytes(receipt().replace("\n", "\r\n").encode("ascii"))
        with self.assertRaisesRegex(ValueError, "LF-only"):
            read_witness(self.first)

    def test_bom_or_unicode_rejected(self):
        self.first.write_bytes(b"\xef\xbb\xbf" + receipt().encode("ascii"))
        with self.assertRaisesRegex(ValueError, "strict ASCII"):
            read_witness(self.first)

    def test_symlinked_witness_rejected(self):
        link = self.root / "link-to-first.txt"
        link.symlink_to(self.first)
        with self.assertRaisesRegex(ValueError, "nonsymlink"):
            read_witness(link)

    def test_git_worktree_input_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "Git"):
            read_witness(self.first)

    def test_numeric_values_out_of_bounds_or_with_prefix_rejected(self):
        for altered in (
            {"process_id": "0"},
            {"process_id": "+3001"},
            {"process_start_utc_ticks": "7"},
            {"frame_count": "-1"},
            {"frame_count": "2000001"},
            {"frame_count": "01666"},
            {"frame_count": "1.5"},
        ):
            with self.subTest(altered=altered):
                self.first.write_text(receipt(**altered), encoding="ascii")
                with self.assertRaisesRegex(ValueError, "numeric field"):
                    read_witness(self.first)

    def test_oversized_witness_rejected(self):
        self.first.write_bytes(b"X" * (MAX_RECEIPT_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "bounded size"):
            read_witness(self.first)

    def test_cli_report_remains_redacted(self):
        output = io.StringIO()
        with patch.object(sys, "argv", [
            "core-witness-audit", str(self.first), str(self.second)
        ]), contextlib.redirect_stdout(output):
            code = main()
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["both_witnesses_report_psx_octoshock"])
        self.assertNotIn("3001", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())


if __name__ == "__main__":
    unittest.main()
