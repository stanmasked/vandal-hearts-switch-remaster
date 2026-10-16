#!/usr/bin/env python3
"""Stage 224 regression suite: two host snapshots and independent ZIP anchors."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import archive_switch_audio_handoff as transfer  # noqa: E402
import compare_switch_audio_archive_reports as comparator  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_archive_switch_audio_handoff import PortableArchiveTests  # noqa: E402


class CrossComputerArchiveTests(unittest.TestCase):
    def setUp(self):
        fixture = PortableArchiveTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.fixture.fixture.base
        self.origin_zip = fixture.destination
        self.received_zip = self.root / "copy-on-other-computer.zip"
        self.origin_report = self.root / "origin-snapshot.json"
        self.received_report = self.root / "recipient-snapshot.json"
        self.origin_sha = fixture.create()["archive_sha256"]
        shutil.copyfile(self.origin_zip, self.received_zip)
        self.received_sha = self.origin_sha

    def snapshot(self, archive, sha, output):
        comparator.save_snapshot(archive, sha, output)
        return comparator.read_snapshot(output)

    def source(self):
        if not self.origin_report.exists():
            self.snapshot(self.origin_zip, self.origin_sha, self.origin_report)
        return comparator.verify_report(self.origin_report, self.origin_zip, self.origin_sha)

    def received(self):
        if not self.received_report.exists():
            self.snapshot(self.received_zip, self.received_sha, self.received_report)
        return comparator.verify_report(
            self.received_report, self.received_zip, self.received_sha)

    def compare(self):
        return comparator.compare(self.source(), self.received())

    def make_received_archive(self, **options):
        self.received_zip.unlink()
        self.fixture.fixture.save_cards()
        self.fixture.fixture.fixture.write_record()
        checked = transfer.create_archive(
            self.fixture.fixture.fixture.root,
            self.fixture.fixture.fixture.observations,
            self.fixture.fixture.cards, self.received_zip, **options)
        self.received_sha = checked["archive_sha256"]
        return checked

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" /
                                 "compare_switch_audio_archive_reports.py"), *args],
            capture_output=True, text=True, check=False)

    def compare_cli(self, *args):
        return self.cli(
            "compare",
            "--source-report", str(self.origin_report),
            "--source-archive", str(self.origin_zip),
            "--source-sha256", self.origin_sha,
            "--received-report", str(self.received_report),
            "--received-archive", str(self.received_zip),
            "--received-sha256", self.received_sha,
            *args,
        )

    def test_identical_cross_host_snapshots_are_equal_not_hardware_pass(self):
        a, b = self.source(), self.received()
        self.assertEqual(a, b)
        result = self.compare()
        self.assertEqual(result["result"], "EXACT_MATCH")
        self.assertEqual(result["differences"], [])
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertEqual(len(a["scenario_statuses"]), 7)
        self.assertEqual(len(a["member_inventory"]), 7)

    def test_container_only_repacked_zip_is_separated_from_source_bytes(self):
        with zipfile.ZipFile(self.received_zip, "r") as original:
            values = [(info.filename, original.read(info)) for info in original.infolist()]
        with zipfile.ZipFile(self.received_zip, "w") as updated:
            for name, data in values:
                info = transfer.zip_entry(name)
                info.compress_type = zipfile.ZIP_STORED
                updated.writestr(info, data)
        self.received_sha = bundle.digest_file(self.received_zip)[1]
        result = self.compare()
        self.assertEqual(result["result"], "CONTAINER_ONLY_DIFFERENCE")
        self.assertEqual([x["code"] for x in result["differences"]],
                         ["ZIP_CONTAINER_REPACKAGED"])
        self.assertNotEqual(result["source_archive_sha256"],
                            result["received_archive_sha256"])

    def test_operator_card_mutation_yields_precise_filename(self):
        self.fixture.fixture.records[0]["observer_note"] = (
            "Changed after archiving, synthetic test")
        self.make_received_archive()
        result = self.compare()
        self.assertEqual(result["result"], "EVIDENCE_CHANGED")
        changed = [x for x in result["differences"]
                   if x["code"] == "EVIDENCE_BYTES_DIFFER"]
        self.assertEqual([x["subject"] for x in changed], ["cards/first.json"])
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")

    def test_missing_card_in_receiver_is_detailed_and_review_different(self):
        (self.fixture.fixture.cards / "second.json").unlink()
        # Original fixture writes no cards here; create directly to preserve removal.
        self.received_zip.unlink()
        self.fixture.fixture.fixture.write_record()
        data = transfer.create_archive(
            self.fixture.fixture.fixture.root,
            self.fixture.fixture.fixture.observations,
            self.fixture.fixture.cards, self.received_zip)
        self.received_sha = data["archive_sha256"]
        result = self.compare()
        self.assertEqual(result["result"], "EVIDENCE_CHANGED")
        self.assertIn("EVIDENCE_FILE_MISSING",
                      {r["code"] for r in result["differences"]})
        self.assertEqual(result["received_review"], "INCONCLUSIVE")

    def test_different_review_options_without_byte_change_are_reported(self):
        self.make_received_archive(require_h06=True)
        result = self.compare()
        self.assertEqual(result["result"], "REVIEW_CHANGED")
        self.assertEqual(result["source_review"],
                         "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(result["received_review"], "INCONCLUSIVE")
        self.assertEqual(
            {x["subject"] for x in result["differences"]},
            {"handoff_review", "scenario_statuses", "retest_scenarios"})

    def test_report_tampering_is_rejected_before_comparison(self):
        self.source()
        b = self.snapshot(self.received_zip, self.received_sha,
                          self.received_report)
        b["handoff_review"] = "INVESTIGATE"
        self.received_report.write_text(json.dumps(b))
        with self.assertRaisesRegex(comparator.ComparisonError, "SAVED_REPORT_MISMATCH"):
            comparator.verify_report(self.received_report, self.received_zip,
                                     self.received_sha)

    def test_origin_report_replacement_is_rejected(self):
        a = self.source()
        a["member_inventory"][0]["sha256"] = "0" * 64
        self.origin_report.write_text(json.dumps(a))
        with self.assertRaisesRegex(comparator.ComparisonError, "SAVED_REPORT_MISMATCH"):
            comparator.verify_report(self.origin_report, self.origin_zip,
                                     self.origin_sha)

    def test_detached_sha_mismatch_blocks_snapshot_creation(self):
        target = self.root / "should-not-exist.json"
        with self.assertRaisesRegex(transfer.ArchiveError, "ARCHIVE_SHA256_MISMATCH"):
            comparator.save_snapshot(self.origin_zip, "0" * 64, target)
        self.assertFalse(target.exists())

    def test_modified_zip_invalid_even_if_snapshot_claims_old_bytes(self):
        self.source()
        self.snapshot(self.received_zip, self.received_sha, self.received_report)
        with self.received_zip.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(transfer.ArchiveError, "ARCHIVE_SHA256_MISMATCH"):
            self.received()

    def test_wrong_snapshot_hardware_status_fails_closed(self):
        self.source()
        obj = json.loads(self.origin_report.read_text())
        obj["hardware_status"] = "PASS"
        self.origin_report.write_text(json.dumps(obj))
        with self.assertRaisesRegex(comparator.ComparisonError, "hardware status"):
            comparator.read_snapshot(self.origin_report)

    def test_unknown_snapshot_field_or_duplicate_key_is_rejected(self):
        self.source()
        obj = json.loads(self.origin_report.read_text())
        obj["independent_operator_signed"] = True
        self.origin_report.write_text(json.dumps(obj))
        with self.assertRaisesRegex(comparator.ComparisonError, "schema"):
            comparator.read_snapshot(self.origin_report)
        self.origin_report.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaises(bundle.BundleError):
            comparator.read_snapshot(self.origin_report)

    def test_refuse_overwriting_existing_report(self):
        self.source()
        first = self.origin_report.read_bytes()
        with self.assertRaisesRegex(comparator.ComparisonError, "already exists"):
            comparator.save_snapshot(self.origin_zip, self.origin_sha, self.origin_report)
        self.assertEqual(first, self.origin_report.read_bytes())

    def test_source_and_received_snapshots_are_deterministic(self):
        one = self.source()
        extra = self.root / "another-report.json"
        two = self.snapshot(self.origin_zip, self.origin_sha, extra)
        self.assertEqual(one, two)
        self.assertEqual(self.origin_report.read_bytes(), extra.read_bytes())

    def test_cli_snapshot_compare_json_and_markdown(self):
        origin = self.cli(
            "snapshot", str(self.origin_zip),
            "--expected-sha256", self.origin_sha,
            "--output", str(self.origin_report))
        self.assertEqual(origin.returncode, 0, origin.stdout + origin.stderr)
        rec = self.cli(
            "snapshot", str(self.received_zip),
            "--expected-sha256", self.received_sha,
            "--output", str(self.received_report))
        self.assertEqual(rec.returncode, 0, rec.stdout + rec.stderr)
        run = self.compare_cli()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["result"], "EXACT_MATCH")
        self.assertEqual(payload["hardware_status"], "HARDWARE NOT TESTED")
        rendered = self.compare_cli("--format", "markdown")
        self.assertEqual(rendered.returncode, 0)
        self.assertIn("HARDWARE NOT TESTED", rendered.stdout)
        self.assertIn("No differences", rendered.stdout)

    def test_cli_reports_changes_with_zero_exit_code_not_acceptance(self):
        self.source()
        self.fixture.fixture.records[0]["observer_note"] = "Different notes"
        self.make_received_archive()
        self.received()
        result = self.compare_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "EVIDENCE_CHANGED")

    def test_invalid_archive_cli_returns_two_not_reconciled(self):
        self.source()
        self.received()
        result = self.compare_cli("--format", "json")
        self.assertEqual(result.returncode, 0)
        bad = self.cli(
            "compare",
            "--source-report", str(self.origin_report),
            "--source-archive", str(self.origin_zip),
            "--source-sha256", "0" * 64,
            "--received-report", str(self.received_report),
            "--received-archive", str(self.received_zip),
            "--received-sha256", self.received_sha)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(json.loads(bad.stdout)["result"], "INVALID_EVIDENCE")

    def test_file_added_or_missing_in_canonical_snapshots(self):
        before, after = self.source(), self.received()
        after = json.loads(json.dumps(after))
        after["member_inventory"].pop()
        compare = comparator.compare(before, after)
        self.assertEqual(compare["result"], "EVIDENCE_CHANGED")
        self.assertIn("EVIDENCE_FILE_MISSING",
                      {x["code"] for x in compare["differences"]})

    def test_source_archives_and_reports_untouched_by_compare(self):
        self.source()
        self.received()
        observed = {
            "origin_zip": self.origin_zip.read_bytes(),
            "received_zip": self.received_zip.read_bytes(),
            "origin_report": self.origin_report.read_bytes(),
            "received_report": self.received_report.read_bytes(),
        }
        result = self.compare()
        self.assertEqual(result["result"], "EXACT_MATCH")
        self.assertEqual(observed["origin_zip"], self.origin_zip.read_bytes())
        self.assertEqual(observed["received_zip"], self.received_zip.read_bytes())
        self.assertEqual(observed["origin_report"], self.origin_report.read_bytes())
        self.assertEqual(observed["received_report"], self.received_report.read_bytes())


if __name__ == "__main__":
    unittest.main()
