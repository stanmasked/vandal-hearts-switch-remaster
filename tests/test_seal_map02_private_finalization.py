"""Private final MAP02 seal/verification (synthetic CD and GPU only)."""
import hashlib
import json
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
        receipt.write_text(json.dumps(record, sort_keys=True) + "\n")
        with self.assertRaisesRegex(ValueError, "authenticity flags"):
            self.call(action="verify")
        receipt.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "not canonical"):
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
