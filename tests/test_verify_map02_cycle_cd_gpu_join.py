"""Adversarial asset-free cycle/CD/GPU witness join verification.

Most cases mock only the *preexisting expensive* final witness verifier and
check fail-closed local receipt handling. The integration test uses the
existing synthetic CD, native GPU and window-scoped fixture; its process
kernel/source witnesses retain the fixture's explicit mocks. No retail data.
"""
import hashlib
import io
import json
import os
from contextlib import redirect_stderr
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import tools.verify_map02_cycle_cd_gpu_join as cycle_module

from tools.publish_map02_cd_bound_witness import MANIFEST
from tools.verify_map02_window_scoped_join import CD_READ
from tools.verify_map02_cycle_cd_gpu_join import (
    CYCLE_RECEIPT, CYCLE_CLEAN_EXIT, CYCLE_SCHEMA, SCHEMA, _cycle_cd_pair,
    verify_cycle_cd_gpu_join,
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
            "schema": "vh.map02.original-cd-read.v2",
            "capture_session": self.nonce,
            "source": "original-CdRead-and-ContinueLoadingCdFile",
            "cdf": "CDF_M_MAP02_PRS",
            "lba": 0x1bcc,
            "sectors": 12,
            "bytes": 12 * 2048,
            "raw_user_crc32": self.crc,
            "returned_user_crc32": self.crc,
            "raw_user_sha256": "a" * 64,
            "returned_user_sha256": "a" * 64,
            "loader_completed": True,
        }, sort_keys=True) + "\n").encode()
        (self.scoped / CD_READ).write_bytes(self.cd_raw)
        (self.scoped / CD_READ).chmod(0o600)
        self.receipt = {
            "schema": CYCLE_SCHEMA,
            "original_cd_raw_user_crc32": self.crc,
            "original_cd_raw_user_sha256": "a" * 64,
            "observed_draw_primitive_count": 2,
            "display_source_rect": [0, 16, 320, 240],
            "present_backend_is_hires": False,
            "pc_present_call_returned": True,
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
        self.native_verifier = patch(
            "tools.verify_map02_cycle_cd_gpu_join.verify_native_windows",
            return_value={"capture_session_sha256": self.digest,
                          "native_draw_pairs": 2})
        self.native_mock = self.native_verifier.start()
        self.addCleanup(self.native_verifier.stop)

    def write_cycle(self):
        raw = (json.dumps(self.receipt, sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
        for name in (CYCLE_RECEIPT, CYCLE_CLEAN_EXIT):
            path = self.cycle / name
            path.write_bytes(raw)
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
        self.assertTrue(result["same_process_draw_primitive_count_matches_native_gpu_windows"])
        self.assertEqual(result["verified_draw_primitive_count"], 2)
        self.assertEqual(result["observed_pc_display_source_rect"],
                         [0, 16, 320, 240])
        self.assertFalse(result["observed_pc_hires_present_backend"])
        self.assertTrue(result["pc_present_call_returned_in_observed_process"])
        self.assertFalse(result["presented_framebuffer_verified"])
        self.assertNotIn(self.nonce, json.dumps(result))
        self.mock.assert_called_once()

    def test_missing_or_nonmatching_normal_exit_seal_rejected(self):
        seal = self.cycle / CYCLE_CLEAN_EXIT
        original = seal.read_bytes()
        seal.unlink()
        with self.assertRaisesRegex(ValueError, "normal-exit seal"):
            self.check()
        self.assertTrue((self.cycle / CYCLE_RECEIPT).is_file())
        seal.write_bytes(original + b" ")
        seal.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "normal-exit seal and receipt differ"):
            self.check()
        seal.write_bytes(original)
        seal.chmod(0o600)
        self.assertEqual(self.check()["schema"], SCHEMA)

    def test_seal_must_be_independent_owner_private_inode(self):
        seal = self.cycle / CYCLE_CLEAN_EXIT
        receipt = self.cycle / CYCLE_RECEIPT
        seal.unlink()
        os.link(receipt, seal)
        with self.assertRaisesRegex(ValueError, "owner-only 0600"):
            self.check()
        seal.unlink()
        seal.write_bytes(receipt.read_bytes())
        seal.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            self.check()
        seal.chmod(0o600)

    def test_prepublication_cycle_cd_pair_matches_both_original_crc_fields(self):
        proof = _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
        self.assertEqual(proof[0], (self.cycle / CYCLE_RECEIPT).read_bytes())
        self.assertEqual(proof[2], self.cd_raw)
        self.assertEqual(len(proof[1]), 2)
        self.assertEqual(len(proof[1][0]), 8)
        self.assertEqual(len(proof[1][1]), 8)
        self.assertEqual(len(proof[3]), 8)
        self.assertEqual(
            _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest), proof)
        self.mock.assert_not_called()  # no costly retail-image audit yet

    def test_prepublication_sha_rejects_mismatch_or_nonhex_even_with_unchanged_crc(self):
        path = self.scoped / CD_READ
        original = self.cd_raw
        for updates in (
                {"returned_user_sha256": "b" * 64},
                {"raw_user_sha256": "Z" * 64},
                {"raw_user_sha256": "ab12"}):
            with self.subTest(fields=updates):
                record = json.loads(original)
                record.update(updates)
                path.write_bytes((json.dumps(record, sort_keys=True) + "\n").encode())
                with self.assertRaisesRegex(ValueError, "checksum.*differ"):
                    _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
        path.write_bytes(original)
        self.assertEqual(_cycle_cd_pair(
            self.scoped, self.cycle, 7, self.digest)[2], original)

    def test_early_sha_pair_must_match_cycle_but_cannot_authenticate_disc(self):
        # Matching all *self-reported* hashes between both native witnesses
        # still does not prove that the owned retail BIN contains those bytes.
        record = json.loads(self.cd_raw)
        record["raw_user_sha256"] = "b" * 64
        record["returned_user_sha256"] = "b" * 64
        altered = (json.dumps(record, sort_keys=True) + "\n").encode()
        path = self.scoped / CD_READ
        path.write_bytes(altered)
        with self.assertRaisesRegex(ValueError, "checksum.*differ"):
            _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
        self.mock.assert_not_called()
        self.receipt["original_cd_raw_user_sha256"] = "b" * 64
        self.write_cycle()
        proof = _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
        self.assertEqual(proof[2], altered)
        self.mock.assert_not_called()  # user-owned original BIN still unchecked
        path.write_bytes(self.cd_raw)

    def test_prepublication_cycle_cd_pair_rejects_crc_and_session_mismatch(self):
        with self.assertRaisesRegex(ValueError, "cycle nonce differs"):
            _cycle_cd_pair(self.scoped, self.cycle, 7, "f" * 64)
        for key in ("raw_user_crc32", "returned_user_crc32", "capture_session"):
            with self.subTest(key=key):
                record = json.loads(self.cd_raw)
                record[key] = ("0" * 8 if key.endswith("crc32") else "cd" * 16)
                path = self.scoped / CD_READ
                path.write_bytes((json.dumps(record, sort_keys=True) + "\n").encode())
                with self.assertRaisesRegex(ValueError, "checksum and original CdRead receipt differ"):
                    _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
                path.write_bytes(self.cd_raw)
        self.mock.assert_not_called()

    def test_cd_pair_refuses_wrong_extent_source_and_incomplete_loader(self):
        path = self.scoped / CD_READ
        baseline = json.loads(self.cd_raw)
        changes = (
            {"lba": 0x1bcd}, {"lba": True}, {"lba": -1},
            {"sectors": 11}, {"sectors": True},
            {"bytes": 24575}, {"bytes": True},
            {"source": "synthetic-CdRead"},
            {"cdf": "CDF_M_MAP01_PRS"},
            {"loader_completed": False}, {"loader_completed": 1},
            {"schema": "vh.map02.original-cd-read.v0"},
        )
        for change in changes:
            with self.subTest(change=change):
                mutated = dict(baseline, **change)
                path.write_bytes((json.dumps(mutated, sort_keys=True) + "\n").encode())
                with self.assertRaises(ValueError):
                    _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
                path.write_bytes(self.cd_raw)
        self.mock.assert_not_called()

    def test_cd_pair_refuses_missing_extra_duplicate_or_multiline_fields(self):
        path = self.scoped / CD_READ
        baseline = json.loads(self.cd_raw)
        variants = [
            (json.dumps({k: v for k, v in baseline.items()
                         if k != "loader_completed"}) + "\n").encode(),
            (json.dumps(dict(baseline, extra_field=True)) + "\n").encode(),
            self.cd_raw + b"\n",
            self.cd_raw.replace(b"\n", b"\r\n"),
            self.cd_raw[:-2] + b",\"lba\":7116}\n",
        ]
        for raw in variants:
            with self.subTest(raw_sha256=sha(raw)):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
                path.write_bytes(self.cd_raw)
        self.mock.assert_not_called()

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
            {"original_cd_raw_user_sha256": "b" * 63},
            {"original_cd_raw_user_sha256": "G" * 64},
            {"original_cd_raw_user_sha256": 123},
            {"observed_draw_primitive_count": 0},
            {"observed_draw_primitive_count": 64},
            {"observed_draw_primitive_count": True},
            {"observed_draw_primitive_count": 1.5},
            {"display_source_rect": [0, 16, 0, 240]},
            {"display_source_rect": [1023, 16, 320, 240]},
            {"display_source_rect": [0, 500, 320, 240]},
            {"display_source_rect": [0, 16, 320]},
            {"display_source_rect": [True, 16, 320, 240]},
            {"present_backend_is_hires": 1},
            {"pc_present_call_returned": False},
            {"pc_present_call_returned": True if False else 1},
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
        with self.assertRaisesRegex(ValueError, "receipt and normal-exit seal"):
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

    def test_hires_presentation_is_explicitly_not_native_framebuffer_proof(self):
        self.receipt["present_backend_is_hires"] = True
        self.write_cycle()
        result = self.check()
        self.assertTrue(result["observed_pc_hires_present_backend"])
        self.assertFalse(result["presented_framebuffer_verified"])

    def test_mismatched_draw_primitive_count_rejected_before_full_audit(self):
        self.receipt["observed_draw_primitive_count"] = 3
        self.write_cycle()
        with self.assertRaisesRegex(ValueError, "primitive count and GPU windows differ"):
            self.check()
        self.mock.assert_not_called()

    def test_gpu_window_session_mismatch_rejected_before_full_audit(self):
        self.native_mock.return_value = {
            "capture_session_sha256": "f" * 64, "native_draw_pairs": 2}
        with self.assertRaisesRegex(ValueError, "primitive count and GPU windows differ"):
            self.check()
        self.mock.assert_not_called()

    def test_mismatched_crc_is_rejected_before_original_disc_verification(self):
        self.receipt["original_cd_raw_user_crc32"] = "0" * 8
        self.write_cycle()
        with self.assertRaisesRegex(ValueError, "checksum.*differ"):
            self.check()
        self.mock.assert_not_called()

    def test_mismatched_cycle_sha_is_rejected_before_owned_disc_verification(self):
        # CRC still matches; a wrong cycle digest cannot pass.
        self.receipt["original_cd_raw_user_sha256"] = "b" * 64
        self.write_cycle()
        with self.assertRaisesRegex(ValueError, "checksum.*differ"):
            self.check()
        self.mock.assert_not_called()

    def test_original_cd_crc_mutation_during_expensive_audit_rejected(self):
        def mutate(*args, **kwargs):
            # Keep valid, single-line JSONL with EXACTLY the same CD fields
            # and CRC. Only the raw bytes differ; the final inode/byte audit
            # must still refuse to accept a modified mid-audit receipt.
            alternate = (json.dumps(json.loads(self.cd_raw), sort_keys=True,
                                    separators=(",", ":")) + "\n").encode()
            self.assertNotEqual(alternate, self.cd_raw)
            (self.scoped / CD_READ).write_bytes(alternate)
            return {"private_map02_cd_final_sha256": sha(self.manifest_raw)}
        self.mock.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self.check()

    def test_changed_cycle_during_expensive_original_verification_rejected(self):
        def mutate(*args, **kwargs):
            changed = (json.dumps(self.receipt, sort_keys=False) + "\n").encode()
            for filename in (CYCLE_RECEIPT, CYCLE_CLEAN_EXIT):
                (self.cycle / filename).write_bytes(changed)
            return {"private_map02_cd_final_sha256": sha(self.manifest_raw)}
        self.mock.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self.check()

    def test_identical_byte_inode_swap_during_full_recheck_is_rejected(self):
        for folder, filename in (
                (self.source, MANIFEST), (self.scoped, CD_READ),
                (self.cycle, CYCLE_RECEIPT),
                (self.cycle, CYCLE_CLEAN_EXIT)):
            with self.subTest(filename=filename):
                target = folder / filename
                original = target.read_bytes()
                def identical_inode_swap(*args, **kwargs):
                    backup = folder.parent / ("previous-" + folder.name + "-" + filename)
                    target.replace(backup)
                    target.write_bytes(original)
                    target.chmod(0o600)
                    self.assertNotEqual(target.stat().st_ino, backup.stat().st_ino)
                    return {"private_map02_cd_final_sha256": sha(self.manifest_raw)}
                with patch.object(cycle_module,
                                  "verify_published_original_cd_witness",
                                  side_effect=identical_inode_swap):
                    with self.assertRaisesRegex(ValueError, "changed during verification"):
                        self.check()
                target.unlink()
                (folder.parent / ("previous-" + folder.name + "-" + filename)).replace(target)
        self.mock.assert_not_called()

    def test_double_read_rejects_byte_change_with_identical_file_metadata(self):
        original_pread = os.pread
        calls = []
        def changed_second_read(fd, size, offset):
            raw = original_pread(fd, size, offset)
            calls.append(1)
            if len(calls) == 2:
                return bytes([raw[0] ^ 1]) + raw[1:]
            return raw
        with patch.object(cycle_module.os, "pread", side_effect=changed_second_read):
            with self.assertRaisesRegex(ValueError, "bytes changed between reads"):
                self.check()
        self.assertEqual(len(calls), 2)
        self.mock.assert_not_called()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_cycle_receipt_fifo_rejected_by_nonblocking_inode_snapshot(self):
        target = self.cycle / CYCLE_RECEIPT
        target.unlink()
        os.mkfifo(target, mode=0o600)
        real_open = os.open
        with patch.object(cycle_module.os, "open", wraps=real_open) as opened:
            with self.assertRaisesRegex(ValueError, "regular file"):
                self.check()
        calls = [c for c in opened.call_args_list
                 if c.args and os.fspath(c.args[0]) == os.fspath(target)]
        self.assertTrue(calls, "cycle FIFO must be opened for inode validation")
        self.assertTrue(calls[0].args[1] & os.O_NONBLOCK)
        self.mock.assert_not_called()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_original_cd_receipt_fifo_rejected_before_expensive_recheck(self):
        target = self.scoped / CD_READ
        target.unlink()
        os.mkfifo(target, mode=0o600)
        real_open = os.open
        with patch.object(cycle_module.os, "open", wraps=real_open) as opened:
            with self.assertRaisesRegex(ValueError, "regular file"):
                _cycle_cd_pair(self.scoped, self.cycle, 7, self.digest)
        calls = [c for c in opened.call_args_list
                 if c.args and os.fspath(c.args[0]) == os.fspath(target)]
        self.assertTrue(calls, "CdRead FIFO must be opened for inode validation")
        self.assertTrue(calls[0].args[1] & os.O_NONBLOCK)
        self.mock.assert_not_called()

    def test_file_hardlink_and_wrong_owner_permissions_are_rejected(self):
        target = self.cycle / CYCLE_RECEIPT
        twin = self.cycle.parent / "cycle-linked-copy"
        os.link(target, twin)
        try:
            with self.assertRaisesRegex(ValueError, "owner-only 0600"):
                self.check()
        finally:
            twin.unlink()
        target.chmod(0o640)
        with self.assertRaisesRegex(ValueError, "owner-only 0600"):
            self.check()
        self.mock.assert_not_called()

    def test_cycle_verifier_cli_redacts_native_errors(self):
        private_path = "/private/map02/owned-cd-and-executable"
        argv = ["cycle-verify", str(self.source), str(self.native),
                str(self.scoped), str(self.handoff), str(self.cycle),
                private_path, "--upstream-checkout", str(self.source),
                "--pc-binary", private_path, "--frame", "7"]
        errors = (
            OSError(2, "original image missing", private_path),
            subprocess.TimeoutExpired([private_path, "--inspect"], 15,
                                      output=private_path.encode()),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = io.StringIO()
                with (patch("sys.argv", argv),
                      patch.object(cycle_module, "verify_cycle_cd_gpu_join",
                                   side_effect=error),
                      redirect_stderr(output)):
                    with self.assertRaises(SystemExit) as exit_result:
                        cycle_module.main()
                self.assertEqual(exit_result.exception.code, 2)
                self.assertIn("private MAP02 cycle verification unavailable",
                              output.getvalue())
                self.assertNotIn(private_path, output.getvalue())

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
        # Full integration uses the REAL native window verifier, not the
        # narrow unit-test mock. The original-game image remains synthetic.
        from tools.verify_map02_native_gpu_windows import verify_native_windows
        recorded = verify_native_windows(fixture.native, target_frame=7)
        event = {
            "schema": CYCLE_SCHEMA,
            "capture_session": fixture.cd_receipt["capture_session"],
            "original_cd_raw_user_crc32": fixture.cd_receipt["raw_user_crc32"],
            "original_cd_raw_user_sha256": fixture.cd_receipt["raw_user_sha256"],
            "observed_draw_primitive_count": recorded["native_draw_pairs"],
            "display_source_rect": [0, 16, 320, 240],
            "present_backend_is_hires": False,
            "pc_present_call_returned": True,
            "gpu_draw_frame": 7,
            "ordered_source_hooks_observed": True,
            "cd_payload_verified_by_this_receipt": False,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False,
        }
        raw = (json.dumps(event, sort_keys=True) + "\n").encode()
        for name in (CYCLE_RECEIPT, CYCLE_CLEAN_EXIT):
            path = cycle / name
            path.write_bytes(raw)
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
