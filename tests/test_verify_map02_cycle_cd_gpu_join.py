"""Adversarial asset-free cycle/CD/GPU witness join verification.

Most cases mock only the *preexisting expensive* final witness verifier and
check fail-closed local receipt handling. The integration test uses the
existing synthetic CD, native GPU and window-scoped fixture; its process
kernel/source witnesses retain the fixture's explicit mocks. No retail data.
"""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tools.publish_map02_cd_bound_witness import MANIFEST
from tools.verify_map02_window_scoped_join import CD_READ
from tools.verify_map02_cycle_cd_gpu_join import (
    CYCLE_RECEIPT, CYCLE_SCHEMA, SCHEMA, verify_cycle_cd_gpu_join,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CycleCdGpuJoinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-cycle-join-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source, self.native, self.scoped, self.handoff, self.cycle = [
            root / label for label in ("source", "native", "scoped",
                                       "handoff", "cycle")
        ]
        for path in (self.source, self.native, self.scoped,
                     self.handoff, self.cycle):
            path.mkdir(mode=0o700)
        self.nonce = "ab" * 16
        self.digest = sha(self.nonce.encode("ascii"))
        self.manifest_raw = (json.dumps({
            "gpu_draw_frame": 7, "capture_session_sha256": self.digest,
        }, sort_keys=True) + "\n").encode()
        (self.source / MANIFEST).write_bytes(self.manifest_raw)
        (self.source / MANIFEST).chmod(0o600)
        self.crc = "d31a04b7"  # synthetic-only CD checksum
        self.cd_raw = (json.dumps({
            "schema": "vh.map02.original-cd-read.v1",
            "capture_session": self.nonce,
            "raw_user_crc32": self.crc,
            "returned_user_crc32": self.crc,
        }, sort_keys=True) + "\n").encode()
        (self.scoped / CD_READ).write_bytes(self.cd_raw)
        (self.scoped / CD_READ).chmod(0o600)
        self.receipt = {
            "schema": CYCLE_SCHEMA,
            "original_cd_raw_user_crc32": self.crc,
            "capture_session": self.nonce,
            "gpu_draw_frame": 7,
            "ordered_source_hooks_observed": True,
            "cd_payload_verified_by_this_receipt": False,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False,
        }
        self.write_cycle()
        self.verifier = patch(
            "tools.verify_map02_cycle_cd_gpu_join.verify_published_original_cd_witness",
            return_value={"private_map02_cd_final_sha256": sha(self.manifest_raw)})
        self.mock = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def write_cycle(self):
        path = self.cycle / CYCLE_RECEIPT
        path.write_bytes((json.dumps(self.receipt, sort_keys=True,
                                     separators=(",", ":")) + "\n").encode())
        path.chmod(0o600)

    def check(self):
        return verify_cycle_cd_gpu_join(
            self.source, self.native, self.scoped, self.handoff, self.cycle,
            Path("/nonexistent/private-disc"), Path("/nonexistent/pinned-upstream"),
            Path("/nonexistent/instrumented-elf"), frame=7)

    def test_accepts_only_same_frame_nonce_and_full_prior_recheck(self):
        result = self.check()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["capture_session_sha256"], self.digest)
        self.assertEqual(result["single_process_cycle_receipt_sha256"],
                         sha((self.cycle / CYCLE_RECEIPT).read_bytes()))
        self.assertTrue(result[
            "same_process_event_order_and_prior_cd_gpu_witness_join_verified"])
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertFalse(result["full_original_gameplay_authenticated"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])
        self.assertNotIn(self.nonce, json.dumps(result))
        self.mock.assert_called_once()

    def test_wrong_frame_or_session_fails_before_expensive_recheck(self):
        self.receipt["gpu_draw_frame"] = 8
        self.write_cycle()
        with self.assertRaisesRegex(ValueError, "frame mismatch"):
            self.check()
        self.receipt["gpu_draw_frame"] = 7
        self.receipt["capture_session"] = "cd" * 16
        self.write_cycle()
        with self.assertRaisesRegex(ValueError, "not one session"):
            self.check()
        self.mock.assert_not_called()

    def test_missing_invalid_nonce_and_overstated_boolean_are_rejected(self):
        for change in (
            {"capture_session": "abc"},
            {"capture_session": "AB" * 16},
            {"capture_session": 123},
            {"original_cd_raw_user_crc32": "xyz"},
            {"original_cd_raw_user_crc32": "D31A04B7"},
            {"original_cd_raw_user_crc32": True},
            {"ordered_source_hooks_observed": False},
            {"ordered_source_hooks_observed": 1},
            {"cd_payload_verified_by_this_receipt": True},
            {"original_map02_rendering_proven": True},
            {"physical_ps1_equivalence_proven": True},
            {"gpu_draw_frame": True},
            {"schema": "unsupported"},
        ):
            with self.subTest(change=change):
                old = dict(self.receipt)
                self.receipt.update(change)
                self.write_cycle()
                with self.assertRaises(ValueError):
                    self.check()
                self.receipt = old
        self.mock.assert_not_called()

    def test_noncanonical_duplicate_or_multiple_receipts_are_rejected(self):
        file = self.cycle / CYCLE_RECEIPT
        original = file.read_bytes()
        for bad in (
            original[:-1],
            original + b"\n",
            original + original,
            original.replace(b'"schema":', b'"schema":"duplicate","schema":', 1),
            original.replace(b"\n", b"\r\n"),
        ):
            with self.subTest(bad=bad[-40:]):
                file.write_bytes(bad)
                with self.assertRaises(ValueError):
                    self.check()
        file.write_bytes(original)
        (self.cycle / "unlisted.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.check()
        self.mock.assert_not_called()

    def test_receipt_permissions_symlinks_and_aliased_roots_rejected(self):
        path = self.cycle / CYCLE_RECEIPT
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            self.check()
        path.chmod(0o600)
        moved = self.cycle / "real"
        path.rename(moved)
        path.symlink_to(moved)
        with self.assertRaises(ValueError):
            self.check()
        path.unlink()
        moved.rename(path)
        with self.assertRaisesRegex(ValueError, "must differ"):
            verify_cycle_cd_gpu_join(
                self.source, self.native, self.scoped, self.handoff,
                self.source, None, None, None, frame=7)

    def test_prior_verifier_must_match_exact_original_bytes(self):
        self.mock.return_value = {
            "private_map02_cd_final_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "SHA differs"):
            self.check()

    def test_mismatched_crc_is_rejected_before_original_disc_verification(self):
        self.receipt["original_cd_raw_user_crc32"] = "0" * 8
        self.write_cycle()
        with self.assertRaisesRegex(ValueError, "CRC32.*differ"):
            self.check()
        self.mock.assert_not_called()

    def test_original_cd_crc_mutation_during_expensive_audit_rejected(self):
        def mutate(*args, **kwargs):
            (self.scoped / CD_READ).write_bytes(self.cd_raw + b" ")
            return {"private_map02_cd_final_sha256": sha(self.manifest_raw)}
        self.mock.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self.check()

    def test_changed_cycle_during_expensive_original_verification_rejected(self):
        def mutate(*args, **kwargs):
            path = self.cycle / CYCLE_RECEIPT
            path.write_bytes((json.dumps(self.receipt, sort_keys=False) + "\n").encode())
            return {"private_map02_cd_final_sha256": sha(self.manifest_raw)}
        self.mock.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self.check()

    def test_changed_original_manifest_during_recheck_rejected(self):
        def mutate(*args, **kwargs):
            (self.source / MANIFEST).write_bytes(self.manifest_raw + b" ")
            return {"private_map02_cd_final_sha256": sha(self.manifest_raw)}
        self.mock.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self.check()


class CycleCdGpuSyntheticIntegrationTests(unittest.TestCase):
    def test_existing_cd_gpu_join_and_new_order_receipt(self):
        from tests.test_publish_map02_cd_bound_witness import (
            OriginalCdBoundFinalWitnessTests,
        )
        fixture = OriginalCdBoundFinalWitnessTests(
            methodName="test_publishes_private_sealed_source_gpu_cd_and_kernel_evidence")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.publish()
        cycle = fixture.source.parent / "cycle-gate"
        cycle.mkdir(mode=0o700)
        event = {
            "schema": CYCLE_SCHEMA,
            "capture_session": fixture.cd_receipt["capture_session"],
            "original_cd_raw_user_crc32": fixture.cd_receipt["raw_user_crc32"],
            "gpu_draw_frame": 7,
            "ordered_source_hooks_observed": True,
            "cd_payload_verified_by_this_receipt": False,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False,
        }
        path = cycle / CYCLE_RECEIPT
        path.write_bytes((json.dumps(event, sort_keys=True) + "\n").encode())
        path.chmod(0o600)
        result = verify_cycle_cd_gpu_join(
            fixture.source, fixture.native, fixture.scoped,
            fixture.handoff, cycle, fixture.image, fixture.upstream,
            fixture.binary, frame=7)
        self.assertEqual(result["source_cd_gpu_process_witness_sha256"],
                         sha((fixture.source / MANIFEST).read_bytes()))
        self.assertFalse(result["original_map02_rendering_proven"])


if __name__ == "__main__":
    unittest.main()
