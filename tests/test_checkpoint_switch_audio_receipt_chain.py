#!/usr/bin/env python3
"""Stage 227 synthetic checkpoint and two-root chain comparison regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import checkpoint_switch_audio_receipt_chain as checkpoint  # noqa: E402
import chain_switch_audio_receipts as chain  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_chain_switch_audio_receipts import ChainedReceiptTests  # noqa: E402


class CrossCopyCheckpointTests(unittest.TestCase):
    def setUp(self):
        original = ChainedReceiptTests("runTest")
        original.setUp()
        self.addCleanup(original.doCleanups)
        self.fixture = original
        self.source = original.store
        self.first = original.append_first()
        self.root = original.fixture.fixture.fixture.base
        self.received = self.root / "copied-on-another-computer"
        shutil.copytree(self.source, self.received)
        self.source_file = self.root / "source-checkpoint.json"
        self.received_file = self.root / "received-checkpoint.json"
        self.source_head = self.first["chain_head_sha256"]
        self.received_head = self.source_head
        self.source_count = self.received_count = 1

    def capture(self, storage, head, count, target):
        return checkpoint.create_checkpoint(storage, head, count, target)

    def both(self):
        origin = self.capture(self.source, self.source_head,
                              self.source_count, self.source_file)
        remote = self.capture(self.received, self.received_head,
                              self.received_count, self.received_file)
        return origin, remote

    def compare(self):
        a = checkpoint.reread_and_replay(
            self.source, self.source_file, bundle.digest_file(self.source_file)[1],
            self.source_head, self.source_count)
        b = checkpoint.reread_and_replay(
            self.received, self.received_file, bundle.digest_file(self.received_file)[1],
            self.received_head, self.received_count)
        return checkpoint.compare_histories(a, b)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" /
                                 "checkpoint_switch_audio_receipt_chain.py"), *args],
            capture_output=True, text=True, check=False)

    def compare_cli(self, *args):
        return self.cli(
            "compare", "--source-root", str(self.source),
            "--source-checkpoint", str(self.source_file),
            "--source-checkpoint-sha256",
            bundle.digest_file(self.source_file)[1],
            "--source-head-sha256", self.source_head,
            "--source-count", str(self.source_count),
            "--received-root", str(self.received),
            "--received-checkpoint", str(self.received_file),
            "--received-checkpoint-sha256",
            bundle.digest_file(self.received_file)[1],
            "--received-head-sha256", self.received_head,
            "--received-count", str(self.received_count), *args)

    def test_copied_history_produces_equal_checkpoints_and_not_hardware_pass(self):
        a, b = self.both()
        self.assertEqual(a["checkpoint_sha256"], b["checkpoint_sha256"])
        self.assertEqual(self.source_file.read_bytes(), self.received_file.read_bytes())
        result = self.compare()
        self.assertEqual(result["result"], "EXACT_HISTORY_MATCH")
        self.assertEqual(result["differences"], [])
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")

    def test_checkpoint_contains_final_head_ordered_fingerprints(self):
        a, _ = self.both()
        v = checkpoint.read_checkpoint(self.source_file, a["checkpoint_sha256"])
        self.assertEqual(v["count"], 1)
        self.assertEqual(v["entries"][0]["record_sha256"], self.source_head)
        self.assertEqual(v["chain_head_sha256"], self.source_head)
        self.assertEqual(v["physical_independence"], "NOT_ATTESTED")
        self.assertEqual(v["entries_sha256"],
                         checkpoint.entries_sha256(v["entries"]))

    def test_repeated_checkpoints_are_byte_identical_regardless_of_local_path(self):
        self.both()
        extra = self.root / "third-checkpoint.json"
        checkpoint.create_checkpoint(self.source, self.source_head, 1, extra)
        self.assertEqual(extra.read_bytes(), self.received_file.read_bytes())

    def test_truncated_received_history_is_rejected_using_independent_count(self):
        self.both()
        (self.received / "chain" / "000001.json").unlink()
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_COUNT_MISMATCH"):
            self.compare()

    def test_substituted_chain_record_is_detected(self):
        self.both()
        path = self.received / "chain" / "000001.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["handoff_review"] = "INVESTIGATE"
        path.write_bytes(chain.stable_bytes(data))
        with self.assertRaises(chain.ChainError):
            self.compare()

    def test_changed_received_nro_archive_is_rejected_after_copy(self):
        self.both()
        path = self.received / "archives" / "first.zip"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(Exception, "ARCHIVE_CHANGED|ARCHIVE_SHA256_MISMATCH"):
            self.compare()

    def test_wrong_pinned_checkpoint_sha_is_rejected(self):
        a, _ = self.both()
        with self.assertRaisesRegex(checkpoint.CheckpointError, "CHECKPOINT_SHA256_MISMATCH"):
            checkpoint.read_checkpoint(self.source_file, "f" * 64)
        self.assertNotEqual(a["checkpoint_sha256"], "f" * 64)

    def test_checkpoint_forgery_even_if_rehashed_must_match_replayed_chain(self):
        self.both()
        card = json.loads(self.received_file.read_text(encoding="utf-8"))
        card["entries"][0]["handoff_review"] = "INVESTIGATE"
        card["entries_sha256"] = checkpoint.entries_sha256(card["entries"])
        self.received_file.write_bytes(checkpoint.to_bytes(card))
        with self.assertRaisesRegex(checkpoint.CheckpointError, "CHECKPOINT_REPORT_DRIFT"):
            self.compare()

    def test_hardware_pass_and_invalid_sequence_fail_closed(self):
        a, _ = self.both()
        obj = json.loads(self.source_file.read_text())
        obj["hardware_status"] = "PASS"
        self.source_file.write_bytes(checkpoint.to_bytes(obj))
        with self.assertRaisesRegex(checkpoint.CheckpointError, "forged hardware"):
            checkpoint.read_checkpoint(
                self.source_file, bundle.digest_file(self.source_file)[1])
        self.source_file.write_bytes(checkpoint.to_bytes(
            checkpoint.canonical_checkpoint(
                chain.verify(self.source, self.source_head, 1))))
        obj = json.loads(self.source_file.read_text())
        obj["entries"][0]["sequence"] = 2
        obj["entries_sha256"] = checkpoint.entries_sha256(obj["entries"])
        self.source_file.write_bytes(checkpoint.to_bytes(obj))
        with self.assertRaisesRegex(checkpoint.CheckpointError, "out-of-order"):
            checkpoint.read_checkpoint(
                self.source_file, bundle.digest_file(self.source_file)[1])

    def test_duplicate_json_keys_or_reformatting_rejected(self):
        self.both()
        self.received_file.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaises(bundle.BundleError):
            checkpoint.read_checkpoint(
                self.received_file, bundle.digest_file(self.received_file)[1])
        obj = checkpoint.canonical_checkpoint(
            chain.verify(self.received, self.received_head, self.received_count))
        self.received_file.write_text(json.dumps(obj, indent=2))
        with self.assertRaisesRegex(checkpoint.CheckpointError, "NONCANONICAL"):
            checkpoint.read_checkpoint(
                self.received_file, bundle.digest_file(self.received_file)[1])

    def test_refuses_overwrite_or_checkpoint_inside_original_evidence(self):
        self.capture(self.source, self.source_head, 1, self.source_file)
        original_bytes = self.source_file.read_bytes()
        with self.assertRaisesRegex(checkpoint.CheckpointError, "already exists"):
            self.capture(self.source, self.source_head, 1, self.source_file)
        self.assertEqual(original_bytes, self.source_file.read_bytes())
        inside = self.source / "would-write.json"
        with self.assertRaisesRegex(checkpoint.CheckpointError, "outside"):
            self.capture(self.source, self.source_head, 1, inside)
        self.assertFalse(inside.exists())

    def test_bad_head_or_count_prevents_checkpoint_creation(self):
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_HEAD_MISMATCH"):
            self.capture(self.source, "f" * 64, 1, self.source_file)
        self.assertFalse(self.source_file.exists())
        with self.assertRaisesRegex(chain.ChainError, "CHAIN_COUNT_MISMATCH"):
            self.capture(self.source, self.source_head, 2, self.source_file)
        self.assertFalse(self.source_file.exists())

    def test_one_valid_copy_is_a_prefix_of_an_independently_pinned_later_copy(self):
        self.fixture.prepare_second()
        extended = self.fixture.append_second(self.source_head)
        self.source_count = 2
        self.source_head = extended["chain_head_sha256"]
        self.both()
        result = self.compare()
        self.assertEqual(result["result"], "RECEIVED_HISTORY_SHORTER")
        self.assertEqual([x["code"] for x in result["differences"]],
                         ["MISSING_IN_RECEIVED_COPY"])

    def test_valid_received_extension_is_not_mistaken_for_same_copy(self):
        # Copy a valid extended history, then leave the source at its earlier
        # independently pinned checkpoint: one entry vs two in the receiver.
        self.fixture.prepare_second()
        extended = self.fixture.append_second(self.source_head)
        shutil.rmtree(self.received)
        shutil.copytree(self.source, self.received)
        (self.source / "chain" / "000002.json").unlink()
        (self.source / "archives" / "second.zip").unlink()
        (self.source / "receipts" / "second.json").unlink()
        self.received_head = extended["chain_head_sha256"]
        self.received_count = 2
        self.both()
        result = self.compare()
        self.assertEqual(result["result"], "RECEIVED_HISTORY_EXTENDED")
        self.assertEqual([x["code"] for x in result["differences"]],
                         ["ADDED_IN_RECEIVED_COPY"])

    def test_divergent_link_classification_is_not_false_exact_match(self):
        a = checkpoint.canonical_checkpoint(
            chain.verify(self.source, self.source_head, 1))
        b = copy.deepcopy(a)
        b["entries"][0]["record_sha256"] = "e" * 64
        b["chain_head_sha256"] = "e" * 64
        b["entries_sha256"] = checkpoint.entries_sha256(b["entries"])
        outcome = checkpoint.compare_histories(a, b)
        self.assertEqual(outcome["result"], "DIVERGENT_VALID_HISTORIES")
        self.assertEqual(outcome["differences"][0]["code"], "DIVERGENT_CHAIN_ENTRY")
        # The fabricated variant is only a classification fixture; full
        # reread_and_replay rejects it when tied to actual source evidence.
        self.both()
        self.received_file.write_bytes(checkpoint.to_bytes(b))
        with self.assertRaisesRegex(
                checkpoint.CheckpointError, "CHECKPOINT_ANCHOR_MISMATCH"):
            self.compare()

    def test_cli_checkpoint_compare_and_read_only_inputs(self):
        before = (self.source / "chain" / "000001.json").read_bytes()
        z1 = self.cli(
            "checkpoint", str(self.source), "--expected-count", "1",
            "--expected-head-sha256", self.source_head,
            "--output", str(self.source_file))
        self.assertEqual(z1.returncode, 0, z1.stdout + z1.stderr)
        z2 = self.cli(
            "checkpoint", str(self.received), "--expected-count", "1",
            "--expected-head-sha256", self.received_head,
            "--output", str(self.received_file))
        self.assertEqual(z2.returncode, 0, z2.stdout + z2.stderr)
        result = self.compare_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "EXACT_HISTORY_MATCH")
        self.assertEqual(json.loads(result.stdout)["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(before, (self.source / "chain" / "000001.json").read_bytes())
        self.assertEqual(
            (self.source / "archives" / "first.zip").read_bytes(),
            (self.received / "archives" / "first.zip").read_bytes())

    def test_cli_invalid_anchor_returns_two_without_fabricated_result(self):
        self.both()
        args = [
            "compare", "--source-root", str(self.source),
            "--source-checkpoint", str(self.source_file),
            "--source-checkpoint-sha256", "f" * 64,
            "--source-head-sha256", self.source_head,
            "--source-count", "1",
            "--received-root", str(self.received),
            "--received-checkpoint", str(self.received_file),
            "--received-checkpoint-sha256",
            bundle.digest_file(self.received_file)[1],
            "--received-head-sha256", self.received_head,
            "--received-count", "1",
        ]
        failed = self.cli(*args)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(json.loads(failed.stdout)["result"], "INVALID_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
