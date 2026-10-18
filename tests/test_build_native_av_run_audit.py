"""Synthetic tests for a reproducible seven-scenario NeXium digest index."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from build_native_av_run_audit import build_report, write_report
from test_verify_native_av_nro_manifest import NRO_NAMES, tiny_nro
from verify_native_av_evidence_inventory import (
    FILES, PNG_PREFIX, PREFIX, SCENARIOS, SUFFIX,
    SD_MODE_BY_SCENARIO, expected_manifest,
)
from verify_native_av_guest_witness import NRO_BY_SCENARIO
from verify_native_av_nro_manifest import COMMIT_FILE, MANIFEST

REVISION = "0123456789abcdef" * 2 + "01234567"
RUN_ID, ATTEMPT = 39129054757, 1


def header():
    body = (1280).to_bytes(4, "big") + (720).to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    return PNG_PREFIX + body + zlib.crc32(b"IHDR" + body).to_bytes(4, "big")


class SevenCaseDigestIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.evidence, self.nros = root / "evidence", root / "nros"
        self.evidence.mkdir()
        self.nros.mkdir()
        self.visited = []
        for i, name in enumerate(NRO_NAMES):
            (self.nros / name).write_bytes(tiny_nro(i))
        (self.nros / MANIFEST).write_text(
            "".join(hashlib.sha256((self.nros / n).read_bytes()).hexdigest() +
                    "  " + n + "\n" for n in NRO_NAMES), encoding="ascii")
        (self.nros / COMMIT_FILE).write_text(REVISION + "\n", encoding="ascii")
        for scenario in SCENARIOS:
            folder = self.evidence / (PREFIX + scenario + SUFFIX)
            folder.mkdir()
            for name in FILES:
                file = folder / name
                if name == "sd-fixture-manifest.json":
                    file.write_text(json.dumps(expected_manifest(
                        SD_MODE_BY_SCENARIO[scenario])), encoding="utf-8")
                elif name in ("av-before.png", "av-after.png"):
                    file.write_bytes(header() + b"synthetic-header-only")
                elif name == "nexium.log":
                    file.write_bytes(b"")
                else:
                    file.write_bytes(("synthetic-" + scenario).encode("ascii"))

    def fake_verified(self, witness, before, after, nro, revision, scenario,
                      run_id, attempt, *, published_nro_dir):
        self.assertEqual(nro.name, NRO_BY_SCENARIO[scenario])
        self.assertEqual((revision, run_id, attempt), (REVISION, RUN_ID, ATTEMPT))
        self.assertEqual(published_nro_dir, self.nros)
        self.assertTrue(witness.is_file() and before.is_file() and after.is_file())
        self.visited.append(scenario)
        return {"heartbeat_changed_pixels": 32}

    def report(self):
        return build_report(self.evidence, self.nros, REVISION, RUN_ID, ATTEMPT,
                            verify_case=self.fake_verified)

    def test_seven_ordered_cases_and_no_false_proof(self):
        report = self.report()
        self.assertEqual(report["scenario_count"], 7)
        self.assertEqual([c["scenario"] for c in report["cases"]], list(SCENARIOS))
        self.assertEqual(self.visited, list(SCENARIOS))
        self.assertFalse(report["physical_hardware_verified"])
        self.assertFalse(report["audible_audio_verified"])
        self.assertFalse(report["original_game_assets_included"])

    def test_every_file_and_nro_digest_matches_its_bytes(self):
        report = self.report()
        for case in report["cases"]:
            folder = self.evidence / (PREFIX + case["scenario"] + SUFFIX)
            self.assertEqual(set(case["evidence_sha256"]), FILES)
            for name, digest in case["evidence_sha256"].items():
                self.assertEqual(digest, hashlib.sha256((folder / name).read_bytes()).hexdigest())
            self.assertEqual(case["nro_sha256"], hashlib.sha256(
                (self.nros / case["nro_filename"]).read_bytes()).hexdigest())

    def test_identical_base_nro_can_have_distinct_guest_evidence(self):
        cases = {c["scenario"]: c for c in self.report()["cases"]}
        self.assertEqual({cases[c]["nro_filename"] for c in ("empty", "full", "partial")},
                         {NRO_NAMES[0]})
        self.assertNotEqual(cases["empty"]["evidence_sha256"]["native-av-guest-witness.json"],
                            cases["full"]["evidence_sha256"]["native-av-guest-witness.json"])

    def test_output_is_repeatable_and_never_overwritten(self):
        report = self.report()
        a, b = (Path(self.temp.name) / f"audit-{i}.json" for i in range(2))
        write_report(a, report)
        write_report(b, report)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(json.loads(a.read_text()), report)
        with self.assertRaises(FileExistsError):
            write_report(a, report)

    def test_missing_case_fails_before_individual_verification(self):
        import shutil
        shutil.rmtree(self.evidence / (PREFIX + "zl" + SUFFIX))
        with self.assertRaisesRegex(ValueError, "case directory inventory mismatch"):
            self.report()
        self.assertEqual(self.visited, [])

    def test_independently_supplied_commit_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "independently expected commit"):
            build_report(self.evidence, self.nros, "f" * 40, RUN_ID, ATTEMPT,
                         verify_case=self.fake_verified)
        self.assertEqual(self.visited, [])

    def test_invalid_identity_and_noninteger_heartbeat_rejected(self):
        for run, attempt in ((True, ATTEMPT), (0, ATTEMPT), (RUN_ID, False)):
            with self.subTest(run=run, attempt=attempt):
                with self.assertRaisesRegex(ValueError, "positive integers"):
                    build_report(self.evidence, self.nros, REVISION, run, attempt,
                                 verify_case=self.fake_verified)
        with self.assertRaisesRegex(ValueError, "invalid verified framebuffer heartbeat"):
            build_report(self.evidence, self.nros, REVISION, RUN_ID, ATTEMPT,
                         verify_case=lambda *a, **kw: {"heartbeat_changed_pixels": True})


if __name__ == "__main__":
    unittest.main()
