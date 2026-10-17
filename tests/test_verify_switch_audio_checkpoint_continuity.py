#!/usr/bin/env python3
"""Stage 228: synthetic checkpoint preservation and fail-closed regression."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import chain_switch_audio_receipts as chain  # noqa: E402
import checkpoint_switch_audio_receipt_chain as checkpoint  # noqa: E402
import verify_switch_audio_checkpoint_continuity as continuity  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_chain_switch_audio_receipts import ChainedReceiptTests  # noqa: E402


class CheckpointContinuityTests(unittest.TestCase):
    def setUp(self):
        parent = ChainedReceiptTests("runTest")
        parent.setUp()
        self.addCleanup(parent.doCleanups)
        self.fixture = parent
        self.storage = parent.store
        self.root = parent.fixture.fixture.fixture.base
        first = parent.append_first()
        self.old_count = 1
        self.old_head = first["chain_head_sha256"]
        self.old_path = self.root / "pinned-before-expansion.json"
        checkpoint.create_checkpoint(self.storage, self.old_head, self.old_count,
                                     self.old_path)
        self.old_hash = bundle.digest_file(self.old_path)[1]
        self.current_path = self.root / "pinned-after-expansion.json"
        self.current_count = 1
        self.current_head = self.old_head

    def extend(self):
        self.fixture.prepare_second()
        added = self.fixture.append_second(self.old_head)
        self.current_count = 2
        self.current_head = added["chain_head_sha256"]

    def checkpoint_current(self):
        return checkpoint.create_checkpoint(
            self.storage, self.current_head, self.current_count,
            self.current_path)

    def assess(self, **overrides):
        kwargs = {
            "prior_checkpoint": self.old_path,
            "prior_checkpoint_sha256": self.old_hash,
            "prior_head_sha256": self.old_head,
            "prior_count": self.old_count,
            "current_root": self.storage,
            "current_checkpoint": self.current_path,
            "current_checkpoint_sha256": bundle.digest_file(self.current_path)[1],
            "current_head_sha256": self.current_head,
            "current_count": self.current_count,
        }
        kwargs.update(overrides)
        return continuity.verify_continuity(**kwargs)

    def cli(self, *extra):
        args = [
            sys.executable, str(ROOT / "tools" /
                                "verify_switch_audio_checkpoint_continuity.py"),
            "--prior-checkpoint", str(self.old_path),
            "--prior-checkpoint-sha256", self.old_hash,
            "--prior-head-sha256", self.old_head,
            "--prior-count", str(self.old_count),
            "--current-root", str(self.storage),
            "--current-checkpoint", str(self.current_path),
            "--current-checkpoint-sha256",
            bundle.digest_file(self.current_path)[1],
            "--current-head-sha256", self.current_head,
            "--current-count", str(self.current_count),
            *extra,
        ]
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def test_valid_extension_preserves_all_prior_records_and_replays_zip(self):
        self.extend()
        self.checkpoint_current()
        result = self.assess(require_growth=True)
        self.assertEqual(result["result"], "CONTINUITY_PRESERVED_WITH_NEW_RECORDS")
        self.assertEqual((result["prior_count"], result["current_count"]), (1, 2))
        self.assertEqual(result["new_records"], 1)
        self.assertEqual(result["new_record_inventory"][0]["sequence"], 2)
        self.assertFalse(result["old_records_changed"])
        self.assertTrue(result["current_root_fully_replayed"])
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertEqual(result["physical_independence"], "NOT_ATTESTED")

    def test_no_growth_is_reported_explicitly_without_false_new_event(self):
        self.checkpoint_current()
        result = self.assess()
        self.assertEqual(result["result"], "CONTINUITY_PRESERVED_NO_GROWTH")
        self.assertEqual(result["new_records"], 0)
        self.assertEqual(result["new_record_inventory"], [])
        with self.assertRaisesRegex(continuity.ContinuityError, "HISTORY_NO_GROWTH"):
            self.assess(require_growth=True)

    def test_genesis_checkpoint_is_valid_prefix_of_one_record(self):
        empty = self.root / "empty-history"
        (empty / "chain").mkdir(parents=True)
        genesis = self.root / "genesis-checkpoint.json"
        checkpoint.create_checkpoint(empty, chain.GENESIS, 0, genesis)
        self.checkpoint_current()
        result = self.assess(
            prior_checkpoint=genesis,
            prior_checkpoint_sha256=bundle.digest_file(genesis)[1],
            prior_head_sha256=chain.GENESIS,
            prior_count=0,
            require_growth=True)
        self.assertEqual(result["new_records"], 1)
        self.assertEqual(result["prior_chain_head_sha256"], chain.GENESIS)

    def test_incorrect_previous_checkpoint_hash_fails_closed(self):
        self.extend()
        self.checkpoint_current()
        with self.assertRaisesRegex(checkpoint.CheckpointError,
                                    "CHECKPOINT_SHA256_MISMATCH"):
            self.assess(prior_checkpoint_sha256="f" * 64)

    def test_changed_old_checkpoint_is_rejected_even_with_same_filename(self):
        self.extend()
        self.checkpoint_current()
        self.old_path.write_bytes(self.old_path.read_bytes() + b"edited")
        with self.assertRaisesRegex(checkpoint.CheckpointError,
                                    "CHECKPOINT_SHA256_MISMATCH"):
            self.assess()

    def test_rehashed_old_checkpoint_disagrees_with_original_head(self):
        self.extend()
        self.checkpoint_current()
        record = json.loads(self.old_path.read_text())
        record["entries"][0]["record_sha256"] = "e" * 64
        record["chain_head_sha256"] = "e" * 64
        record["entries_sha256"] = checkpoint.entries_sha256(record["entries"])
        self.old_path.write_bytes(checkpoint.to_bytes(record))
        with self.assertRaisesRegex(continuity.ContinuityError,
                                    "HISTORY_PRIOR_ANCHOR_MISMATCH"):
            self.assess(prior_checkpoint_sha256=bundle.digest_file(self.old_path)[1])

    def test_wrong_old_count_is_rejected_even_when_new_history_is_valid(self):
        self.extend()
        self.checkpoint_current()
        with self.assertRaisesRegex(continuity.ContinuityError,
                                    "HISTORY_PRIOR_ANCHOR_MISMATCH"):
            self.assess(prior_count=2)
        with self.assertRaisesRegex(continuity.ContinuityError,
                                    "HISTORY_PRIOR_ANCHOR_MISMATCH"):
            self.assess(prior_head_sha256="f" * 64)

    def test_wrong_new_count_or_head_must_fail_strict_current_replay(self):
        self.extend()
        self.checkpoint_current()
        with self.assertRaisesRegex(checkpoint.CheckpointError,
                                    "CHECKPOINT_ANCHOR_MISMATCH"):
            self.assess(current_count=1)
        with self.assertRaisesRegex(checkpoint.CheckpointError,
                                    "CHECKPOINT_ANCHOR_MISMATCH"):
            self.assess(current_head_sha256="f" * 64)

    def test_corrupt_zip_in_old_prefix_detected_even_if_new_checkpoint_exists(self):
        self.extend()
        self.checkpoint_current()
        original = self.fixture.first_zip
        original.write_bytes(original.read_bytes() + b"altered-zip")
        with self.assertRaises(Exception):
            self.assess()

    def test_changed_prior_chain_record_rejected_by_fresh_replay(self):
        self.extend()
        self.checkpoint_current()
        record = self.storage / "chain" / "000001.json"
        record.write_bytes(record.read_bytes() + b"tamper")
        with self.assertRaises(chain.ChainError):
            self.assess()

    def test_deleted_prior_chain_record_is_detected_after_extension(self):
        self.extend()
        self.checkpoint_current()
        (self.storage / "chain" / "000001.json").unlink()
        # The chain directory validates contiguous numbering before total count.
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_GAP_OR_REORDER"):
            self.assess()

    def test_removed_new_receipt_detected_by_full_current_audit(self):
        self.extend()
        self.checkpoint_current()
        (self.storage / "receipts" / "second.json").unlink()
        with self.assertRaisesRegex(chain.ChainError, "evidence file missing"):
            self.assess()

    def test_reordered_old_prefix_is_rejected_not_accepted_as_growth(self):
        self.extend()
        self.checkpoint_current()
        old = checkpoint.read_checkpoint(self.old_path, self.old_hash)
        current = checkpoint.read_checkpoint(
            self.current_path, bundle.digest_file(self.current_path)[1])
        modified = copy.deepcopy(current)
        modified["entries"][0]["record_sha256"] = "e" * 64
        modified["entries_sha256"] = checkpoint.entries_sha256(modified["entries"])
        with self.assertRaisesRegex(continuity.ContinuityError,
                                    "HISTORY_PREFIX_DIVERGED"):
            continuity.assess_continuity(old, modified)

    def test_shorter_current_history_is_rejected_even_when_well_formed(self):
        self.extend()
        self.checkpoint_current()
        previous = checkpoint.read_checkpoint(
            self.current_path, bundle.digest_file(self.current_path)[1])
        shorter = checkpoint.read_checkpoint(self.old_path, self.old_hash)
        with self.assertRaisesRegex(continuity.ContinuityError,
                                    "HISTORY_ROLLBACK"):
            continuity.assess_continuity(previous, shorter)

    def test_extra_records_cannot_be_disguised_as_no_growth(self):
        self.extend()
        self.checkpoint_current()
        old = checkpoint.read_checkpoint(self.old_path, self.old_hash)
        new = checkpoint.read_checkpoint(
            self.current_path, bundle.digest_file(self.current_path)[1])
        self.assertEqual(continuity.assess_continuity(
            old, new, require_growth=True)["new_records"], 1)

    def test_cli_success_and_strict_growth_requirement(self):
        self.extend()
        self.checkpoint_current()
        response = self.cli("--require-growth")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        data = json.loads(response.stdout)
        self.assertEqual(data["result"], "CONTINUITY_PRESERVED_WITH_NEW_RECORDS")
        self.assertEqual(data["hardware_status"], "HARDWARE NOT TESTED")
        fail = self.cli("--prior-checkpoint-sha256", "0" * 64)
        self.assertEqual(fail.returncode, 2)
        self.assertEqual(json.loads(fail.stdout)["result"], "INVALID_EVIDENCE")

    def test_verify_never_edits_prior_checkpoint_chain_zip_or_receipts(self):
        self.extend()
        self.checkpoint_current()
        old_bytes = self.old_path.read_bytes()
        fresh_bytes = self.current_path.read_bytes()
        tracked = {
            str(p.relative_to(self.storage)): p.read_bytes()
            for p in self.storage.rglob("*") if p.is_file()
        }
        self.assess(require_growth=True)
        self.assertEqual(old_bytes, self.old_path.read_bytes())
        self.assertEqual(fresh_bytes, self.current_path.read_bytes())
        self.assertEqual(tracked, {
            str(p.relative_to(self.storage)): p.read_bytes()
            for p in self.storage.rglob("*") if p.is_file()
        })


if __name__ == "__main__":
    unittest.main()
