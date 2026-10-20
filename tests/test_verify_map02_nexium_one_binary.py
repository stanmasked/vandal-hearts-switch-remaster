"""ROM-free tests: pinned NeXium host identity cannot be forged per guest."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_map02_nexium_one_binary import verify_host_links, verify_evidence_attempts

SOURCE = "a" * 40
RUN = 123456789
BINARY = "b" * 64


def write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


class OneNeXiumBinaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        d = self.root / "map02-nexium-once-binary"
        d.mkdir()
        archive = b"generated-fixture-not-a-real-NeXium-build"
        (d / "nexium-linux-x86_64.tar.gz").write_bytes(archive)
        self.manifest = {
            "schema": "vh-map02-nexium-one-host-binary/v1",
            "source_sha": SOURCE, "event_sha": "e" * 40,
            "run_id": RUN, "attempt": 1,
            "upstream_asset_id": 400, "upstream_release_id": 300,
            "host_archive_sha256": hashlib.sha256(archive).hexdigest(),
            "host_executable_sha256": BINARY,
            "upstream_source_commit_verified": False,
            "cross_run_release_immutability_proven": False,
        }
        write_json(d / "manifest.json", self.manifest)
        for ms in (21, 22):
            for repeat in (1, 2, 3):
                t = self.trial(ms, repeat)
                t.mkdir()
                write_json(t / "nexium-host-build.json", self.manifest)
                write_json(t / "pulse-client-trial.json", {
                    "source_sha": SOURCE, "run_id": RUN, "attempt": 1,
                    "variant": str(ms), "independent_repeat": repeat,
                    "same_run_host_binary_sha256_verified": True,
                    "host_binary_sha256": BINARY,
                })

    def make_guest_attempt_manifests(self):
        data = {"schema": "vh-map02-presubmit-guest-nro/v1",
                "source_sha": SOURCE, "run_id": RUN, "attempt": 1}
        nro = self.root / "map02-audout-presubmit-research-nro"
        nro.mkdir()
        write_json(nro / "manifest.json", data)
        for ms in (21, 22):
            for repeat in (1, 2, 3):
                write_json(self.trial(ms, repeat) / "manifest.json", data)

    def trial(self, ms=21, repeat=1):
        return self.root / f"map02-presubmit-nexium-guest-proof-{ms}-r{repeat}"

    def change_json(self, path, key, value):
        obj = json.loads(path.read_text())
        obj[key] = value
        write_json(path, obj)

    def test_six_unique_guest_host_identities_verified_without_dac_claim(self):
        x = verify_host_links(self.root, SOURCE, RUN)
        self.assertEqual(len(x["guest_trials"]), 6)
        self.assertEqual(x["host_executable_sha256"], BINARY)
        self.assertTrue(x["same_host_executable_sha256_all_six_verified"])
        self.assertFalse(x["cpal_alsa_root_cause_proven"])
        self.assertFalse(x["physical_nintendo_switch_speaker_proven"])
        self.assertFalse(x["cross_run_release_immutability_proven"])

    def test_host_archive_byte_change_rejected(self):
        p = self.root / "map02-nexium-once-binary" / "nexium-linux-x86_64.tar.gz"
        p.write_bytes(b"tamper")
        with self.assertRaisesRegex(ValueError, "archive SHA"):
            verify_host_links(self.root, SOURCE, RUN)

    def test_single_guest_manifests_rewritten_rejected(self):
        self.change_json(self.trial(22, 2) / "nexium-host-build.json",
                         "host_executable_sha256", "c" * 64)
        with self.assertRaisesRegex(ValueError, "Host manifest mismatch"):
            verify_host_links(self.root, SOURCE, RUN)

    def test_guest_lies_about_host_sha_rejected(self):
        self.change_json(self.trial(21, 1) / "pulse-client-trial.json",
                         "host_binary_sha256", "c" * 64)
        with self.assertRaisesRegex(ValueError, "Host executable identity"):
            verify_host_links(self.root, SOURCE, RUN)

    def test_missing_failed_guest_cannot_pass(self):
        import shutil
        shutil.rmtree(self.trial(21, 3))
        with self.assertRaisesRegex(ValueError, "Missing independent guest"):
            verify_host_links(self.root, SOURCE, RUN)

    def test_guests_from_other_run_cannot_pass(self):
        self.change_json(self.trial(22, 1) / "pulse-client-trial.json",
                         "run_id", RUN+1)
        with self.assertRaisesRegex(ValueError, "trial provenance"):
            verify_host_links(self.root, SOURCE, RUN)

    def test_false_upstream_commit_claim_rejected(self):
        path = self.root / "map02-nexium-once-binary" / "manifest.json"
        self.change_json(path, "upstream_source_commit_verified", True)
        with self.assertRaisesRegex(ValueError, "upstream"):
            verify_host_links(self.root, SOURCE, RUN)

    def test_all_seven_same_attempt_manifests_accepted(self):
        self.make_guest_attempt_manifests()
        self.assertEqual(verify_evidence_attempts(self.root, SOURCE, RUN), 1)

    def test_reused_old_attempt_guest_archive_rejected(self):
        self.make_guest_attempt_manifests()
        self.change_json(self.trial(21, 3) / "manifest.json", "attempt", 2)
        with self.assertRaisesRegex(ValueError, "Cross-attempt"):
            verify_evidence_attempts(self.root, SOURCE, RUN)

    def test_reused_old_attempt_nro_archive_rejected(self):
        self.make_guest_attempt_manifests()
        self.change_json(self.root /
                         "map02-audout-presubmit-research-nro" /
                         "manifest.json", "attempt", 2)
        with self.assertRaisesRegex(ValueError, "Cross-attempt"):
            verify_evidence_attempts(self.root, SOURCE, RUN)

    def test_missing_source_identity_rejected(self):
        self.change_json(self.trial(21, 2) / "pulse-client-trial.json",
                         "source_sha", "0" * 40)
        with self.assertRaisesRegex(ValueError, "trial provenance"):
            verify_host_links(self.root, SOURCE, RUN)


if __name__ == "__main__":
    unittest.main()
