"""Private two-word MAP02 manifest publication and rollback regressions."""
import hashlib
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

import test_verify_map02_putpixel_multi_scope as fixture_module
from tools.publish_map02_multi_capture_manifest import publish_multi_manifest
from tools.verify_map02_putpixel_multi_scope import MANIFEST, verify_multi_pixel_ot


class MultiCaptureReceiptPublisherTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.TwoWordPutPixelTests(
            methodName="test_interleaved_two_coordinates_bound_to_same_drawotag")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source, self.native = self.fixture.source, self.fixture.native
        self.target = self.source / MANIFEST
        # This file exists in the legacy hand-written synthetic fixture;
        # exercise the new publisher starting with NO published receipt.
        self.target.unlink()
        self.assertFalse(self.target.exists())

    def test_publishes_private_receipt_only_after_full_replay(self):
        pixel_path = self.native / "putpixel-native-events.jsonl"
        prior_pixel_sha = hashlib.sha256(pixel_path.read_bytes()).hexdigest()
        report = publish_multi_manifest(self.source, self.native)
        self.assertTrue(report["private_receipt_published"])
        self.assertTrue(report["private_capture_dependencies_rechecked"])
        self.assertGreater(report["private_capture_dependency_file_count"], 5)
        self.assertEqual(report["distinct_private_vram_words_verified"], 2)
        self.assertEqual(report["source_keyed_ft4_draws_checked"], 2)
        self.assertFalse(report["native_capture_process_identity_authenticated"])
        self.assertFalse(report["real_map02_gameplay_authenticated"])
        self.assertFalse(report["physical_ps1_pixel_equivalence_verified"])
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(report["two_word_manifest_sha256"],
                         hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(hashlib.sha256(pixel_path.read_bytes()).hexdigest(),
                         prior_pixel_sha)
        manifest = json.loads(self.target.read_bytes())
        self.assertEqual(manifest["schema"],"vh.map02.native-putpixel-multi-ot.v1")
        self.assertEqual(manifest["source_frame"],411)
        self.assertEqual(manifest["gpu_draw_frame"],12)
        checked = verify_multi_pixel_ot(self.source, self.native)
        self.assertEqual(checked["two_word_manifest_sha256"],
                         report["two_word_manifest_sha256"])
        public = json.dumps(report)
        for raw_key in ('"x"','"y"','"front"','"before"','"after"',
                        '"xy"','"clut"','/tmp/','0x801f'):
            self.assertNotIn(raw_key, public)

    def test_existing_receipt_not_overwritten_even_if_content_is_invalid(self):
        self.target.write_bytes(b"DO NOT OVERWRITE")
        with self.assertRaisesRegex(ValueError, "already exists"):
            publish_multi_manifest(self.source, self.native)
        self.assertEqual(self.target.read_bytes(), b"DO NOT OVERWRITE")

    def test_bad_pixel_arithmetic_refused_without_creating_receipt(self):
        self.fixture.rows[0]["front"] = 0x03e0
        self.fixture.save()
        self.target.unlink()
        with self.assertRaisesRegex(ValueError, "source-pinned PC WritePixel|two-word PutPixel"):
            publish_multi_manifest(self.source, self.native)
        self.assertFalse(self.target.exists())

    def test_incomplete_second_word_refused_without_creating_receipt(self):
        self.fixture.rows = [
            self.fixture.base.row(0, 1, 0, 0x801f, 0x801f),
            self.fixture.base.row(1, 2, 0x801f, 0x7c00, 0x7c00),
        ]
        self.fixture.save()
        self.target.unlink()
        with self.assertRaisesRegex(ValueError, "exactly two distinct"):
            publish_multi_manifest(self.source, self.native)
        self.assertFalse(self.target.exists())

    def test_mutated_primary_log_after_replay_refused(self):
        from tools import publish_map02_multi_capture_manifest as publisher
        original = publisher._input_bytes
        count = [0]

        def change_after_replay(source_dir, native_dir):
            result = original(source_dir, native_dir)
            count[0] += 1
            if count[0] == 2:
                result = dict(result)
                result["putpixel_events_sha256"] = "0" * 64
            return result

        with patch.object(publisher, "_input_bytes",
                          side_effect=change_after_replay):
            with self.assertRaisesRegex(ValueError, "mutated during verification"):
                publish_multi_manifest(self.source, self.native)
        self.assertEqual(count[0], 2)
        self.assertFalse(self.target.exists())

    def test_native_vram_snapshot_mutated_after_replay_refused(self):
        # This full 1 MiB snapshot is not one of the three separately
        # bound JSONL/manifest hashes. Mutation after valid replay must
        # nevertheless prevent private receipt publication.
        from tools import publish_map02_multi_capture_manifest as publisher
        original = publisher.verify_multi_pixel_ot
        snapshot = self.native / "gpu-0003-vram.bin"

        def mutate_after_replay(*args, **kwargs):
            result = original(*args, **kwargs)
            raw = bytearray(snapshot.read_bytes())
            raw[0] ^= 1
            snapshot.write_bytes(raw)
            return result

        with patch.object(publisher, "verify_multi_pixel_ot",
                          side_effect=mutate_after_replay):
            with self.assertRaisesRegex(ValueError, "dependencies mutated"):
                publish_multi_manifest(self.source, self.native)
        self.assertFalse(self.target.exists())

    def test_source_ft4_log_mutated_after_replay_refused(self):
        from tools import publish_map02_multi_capture_manifest as publisher
        original = publisher.verify_multi_pixel_ot
        source_log = self.source / "gpu-events.jsonl"

        def mutate_after_replay(*args, **kwargs):
            result = original(*args, **kwargs)
            source_log.write_bytes(source_log.read_bytes() + b" ")
            return result

        with patch.object(publisher, "verify_multi_pixel_ot",
                          side_effect=mutate_after_replay):
            with self.assertRaisesRegex(ValueError, "dependencies mutated"):
                publish_multi_manifest(self.source, self.native)
        self.assertFalse(self.target.exists())

    def test_injected_post_fsync_dependency_change_rolls_back_receipt(self):
        from tools import publish_map02_multi_capture_manifest as publisher
        original = publisher._capture_dependency_inventory
        count = [0]

        def changed_after_fsync(*args):
            result = original(*args)
            count[0] += 1
            if count[0] == 3:
                return result + (("native", "unexpected", "0" * 64),)
            return result

        with patch.object(publisher, "_capture_dependency_inventory",
                          side_effect=changed_after_fsync):
            with self.assertRaisesRegex(ValueError, "mutated after receipt fsync"):
                publish_multi_manifest(self.source, self.native)
        self.assertEqual(count[0], 3)
        self.assertFalse(self.target.exists())

    def test_capture_dependency_symlink_and_subdirectory_refused(self):
        linked = self.native / "snapshot-alias"
        linked.symlink_to(self.native / "gpu-0003-vram.bin")
        with self.assertRaisesRegex(ValueError, "regular, nonlinked"):
            publish_multi_manifest(self.source, self.native)
        linked.unlink()
        nested = self.native / "unexpected-subdirectory"
        nested.mkdir()
        with self.assertRaisesRegex(ValueError, "regular, nonlinked"):
            publish_multi_manifest(self.source, self.native)
        self.assertFalse(self.target.exists())

    def test_directory_symlink_and_receipt_symlink_refused(self):
        linked = self.source.parent / "source-symlink"
        linked.symlink_to(self.source, target_is_directory=True)
        self.addCleanup(linked.unlink)
        with self.assertRaisesRegex(ValueError, "directory missing or symlinked"):
            publish_multi_manifest(linked, self.native)
        self.target.symlink_to(self.native / "putpixel-native-events.jsonl")
        with self.assertRaisesRegex(ValueError, "already exists"):
            publish_multi_manifest(self.source, self.native)


if __name__ == "__main__":
    unittest.main()
