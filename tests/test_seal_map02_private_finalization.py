"""Private final MAP02 seal/verification (synthetic CD and GPU only)."""
import hashlib
import json
import os
from pathlib import Path
import stat
from unittest.mock import patch
import unittest

from tests.test_finalize_map02_private_capture import (
    PrivatePostcaptureCompletionTests,
)
from tools.seal_map02_private_finalization import (
    NAME, SCHEMA, seal_final_capture, verify_final_seal,
)


class PrivateFinalSealTests(unittest.TestCase):
    def setUp(self):
        fixture = PrivatePostcaptureCompletionTests(
            methodName="test_existing_artifacts_read_only_and_no_game_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.seal_dir = Path(fixture.fixture.tmp.name) / "final-seal"
        self.seal_dir.mkdir(mode=0o700)

    def call(self, *, action="seal", seal=None, **kwargs):
        f = self.fixture
        frame = kwargs.pop("frame", 7)
        fn = seal_final_capture if action == "seal" else verify_final_seal
        return fn(
            f.source, f.fixture.base.fixture.root, f.fixture.scoped,
            f.fixture.handoff, f.fixture.base.cycle, f.preview, f.rgb,
            Path("/no-owned-retail-image"), Path("/no-local-upstream"),
            Path("/no-original-elf"), seal or self.seal_dir,
            frame=frame, **kwargs)

    def test_publish_exclusive_owner_private_seal_then_independently_verify(self):
        published = self.call()
        receipt = self.seal_dir / NAME
        self.assertEqual(published["schema"], SCHEMA)
        self.assertTrue(published["two_independent_readonly_final_audits"])
        self.assertTrue(
            published["postpublication_independent_verification_completed"])
        self.assertEqual({p.name for p in self.seal_dir.iterdir()}, {NAME})
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
        self.assertEqual(
            published["private_final_seal_sha256"],
            hashlib.sha256(receipt.read_bytes()).hexdigest())
        payload = json.loads(receipt.read_bytes())
        self.assertTrue(payload["independent_postcapture_recheck_completed"])
        self.assertEqual(payload["verified_draw_primitives"], 2)
        self.assertFalse(payload["original_map02_rendering_proven"])
        self.assertFalse(payload["game_bytes_uploaded"])
        verified = self.call(action="verify")
        self.assertEqual(
            verified["private_final_seal_sha256"],
            published["private_final_seal_sha256"])
        self.assertTrue(verified["sealed_evidence_independently_reverified"])
        output = json.dumps(published) + receipt.read_text()
        self.assertNotIn(self.fixture.fixture.token, output)
        self.assertNotIn(str(self.fixture.source), output)

    def test_never_overwrite_even_identical_report_or_symlink(self):
        self.call()
        original = (self.seal_dir / NAME).read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.call()
        self.assertEqual((self.seal_dir / NAME).read_bytes(), original)
        with self.assertRaises(ValueError):
            self.call(action="verify", frame=8)

    def test_reject_modified_seal_or_false_claims(self):
        self.call()
        receipt = self.seal_dir / NAME
        original = receipt.read_bytes()
        record = json.loads(original)
        record["original_map02_rendering_proven"] = True
        receipt.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaisesRegex(ValueError, "authenticity flags"):
            self.call(action="verify")
        receipt.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "not canonical"):
            self.call(action="verify")

    def test_reject_noncanonical_jsonl_even_when_fields_match(self):
        self.call()
        receipt = self.seal_dir / NAME
        content = json.loads(receipt.read_bytes())
        # Valid JSON with all original values must still fail canonicality.
        receipt.write_text(json.dumps(content, sort_keys=True, indent=2) + "\n")
        with self.assertRaisesRegex(ValueError, "not canonical JSONL"):
            self.call(action="verify")

    def test_reject_capture_change_after_seal(self):
        self.call()
        self.fixture.fixture.fixture.rgbfile.write_bytes(b"\xff\xfe\xfd")
        with self.assertRaises(ValueError):
            self.call(action="verify")

    def test_failed_write_readback_removes_only_its_new_inode(self):
        from tools.seal_map02_private_finalization import _publish
        # Deliberate post-write readback corruption: failure must not leave
        # an apparent final seal behind. The directory must remain private.
        with patch(
                "tools.seal_map02_private_finalization.os.pread",
                return_value=b"corrupted"):
            with self.assertRaisesRegex(ValueError, "readback/identity"):
                _publish(self.seal_dir, b"synthetic-private-test-receipt\n")
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_zero_length_write_rolls_back_unchanged_created_inode(self):
        from tools.seal_map02_private_finalization import _publish
        with patch("tools.seal_map02_private_finalization.os.write",
                   return_value=0):
            with self.assertRaisesRegex(ValueError, "incomplete private seal write"):
                _publish(self.seal_dir, b"synthetic-partial-test\n")
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_short_write_then_failure_rolls_back_only_own_inode(self):
        import os
        from tools.seal_map02_private_finalization import _publish
        actual_write = os.write
        calls = [0]

        def short_then_zero(fd, data):
            calls[0] += 1
            if calls[0] == 1:
                return actual_write(fd, data[:4])
            return 0

        with patch("tools.seal_map02_private_finalization.os.write",
                   side_effect=short_then_zero):
            with self.assertRaisesRegex(ValueError, "incomplete private seal write"):
                _publish(self.seal_dir, b"synthetic-partial-test\n")
        self.assertEqual(calls[0], 2)
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_failed_file_fsync_rolls_back_unchanged_created_inode(self):
        from tools.seal_map02_private_finalization import _publish
        with patch("tools.seal_map02_private_finalization.os.fsync",
                   side_effect=OSError("synthetic fsync failure")):
            with self.assertRaisesRegex(OSError, "synthetic fsync failure"):
                _publish(self.seal_dir, b"synthetic-partial-test\n")
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_failed_file_fsync_preserves_modified_same_inode(self):
        from tools.seal_map02_private_finalization import _publish
        receipt = self.seal_dir / NAME

        def rewrite_then_fail(fd):
            receipt.write_bytes(b"external-mutated-before-fsync")
            raise OSError("synthetic fsync failure")

        with patch("tools.seal_map02_private_finalization.os.fsync",
                   side_effect=rewrite_then_fail):
            with self.assertRaisesRegex(OSError, "synthetic fsync failure"):
                _publish(self.seal_dir, b"synthetic-partial-test\n")
        self.assertEqual(receipt.read_bytes(), b"external-mutated-before-fsync")

    def test_directory_fsync_failure_rolls_back_durably(self):
        import os
        from tools.seal_map02_private_finalization import _publish
        real_fsync = os.fsync
        directory_fsync_calls = [0]

        def fail_first_directory_sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_fsync_calls[0] += 1
                if directory_fsync_calls[0] == 1:
                    raise OSError("synthetic directory fsync failure")
            return real_fsync(fd)

        with patch("tools.seal_map02_private_finalization.os.fsync",
                   side_effect=fail_first_directory_sync):
            with self.assertRaisesRegex(OSError, "directory fsync failure"):
                _publish(self.seal_dir, b"synthetic-private-seal\n")
        # The first fsync fails to publish; the second must durably unlink.
        self.assertEqual(directory_fsync_calls[0], 2)
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_partial_write_foreign_inode_replacement_is_preserved(self):
        import os
        from tools.seal_map02_private_finalization import _publish
        original_write = os.write
        receipt = self.seal_dir / NAME
        attempts = [0]

        def swap_after_partial_write(fd, data):
            attempts[0] += 1
            if attempts[0] == 1:
                n = original_write(fd, data[:4])
                receipt.unlink()
                receipt.write_bytes(b"foreign-inode-after-partial-write")
                receipt.chmod(0o600)
                return n
            return 0

        with patch("tools.seal_map02_private_finalization.os.write",
                   side_effect=swap_after_partial_write):
            with self.assertRaisesRegex(ValueError, "incomplete private seal write"):
                _publish(self.seal_dir, b"synthetic-private-seal\n")
        self.assertEqual(attempts[0], 2)
        self.assertEqual(receipt.read_bytes(),
                         b"foreign-inode-after-partial-write")

    def test_failed_readback_keeps_foreign_changes_to_same_inode(self):
        from tools.seal_map02_private_finalization import _publish
        receipt = self.seal_dir / NAME

        def mutate_during_readback(fd, length, offset):
            receipt.write_bytes(b"foreign-modified-evidence")
            return b"corrupted"

        with patch(
                "tools.seal_map02_private_finalization.os.pread",
                side_effect=mutate_during_readback):
            with self.assertRaisesRegex(ValueError, "readback/identity"):
                _publish(self.seal_dir, b"original-synthetic-receipt\n")
        self.assertEqual(receipt.read_bytes(), b"foreign-modified-evidence")

    def test_second_audit_mismatch_never_publishes_seal(self):
        from tools.seal_map02_private_finalization import finalize_private_capture
        original = finalize_private_capture
        count = [0]
        def change(*args, **kw):
            report = original(*args, **kw)
            count[0] += 1
            if count[0] == 2:
                report = dict(report, verified_draw_primitives=99)
            return report
        with patch(
                "tools.seal_map02_private_finalization.finalize_private_capture",
                side_effect=change):
            with self.assertRaisesRegex(ValueError, "changed between audits"):
                self.call()
        self.assertEqual(count[0], 2)
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_postpublication_third_audit_blocks_changed_source_and_rolls_back(self):
        from tools.seal_map02_private_finalization import finalize_private_capture
        original = finalize_private_capture
        calls = [0]
        def change_on_postpublication(*args, **kwargs):
            report = original(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 3:
                report = dict(report, verified_draw_primitives=4)
            return report
        with patch(
                "tools.seal_map02_private_finalization.finalize_private_capture",
                side_effect=change_on_postpublication):
            with self.assertRaisesRegex(ValueError, "final seal differs"):
                self.call()
        self.assertEqual(calls[0], 3)
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_postpublication_failure_must_not_delete_replaced_foreign_inode(self):
        def replace_seal(*args, **kwargs):
            path = self.seal_dir / NAME
            path.unlink()
            path.write_bytes(b"foreign-evidence")
            path.chmod(0o600)
            raise ValueError("postpublication readback failed")
        with patch(
                "tools.seal_map02_private_finalization.verify_final_seal",
                side_effect=replace_seal):
            with self.assertRaisesRegex(ValueError, "readback failed"):
                self.call()
        self.assertEqual((self.seal_dir / NAME).read_bytes(),
                         b"foreign-evidence")

    def test_postaudit_identical_bytes_on_foreign_inode_are_not_accepted(self):
        from tools.seal_map02_private_finalization import verify_final_seal
        original_verify = verify_final_seal
        replacement_bytes = []

        def swap_after_verification(*args, **kwargs):
            result = original_verify(*args, **kwargs)
            path = self.seal_dir / NAME
            replacement_bytes.append(path.read_bytes())
            replacement = self.seal_dir / "foreign-inode"
            replacement.write_bytes(replacement_bytes[-1])
            replacement.chmod(0o600)
            replacement.replace(path)
            return result

        with patch(
                "tools.seal_map02_private_finalization.verify_final_seal",
                side_effect=swap_after_verification):
            with self.assertRaisesRegex(ValueError, "inode changed"):
                self.call()
        # Preserve the foreign inode even though its content is identical.
        self.assertEqual((self.seal_dir / NAME).read_bytes(),
                         replacement_bytes[0])
        self.assertEqual({p.name for p in self.seal_dir.iterdir()}, {NAME})

    def test_postaudit_mutation_of_same_inode_is_not_deleted(self):
        from tools.seal_map02_private_finalization import verify_final_seal
        original_verify = verify_final_seal

        def mutate_after_verification(*args, **kwargs):
            result = original_verify(*args, **kwargs)
            path = self.seal_dir / NAME
            path.write_bytes(b"foreign-same-inode")
            return result

        with patch(
                "tools.seal_map02_private_finalization.verify_final_seal",
                side_effect=mutate_after_verification):
            with self.assertRaisesRegex(ValueError, "inode changed"):
                self.call()
        self.assertEqual((self.seal_dir / NAME).read_bytes(),
                         b"foreign-same-inode")

    def test_postaudit_extra_directory_entry_blocks_success(self):
        from tools.seal_map02_private_finalization import verify_final_seal
        original_verify = verify_final_seal

        def add_foreign_entry(*args, **kwargs):
            result = original_verify(*args, **kwargs)
            (self.seal_dir / "foreign-evidence").write_bytes(b"keep-me")
            return result

        with patch(
                "tools.seal_map02_private_finalization.verify_final_seal",
                side_effect=add_foreign_entry):
            with self.assertRaisesRegex(ValueError, "directory entries changed"):
                self.call()
        self.assertEqual((self.seal_dir / "foreign-evidence").read_bytes(),
                         b"keep-me")
        self.assertFalse((self.seal_dir / NAME).exists())

    def test_missing_png_or_cd_proof_does_not_seal(self):
        (self.fixture.preview / "map02-native-vram-preview.png").unlink()
        with self.assertRaises(ValueError):
            self.call()
        self.assertEqual(list(self.seal_dir.iterdir()), [])

    def test_private_directory_must_be_separate_and_owner_only(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            self.call(seal=self.fixture.preview)
        self.seal_dir.chmod(0o755)
        self.addCleanup(self.seal_dir.chmod, 0o700)
        with self.assertRaises(ValueError):
            self.call()
        self.seal_dir.chmod(0o700)
        other = self.seal_dir / "other"
        other.write_text("foreign")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.call()
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.call(action="verify")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_private_final_seal_fifo_rejected_without_blocking(self):
        self.call()
        receipt = self.seal_dir / NAME
        receipt.unlink()
        os.mkfifo(receipt, mode=0o600)
        real_open = os.open

        def guarded_open(path, flags, *args, **kwargs):
            if (os.fspath(path) == os.fspath(receipt) and
                    not flags & os.O_NONBLOCK):
                raise AssertionError("FIFO opened without O_NONBLOCK")
            return real_open(path, flags, *args, **kwargs)

        # A regression must fail immediately instead of blocking the runner.
        with patch("tools.seal_map02_private_finalization.os.open",
                   side_effect=guarded_open):
            with self.assertRaisesRegex(ValueError, "regular file"):
                self.call(action="verify")

    def test_symlink_and_hardlink_receipt_rejected(self):
        seal = self.seal_dir / NAME
        seal.symlink_to(Path("/untrusted/seal"))
        with self.assertRaises(ValueError):
            self.call()
        with self.assertRaises(ValueError):
            self.call(action="verify")
        seal.unlink()
        self.call()
        other = self.seal_dir.parent / "hardlink-seal"
        other.hardlink_to(seal)
        self.addCleanup(other.unlink)
        with self.assertRaises(ValueError):
            self.call(action="verify")


if __name__ == "__main__":
    unittest.main()
