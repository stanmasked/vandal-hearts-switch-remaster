"""Private SHA-bound final MAP02 source/window/pixel/blend/VRAM witness tests.

The source GTE verifier is mocked ONLY in this clearly synthetic unit
fixture. Actual native GPU windows, full VRAM buffers, scoped event joins,
hashes, privacy and publishing logic all execute unmocked.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from tests.test_verify_map02_window_scoped_join import WindowScopedJoinTests
from tools.publish_map02_window_scoped_witness import (
    MANIFEST, SCHEMA, _validate,
    publish_window_scoped_witness, verify_published_window_scoped_witness,
)
from tools.publish_map02_native_window_source_witness import (
    MANIFEST as SOURCE_WITNESS,
)


class FinalWindowScopedWitnessTests(unittest.TestCase):
    def setUp(self):
        fixture = WindowScopedJoinTests(
            methodName="test_observed_selected_pixel_and_global_draw_ordinals_match")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.native = fixture.native
        self.scoped = fixture.scoped
        # Asset-free, deterministic fixture nonce only; real PC runtime
        # obtains unpredictable fresh token from OS randomness.
        token = "bc" * 16
        index = self.native / "gpu-native-window-index.json"
        meta = json.loads(index.read_bytes())
        meta["capture_session"] = token
        index.write_text(json.dumps(meta, sort_keys=True) + "\n")
        (self.scoped / "gpu-scoped-session.json").write_text(
            json.dumps({
                "schema": "vh.map02.scoped-session.v1",
                "gpu_draw_frame": 7, "capture_session": token,
            }, sort_keys=True) + "\n")
        self.source = self.native.parent / "source"
        self.source.mkdir(mode=0o700)
        self.source_bytes = (
            b'{"schema":"synthetic-only-source-GTE-witness"}\n'
        )
        (self.source / SOURCE_WITNESS).write_bytes(self.source_bytes)
        self.source_digest = hashlib.sha256(self.source_bytes).hexdigest()
        self.mock = patch(
            "tools.verify_map02_window_scoped_join.verify_published_window_source_witness",
            return_value={
                "native_window_file_tree_bound": True,
                "window_source_witness_manifest_sha256": self.source_digest,
            },
        )
        self.stub_source = self.mock.start()
        self.addCleanup(self.mock.stop)

    def publish(self):
        return publish_window_scoped_witness(
            self.source, self.native, self.scoped, frame=7)

    def verify(self, *, frame=7):
        return verify_published_window_scoped_witness(
            self.source, self.native, self.scoped, frame=frame)

    def test_publish_recheck_all_four_streams_and_source_bound_sha(self):
        result = self.publish()
        self.assertTrue(result["four_scoped_gpu_streams_source_bound"])
        self.assertEqual(result["global_draw_ordinals_checked"], 2)
        final = self.source / MANIFEST
        self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o600)
        payload = json.loads(final.read_bytes())
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual(payload["source_window_witness_manifest_sha256"],
                         self.source_digest)
        self.assertEqual(
            payload["putpixel_staged_sha256"],
            hashlib.sha256(
                (self.scoped / "putpixel-native-events.pending.jsonl").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(payload["independently_sampled_draw_edges"], 2)
        self.assertFalse(payload["whole_original_gameplay_frame_proven"])
        self.assertFalse(payload["physical_ps1_equivalence_proven"])
        assert result == self.verify()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.publish()
        self.assertFalse(list(self.source.glob(".*.tmp")))

    def test_missing_original_source_binding_fails_without_marker(self):
        self.stub_source.return_value = {
            "native_window_file_tree_bound": True,
            "window_source_witness_manifest_sha256": "a" * 64,
        }
        with self.assertRaisesRegex(ValueError, "GTE window witness changed"):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())
        self.assertFalse(list(self.source.glob(".*.tmp")))

    def test_source_verifier_cannot_be_skipped_or_claim_false_proof(self):
        self.stub_source.side_effect = ValueError("original source GTE unavailable")
        with self.assertRaisesRegex(ValueError, "GTE"):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())
        self.stub_source.side_effect = None
        self.publish()
        manifest = self.source / MANIFEST
        data = json.loads(manifest.read_bytes())
        for key in ("whole_original_gameplay_frame_proven",
                    "physical_ps1_equivalence_proven"):
            tampered = dict(data, **{key: True})
            manifest.write_text(json.dumps(tampered) + "\n")
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "overstated"):
                self.verify()
        self.assertFalse(self.verify_accepted_tampered_manifest())

    def verify_accepted_tampered_manifest(self):
        try:
            self.verify()
        except ValueError:
            return False
        return True

    def test_rejects_scoped_receipt_from_another_process(self):
        session = self.scoped / "gpu-scoped-session.json"
        meta = json.loads(session.read_bytes())
        meta["capture_session"] = "de" * 16
        session.write_text(json.dumps(meta) + "\n")
        with self.assertRaisesRegex(ValueError, "mixed-session"):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())

    def test_rejects_missing_scoped_receipt(self):
        (self.scoped / "gpu-scoped-session.json").unlink()
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())

    def test_reverify_rejects_tampered_scoped_and_full_vram_snapshots(self):
        self.publish()
        pixel = self.scoped / "putpixel-native-events.pending.jsonl"
        pixel.write_bytes(pixel.read_bytes().replace(b'"before":0', b'"before":8'))
        with self.assertRaises(ValueError):
            self.verify()
        self.fixture.save()
        snapshot = self.native / "window-000" / "gpu-0003-vram.bin"
        data = bytearray(snapshot.read_bytes())
        data[0] ^= 1
        snapshot.write_bytes(data)
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_frame_and_noncanonical_manifest_rejected(self):
        self.publish()
        with self.assertRaisesRegex(ValueError, "frame"):
            self.verify(frame=8)
        final = self.source / MANIFEST
        data = json.loads(final.read_bytes())
        examples = (
            dict(data, gpu_frame=True),
            dict(data, putpixel_staged_sha256="not-a-digest"),
            dict(data, independently_sampled_draw_edges=1),
            dict(data, schema="not-our-schema"),
            dict(data, source_gte_subsequence_verified=False),
        )
        for bad in examples:
            final.write_text(json.dumps(bad) + "\n")
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.verify()
        with self.assertRaises(ValueError):
            _validate(json.loads('{"schema":"x"}'))

    def test_publish_aborts_cleanly_if_second_verification_disagrees(self):
        from tools.publish_map02_window_scoped_witness import _verified_payload
        correct = _verified_payload(
            self.source, self.native, self.scoped, frame=7, compiler="gcc")
        corrupted = dict(correct, putpixel_staged_sha256="f" * 64)
        with patch(
            "tools.publish_map02_window_scoped_witness._verified_payload",
            side_effect=[correct, corrupted],
        ):
            with self.assertRaisesRegex(ValueError, "changed before publication"):
                self.publish()
        self.assertFalse((self.source / MANIFEST).exists())
        self.assertFalse(list(self.source.glob(".*.tmp")))

    def test_exclusive_link_failure_leaves_no_publication(self):
        with patch(
            "tools.publish_map02_window_scoped_witness.os.link",
            side_effect=OSError("permission denied"),
        ):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse((self.source / MANIFEST).exists())
        self.assertFalse(list(self.source.glob(".*.tmp")))

    def test_rejects_symlinked_source_witness_and_nonprivate_directory(self):
        source_manifest = self.source / SOURCE_WITNESS
        source_manifest.unlink()
        raw = self.source / "symlink-target"
        raw.write_bytes(self.source_bytes)
        source_manifest.symlink_to(raw)
        with self.assertRaises(ValueError):
            self.publish()
        source_manifest.unlink()
        raw.rename(source_manifest)
        os.chmod(self.source, 0o755)
        with self.assertRaises(ValueError):
            self.publish()


if __name__ == "__main__":
    unittest.main()
