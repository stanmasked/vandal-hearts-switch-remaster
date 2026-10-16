#!/usr/bin/env python3
"""Stage 226: synthetic, host-only chained ZIP receipts and omission checks."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import archive_switch_audio_handoff as archive  # noqa: E402
import chain_switch_audio_receipts as chain  # noqa: E402
import replay_switch_audio_evidence_report as replay  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_archive_switch_audio_handoff import PortableArchiveTests  # noqa: E402


class ChainedReceiptTests(unittest.TestCase):
    def setUp(self):
        fixture = PortableArchiveTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.store = fixture.fixture.fixture.base / "stage226-store"
        for part in ("chain", "archives", "receipts"):
            (self.store / part).mkdir(parents=True)
        self.first_zip = self.store / "archives" / "first.zip"
        self.first_receipt = self.store / "receipts" / "first.json"
        first = fixture.create()
        shutil.copyfile(fixture.destination, self.first_zip)
        self.first_sha = first["archive_sha256"]
        self.first_receipt_sha = replay.record(
            self.first_zip, self.first_sha, self.first_receipt)["receipt_sha256"]

    def entry(self, number):
        return self.store / "chain" / f"{number:06d}.json"

    def append_first(self):
        return chain.append(
            self.store, "archives/first.zip", "receipts/first.json",
            self.first_sha, self.first_receipt_sha, chain.GENESIS, 0)

    def prepare_second(self):
        fx = self.fixture.fixture
        fx.records[0]["observer_note"] = "Second synthetic session batch"
        fx.save_cards()
        fx.fixture.write_record()
        second_zip = self.store / "archives" / "second.zip"
        other = archive.create_archive(
            fx.fixture.root, fx.fixture.observations, fx.cards, second_zip)
        self.second_sha = other["archive_sha256"]
        self.second_receipt = self.store / "receipts" / "second.json"
        self.second_receipt_sha = replay.record(
            second_zip, self.second_sha, self.second_receipt)["receipt_sha256"]

    def append_second(self, head):
        return chain.append(
            self.store, "archives/second.zip", "receipts/second.json",
            self.second_sha, self.second_receipt_sha, head, 1)

    def two(self):
        first = self.append_first()
        self.prepare_second()
        second = self.append_second(first["chain_head_sha256"])
        return first, second

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" /
                                 "chain_switch_audio_receipts.py"), *args],
            capture_output=True, text=True, check=False)

    def test_empty_genesis_is_not_an_apparatus_success(self):
        result = chain.verify(self.store, chain.GENESIS, 0)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["physical_independence"], "NOT_ATTESTED")
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")

    def test_one_pinned_record_replays_full_zip_and_receipt(self):
        a = self.append_first()
        result = chain.verify(self.store, a["chain_head_sha256"], 1)
        self.assertEqual(result["result"], "PINNED_RECEIPT_CHAIN_REPLAYED")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["chain_head_sha256"], a["chain_head_sha256"])
        self.assertEqual(result["entries"][0]["receipt_sha256"],
                         self.first_receipt_sha)

    def test_two_distinct_links_verify_and_bind_previous_sha(self):
        first, second = self.two()
        entry, h = chain.read_entry(self.entry(2))
        self.assertEqual(entry["sequence"], 2)
        self.assertEqual(entry["previous_record_sha256"],
                         first["chain_head_sha256"])
        self.assertEqual(h, second["chain_head_sha256"])
        check = chain.verify(self.store, second["chain_head_sha256"], 2)
        self.assertEqual(check["count"], 2)
        self.assertNotEqual(check["entries"][0]["archive_sha256"],
                            check["entries"][1]["archive_sha256"])

    def test_removed_last_file_detected_by_pinned_count(self):
        _, final = self.two()
        self.entry(2).unlink()
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_COUNT_MISMATCH"):
            chain.verify(self.store, final["chain_head_sha256"], 2)

    def test_missing_first_file_detected_by_gap(self):
        _, final = self.two()
        self.entry(1).unlink()
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_GAP_OR_REORDER"):
            chain.verify(self.store, final["chain_head_sha256"], 2)

    def test_swapped_records_detected_by_sequence_or_link(self):
        _, final = self.two()
        a, b = self.entry(1), self.entry(2)
        raw_a, raw_b = a.read_bytes(), b.read_bytes()
        a.write_bytes(raw_b)
        b.write_bytes(raw_a)
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_LINK_MISMATCH"):
            chain.verify(self.store, final["chain_head_sha256"], 2)

    def test_changed_record_fields_detected_by_pinned_head(self):
        first = self.append_first()
        changed = json.loads(self.entry(1).read_text())
        changed["handoff_review"] = "INVESTIGATE"
        self.entry(1).write_bytes(chain.stable_bytes(changed))
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_HEAD_MISMATCH|CHAIN_REVIEW_MISMATCH"):
            chain.verify(self.store, first["chain_head_sha256"], 1)

    def test_forged_hardware_pass_invalid_even_with_new_hash(self):
        self.append_first()
        altered = json.loads(self.entry(1).read_text())
        altered["hardware_status"] = "PASS"
        self.entry(1).write_bytes(chain.stable_bytes(altered))
        with self.assertRaisesRegex(chain.ChainError, "claimed hardware PASS"):
            chain.verify(self.store, chain.sha256(self.entry(1).read_bytes()), 1)

    def test_changed_zip_or_receipt_rejected_on_replay(self):
        first = self.append_first()
        with self.first_zip.open("ab") as stream:
            stream.write(b"CORRUPTION")
        with self.assertRaises(replay.ReplayError):
            chain.verify(self.store, first["chain_head_sha256"], 1)
        self.first_zip.write_bytes(self.fixture.destination.read_bytes())
        with self.first_receipt.open("ab") as stream:
            stream.write(b"MODIFIED")
        with self.assertRaisesRegex(replay.ReplayError, "RECEIPT_SHA256_MISMATCH"):
            chain.verify(self.store, first["chain_head_sha256"], 1)

    def test_untrusted_head_is_rejected_even_if_chain_internally_consistent(self):
        first = self.append_first()
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_HEAD_MISMATCH"):
            chain.verify(self.store, "f" * 64, 1)
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_COUNT_MISMATCH"):
            chain.verify(self.store, first["chain_head_sha256"], 2)

    def test_append_requires_correct_prior_head_and_count(self):
        first = self.append_first()
        self.prepare_second()
        for head, count in ((chain.GENESIS, 0), ("f" * 64, 1)):
            with self.subTest(head=head), self.assertRaises(chain.ChainError):
                self.append_second(head) if count == 1 else chain.append(
                    self.store, "archives/second.zip", "receipts/second.json",
                    self.second_sha, self.second_receipt_sha, head, count)
        self.assertFalse(self.entry(2).exists())
        self.append_second(first["chain_head_sha256"])

    def test_refuse_same_archive_or_receipt_second_time(self):
        a = self.append_first()
        with self.assertRaisesRegex(chain.ChainError, "REPLAYED_EVIDENCE"):
            chain.append(self.store, "archives/first.zip",
                         "receipts/first.json", self.first_sha,
                         self.first_receipt_sha, a["chain_head_sha256"], 1)
        self.assertFalse(self.entry(2).exists())

    def test_untracked_files_and_symlinks_fail_closed(self):
        a = self.append_first()
        (self.store / "chain" / "extra.txt").write_text("not part of chain")
        with self.assertRaisesRegex(chain.ChainError, "unexpected"):
            chain.verify(self.store, a["chain_head_sha256"], 1)
        (self.store / "chain" / "extra.txt").unlink()
        self.first_zip.unlink()
        self.first_zip.symlink_to(self.fixture.destination)
        with self.assertRaisesRegex(chain.ChainError, "symbolic link"):
            chain.verify(self.store, a["chain_head_sha256"], 1)

    def test_noncanonical_duplicate_key_and_numbering_overflow_rejected(self):
        a = self.append_first()
        with self.entry(1).open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(chain.ChainError, "NONCANONICAL"):
            chain.verify(self.store, a["chain_head_sha256"], 1)
        self.entry(1).write_text('{"schema":"a","schema":"b"}')
        with self.assertRaises(bundle.BundleError):
            chain.verify(self.store, a["chain_head_sha256"], 1)

    def test_invalid_relative_archive_path_rejected_without_new_entry(self):
        for name in ("../first.zip", "/tmp/test.zip", "chain/another.zip",
                     "archives/./first.zip", "archives\\first.zip"):
            with self.subTest(name=name), self.assertRaises(chain.ChainError):
                chain.append(self.store, name, "receipts/first.json",
                             self.first_sha, self.first_receipt_sha, chain.GENESIS, 0)
        self.assertFalse(self.entry(1).exists())

    def test_cli_two_steps_hardware_never_auto_approved(self):
        cmd = self.cli(
            "append", str(self.store), "--expected-count", "0",
            "--expected-head-sha256", chain.GENESIS,
            "--archive", "archives/first.zip", "--receipt", "receipts/first.json",
            "--archive-sha256", self.first_sha,
            "--receipt-sha256", self.first_receipt_sha)
        self.assertEqual(cmd.returncode, 0, cmd.stdout + cmd.stderr)
        head = json.loads(cmd.stdout)["chain_head_sha256"]
        verified = self.cli(
            "verify", str(self.store), "--expected-count", "1",
            "--expected-head-sha256", head)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        failed = self.cli(
            "verify", str(self.store), "--expected-count", "1",
            "--expected-head-sha256", "e" * 64)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(json.loads(failed.stdout)["result"], "INVALID_EVIDENCE")

    def test_prior_entries_and_original_zip_not_modified_by_append(self):
        first = self.append_first()
        old_entry = self.entry(1).read_bytes()
        old_zip = self.first_zip.read_bytes()
        old_receipt = self.first_receipt.read_bytes()
        self.prepare_second()
        self.append_second(first["chain_head_sha256"])
        self.assertEqual(old_entry, self.entry(1).read_bytes())
        self.assertEqual(old_zip, self.first_zip.read_bytes())
        self.assertEqual(old_receipt, self.first_receipt.read_bytes())


if __name__ == "__main__":
    unittest.main()
