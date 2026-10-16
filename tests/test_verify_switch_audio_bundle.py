#!/usr/bin/env python3
"""Stage 213 integrity regressions using only synthetic files, never hardware results."""
from __future__ import annotations

import csv
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import analyze_switch_audio_log as audio  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402


def synthetic_structural_nro() -> bytes:
    """Test fixture with NRO0 layout; NOT executable Nintendo Switch code."""
    content = bytearray(0x100)
    content[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", content, 0x18, 0x100)
    for field, start in ((0x20, 0x80), (0x28, 0xA0), (0x30, 0xC0)):
        struct.pack_into("<II", content, field, start, 0x20)
    return bytes(content)


def write_session(path: Path, pages: int = 1200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(audio.COLUMNS)
        for elapsed, event, status, count in (
                (0, "START", 1, 0), (6000, "EXIT", 0, pages)):
            row = {k: 0 for k in audio.COLUMNS}
            row.update(elapsed_ms=elapsed, event=event, status=status,
                       output_pages=count, output_frames=count * 557,
                       first_pcm_count=1 if event == "EXIT" else 0,
                       last_pcm_us=12000 if event == "EXIT" else 0)
            writer.writerow([row[col] for col in audio.COLUMNS])


class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        (self.root / "nro").mkdir()
        (self.root / "nro" / "vandal-hearts-prototype.nro").write_bytes(
            synthetic_structural_nro()
        )
        self.nro = "nro/vandal-hearts-prototype.nro"
        self.sessions = [
            "session-01/audio-diagnostics-0000.csv",
            "session-02/audio-diagnostics-0001.csv",
        ]
        write_session(self.root / self.sessions[0], 1200)
        write_session(self.root / self.sessions[1], 1300)

    def create(self, sessions=None):
        return bundle.create(self.root, self.nro,
                             self.sessions if sessions is None else sessions,
                             "a" * 40, "")

    def test_valid_manifest_still_requires_manual_hardware_review(self):
        result = self.create()
        self.assertEqual(result["integrity"], "VERIFIED")
        self.assertEqual(result["nro_structure"], "VALID_STRUCTURAL_HEADER_ONLY")
        self.assertEqual(result["build_provenance"], "SELF_REPORTED_UNVERIFIED")
        self.assertEqual(result["telemetry_readiness"], "ENOUGH_DATA_FOR_MANUAL_REVIEW")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["session_count"], 2)
        self.assertEqual(bundle.inspect(self.root), result)
        self.assertEqual([s["observed_pcm_pages"] for s in result["sessions"]],
                         [1200, 1300])

    def test_structural_nro_gate_matches_existing_check_nro_cli(self):
        check = [sys.executable, str(ROOT / "tests" / "check_nro.py"),
                 str(self.root / self.nro)]
        good = subprocess.run(check, check=False, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        data = bytearray((self.root / self.nro).read_bytes())
        struct.pack_into("<II", data, 0x30, 0xF8, 0x20)
        (self.root / self.nro).write_bytes(data)
        bad = subprocess.run(check, check=False, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
        with self.assertRaisesRegex(bundle.BundleError, "data segment"):
            bundle.create(self.root, self.nro, [], "a" * 40, "")

    def test_rejects_non_nro_bytes_even_on_initial_create(self):
        (self.root / self.nro).write_bytes(b"fake extension only")
        with self.assertRaisesRegex(bundle.BundleError, "NRO is too small"):
            self.create()
        self.assertFalse((self.root / bundle.MANIFEST_NAME).exists())

    def test_rejects_nro_magic_and_invalid_sections(self):
        path = self.root / self.nro
        good = bytearray(path.read_bytes())
        damaged = bytearray(good)
        damaged[0x10:0x14] = b"FAKE"
        path.write_bytes(damaged)
        with self.assertRaisesRegex(bundle.BundleError, "NRO0 magic"):
            self.create()
        damaged = bytearray(good)
        struct.pack_into("<II", damaged, 0x28, 0xF8, 0x20)
        path.write_bytes(damaged)
        with self.assertRaisesRegex(bundle.BundleError, "rodata segment"):
            self.create()
        damaged = bytearray(good)
        struct.pack_into("<I", damaged, 0x18, 0x200)
        path.write_bytes(damaged)
        with self.assertRaisesRegex(bundle.BundleError, "declared NRO"):
            self.create()
        path.write_bytes(good)
        self.create()
        # A dishonest edited manifest/hash must not turn a malformed NRO into valid evidence.
        damaged = bytearray(good)
        damaged[0x10:0x14] = b"FAKE"
        path.write_bytes(damaged)
        manifest_file = self.root / bundle.MANIFEST_NAME
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        size, digest = bundle.digest_file(path)
        manifest["nro"].update(size=size, sha256=digest)
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(bundle.BundleError, "NRO0 magic"):
            bundle.inspect(self.root)

    def test_only_header_structure_not_executability(self):
        self.create()
        report = bundle.inspect(self.root)
        self.assertEqual(report["nro_structure"], "VALID_STRUCTURAL_HEADER_ONLY")
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["build_provenance"], "SELF_REPORTED_UNVERIFIED")

    def test_byte_identical_csv_copies_are_not_two_independent_sessions(self):
        (self.root / self.sessions[1]).write_bytes(
            (self.root / self.sessions[0]).read_bytes())
        report = self.create()
        self.assertEqual(report["integrity"], "VERIFIED")
        self.assertEqual(report["telemetry_readiness"], "INCOMPLETE")
        self.assertIn("Identical CSV bytes", report["evidence_warnings"][0])

    def test_nro_modified_after_manifest_is_rejected(self):
        self.create()
        path = self.root / self.nro
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(bundle.BundleError, "size or SHA-256 mismatch"):
            bundle.inspect(self.root)

    def test_corrupted_csv_size_or_byte_is_rejected(self):
        self.create()
        path = self.root / self.sessions[0]
        old = path.read_bytes()
        path.write_bytes(old + b"unexpected")
        with self.assertRaisesRegex(bundle.BundleError, "size or SHA-256 mismatch"):
            bundle.inspect(self.root)
        path.write_bytes(old.replace(b"1200", b"1201"))
        with self.assertRaisesRegex(bundle.BundleError, "size or SHA-256 mismatch"):
            bundle.inspect(self.root)

    def test_missing_nro_and_old_good_csv_are_detected(self):
        self.create()
        (self.root / self.nro).unlink()
        with self.assertRaisesRegex(bundle.BundleError, "missing"):
            bundle.inspect(self.root)

    def test_csv_is_strictly_parsed_at_create_and_verify(self):
        path = self.root / self.sessions[1]
        path.write_text("corrupt,header\n", encoding="utf-8")
        with self.assertRaises(audio.LogFormatError):
            self.create()
        write_session(path, 1300)
        self.create()
        item = self.root / bundle.MANIFEST_NAME
        raw = json.loads(item.read_text(encoding="utf-8"))
        path.write_text("corrupt,header\n", encoding="utf-8")
        size, digest = bundle.digest_file(path)
        raw["sessions"][1].update(size=size, sha256=digest)
        item.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(audio.LogFormatError):
            bundle.inspect(self.root)

    def test_rejects_duplicate_unsafe_or_extra_paths(self):
        with self.assertRaisesRegex(bundle.BundleError, "repeated"):
            self.create([self.sessions[0], self.sessions[0]])
        with self.assertRaisesRegex(bundle.BundleError, "unsafe"):
            bundle.record(self.root, "../escape.csv", "csv")
        with self.assertRaisesRegex(bundle.BundleError, "invalid relative"):
            bundle.record(self.root, "session-01\\evil.csv", "csv")
        with self.assertRaisesRegex(bundle.BundleError, "untracked"):
            self.create([self.sessions[0]])
        self.create()
        write_session(self.root / "unknown.csv")
        with self.assertRaisesRegex(bundle.BundleError, "untracked"):
            bundle.inspect(self.root)

    def test_rejects_symlink_to_another_file(self):
        alias = self.root / "session-01" / "alias.csv"
        alias.symlink_to(self.root / self.sessions[0])
        with self.assertRaisesRegex(bundle.BundleError, "symbolic links"):
            bundle.record(self.root, "session-01/alias.csv", "csv")

    def test_rejects_forged_hardware_success_and_duplicate_json_key(self):
        self.create()
        manifest = self.root / bundle.MANIFEST_NAME
        obj = json.loads(manifest.read_text(encoding="utf-8"))
        obj["hardware_status"] = "PASS"
        manifest.write_text(json.dumps(obj), encoding="utf-8")
        with self.assertRaisesRegex(bundle.BundleError, "claimed physical acceptance"):
            bundle.inspect(self.root)
        manifest.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(bundle.BundleError, "duplicate JSON key"):
            bundle.inspect(self.root)

    def test_incomplete_sessions_do_not_report_readiness(self):
        (self.root / self.sessions[1]).unlink()
        result = self.create([self.sessions[0]])
        self.assertEqual(result["telemetry_readiness"], "INCOMPLETE")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")

    def test_manifest_cannot_be_overwritten(self):
        self.create()
        with self.assertRaisesRegex(bundle.BundleError, "already exists"):
            self.create()

    def test_cli_json_and_error_status(self):
        command = [sys.executable, str(ROOT / "tools" /
                                      "verify_switch_audio_bundle.py")]
        create = subprocess.run(
            command + ["create", str(self.root), "--git-sha", "b" * 40,
                       "--nro", self.nro,
                       "--session", self.sessions[0],
                       "--session", self.sessions[1]],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(create.returncode, 0, create.stderr + create.stdout)
        self.assertEqual(json.loads(create.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        check = subprocess.run(command + ["verify", str(self.root)],
                               check=False, capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout)
        (self.root / self.sessions[1]).write_bytes(b"bad data")
        check = subprocess.run(command + ["verify", str(self.root)],
                               check=False, capture_output=True, text=True)
        self.assertEqual(check.returncode, 1, check.stdout)
        self.assertEqual(json.loads(check.stdout)["integrity"], "FAILED")


if __name__ == "__main__":
    unittest.main()
