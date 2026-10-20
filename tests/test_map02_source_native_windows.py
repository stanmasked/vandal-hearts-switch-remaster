"""Synthetic SHA-bound source FT4 -> window witness regressions.

Only verify_bundle (the expensive independently captured GTE source check)
is mocked in this fixture. Actual window full-VRAM and texture/OT checks run.
No synthetic result is evidence of authentic MAP02 gameplay.
"""
import hashlib
import io
import json
import os
from contextlib import redirect_stderr
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import tools.verify_map02_source_native_windows as source_module
import tools.publish_map02_native_window_source_witness as witness_module

from tests.test_verify_map02_native_gpu_windows import (
    NativeGpuWindowEvidenceTests, jsonline,
)
from tools.verify_map02_source_native_windows import (
    CLAIM, verify_window_source_join,
)
from tools.publish_map02_native_window_source_witness import (
    MANIFEST, publish_window_source_witness,
    verify_published_window_source_witness,
)
from tools.verify_map02_vram_timeline import VRAM_BYTES
from tools.verify_map02_frame_bundle import MAP_BYTES


def sha(data):
    return hashlib.sha256(data).hexdigest()


class WindowSourceWitnessTests(unittest.TestCase):
    def setUp(self):
        # Reuse the actual byte-backed native-VRAM fixture, not mocked GPU
        # records or invented window verifier return values.
        fixture = NativeGpuWindowEvidenceTests(
            methodName="test_small_one_window_is_not_mislabeled_as_complete_gameplay")
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        self.fixture = fixture
        self.native = fixture.root
        self.source = self.native.parent / "source"
        self.source.mkdir(mode=0o700)
        self.window = fixture.window
        first = fixture.events[0]
        second = fixture.events[1]
        self.source_event = {
            "gte": {"perimeter_xy": [[0, 0], [2, 0], [0, 2], [2, 2]],
                    "raw_otz": 6},
            "texture": {
                "tpage": 0, "clut": 0, "u": 0, "v": 0, "w": 1, "h": 1,
                "mask_x": 0, "mask_y": 0,
                "offset_x": 0, "offset_y": 0,
            },
        }
        native_ft4 = {
            "tpage": 0, "clut": 0,
            "xy": [0, 0, 2, 0, 2, 2, 0, 2],
            "uv": [0, 0, 1, 0, 0, 1, 1, 1],
        }
        for event in (first, second):
            event["ft4"] = native_ft4
            event["primitive_type"] = 2
        self.save_native()
        self.source_bundle = jsonline({"ot_size": 64})
        self.source_events = jsonline(self.source_event)
        (self.source / "bundle.json").write_bytes(self.source_bundle)
        (self.source / "gpu-events.jsonl").write_bytes(self.source_events)
        (self.source / "gpu-vram-le.bin").write_bytes(bytes(VRAM_BYTES))
        (self.source / "map02.decoded.bin").write_bytes(bytes(MAP_BYTES))
        self.claim = {
            "schema": "vh.map02.native-window-source-claim.v1",
            "source_frame": 7, "gpu_draw_frame": 7,
            "source_bundle_manifest_sha256": sha(self.source_bundle),
            "source_events_sha256": sha(self.source_events),
            "native_window_index_sha256": sha(
                (self.native / "gpu-native-window-index.json").read_bytes()),
            "source_events_in_addprim_order": True,
            "one_clear_otag_one_draw_otag": True,
        }
        self.save_claim()
        self.mock_bundle = patch(
            "tools.verify_map02_source_native_windows.verify_bundle",
            return_value={"frame": 7, "submitted_faces_checked": 1})
        self.checked_bundle = self.mock_bundle.start()
        self.addCleanup(self.mock_bundle.stop)

    def save_claim(self):
        (self.source / CLAIM).write_bytes(jsonline(self.claim))

    def save_native(self):
        (self.window / "gpu-native-events.jsonl").write_bytes(
            b"".join(map(jsonline, self.fixture.events)))

    def test_exact_ft4_materials_and_relative_ot_source_join(self):
        result = verify_window_source_join(self.source, self.native)
        self.checked_bundle.assert_called()
        self.assertTrue(result["original_gte_compiled_and_checked"])
        self.assertTrue(result["source_map_vram_inode_and_bytes_reverified"])
        self.assertEqual(result["source_ft4_exact_matches"], 1)
        self.assertEqual(result["native_draw_pairs"], 2)
        self.assertEqual(result["native_gpu_events"], 4)
        self.assertGreaterEqual(result["source_texture_palette_words_checked"], 1)
        self.assertFalse(result["source_addprim_chronology_authenticated"])
        self.assertFalse(result["full_original_scene_authenticated"])

    def test_source_ft4_and_witness_survive_window1_loadimage_transfer(self):
        # One actual, independently audited GPU window fixture holds 64
        # invented DRAW events and a post-boundary LoadImage transfer pair.
        # Only the expensive source/GTE bundle is mocked: ALL native VRAM,
        # per-window filenames, upload bytes and witness hashes are real.
        second = self.fixture.build_two_windows_across_recorder_capacity()
        first_log = self.window / "gpu-native-events.jsonl"
        records = [json.loads(line) for line in first_log.read_bytes().splitlines()]
        packet = dict(self.fixture.events[0]["ft4"])
        for event in records[:2]:
            event["ft4"] = packet
            event["primitive_type"] = 2
        first_log.write_bytes(b"".join(jsonline(e) for e in records))

        window1_log = second / "gpu-native-events.jsonl"
        window1 = [json.loads(line) for line in window1_log.read_bytes().splitlines()]
        for event in window1:
            event.update(operation="load", frame=6, rect=[0, 0, 1, 1],
                         primitive_type=0)
        local_name = "gpu-0001-upload.bin"
        window1[0]["upload"] = ""
        window1[1]["upload"] = local_name
        window1_log.write_bytes(b"".join(jsonline(e) for e in window1))
        (second / local_name).write_bytes((33).to_bytes(2, "little"))
        self.fixture.status.update(
            draw_before_hooks=32, transfer_before_hooks=1)
        self.fixture.save_status()
        self.claim["native_window_index_sha256"] = sha(
            (self.native / "gpu-native-window-index.json").read_bytes())
        self.save_claim()

        # A source-keyed FT4 in window 000 must remain uniquely bound to
        # source materials despite a later, independently verified upload.
        joined = verify_window_source_join(self.source, self.native)
        self.assertEqual(joined["native_windows"], 2)
        self.assertEqual(joined["native_gpu_events"], 66)
        self.assertEqual(joined["native_draw_pairs"], 32)
        self.assertEqual(joined["source_ft4_exact_matches"], 1)
        self.assertFalse(joined["full_original_scene_authenticated"])

        receipt = publish_window_source_witness(self.source, self.native)
        self.assertTrue(receipt["native_window_file_tree_bound"])
        original = verify_published_window_source_witness(
            self.source, self.native)
        self.assertEqual(original["source_ft4_exact_matches"], 1)

        # A corrupted or legacy global upload pathname in window 001
        # must invalidate the source-linked published witness too.
        (second / local_name).rename(second / "gpu-0065-upload.bin")
        window1[1]["upload"] = "gpu-0065-upload.bin"
        window1_log.write_bytes(b"".join(jsonline(e) for e in window1))
        with self.assertRaisesRegex(ValueError, "upload name"):
            verify_published_window_source_witness(self.source, self.native)

    def test_rejects_unsampled_source_vram_mutation_during_gte(self):
        # This source VRAM word is outside the FT4 texture/CLUT
        # material footprint. The material comparison alone would pass
        # even though the source game asset was modified after capture.
        def mutate_then_return(*args, **kwargs):
            path = self.source / "gpu-vram-le.bin"
            with path.open("r+b") as stream:
                stream.seek(VRAM_BYTES - 2)
                stream.write(b"\x01\x00")
            return {"frame": 7, "submitted_faces_checked": 1}

        self.checked_bundle.side_effect = mutate_then_return
        with self.assertRaisesRegex(ValueError, "asset changed"):
            verify_window_source_join(self.source, self.native)

    def test_rejects_byte_identical_decoded_map_inode_swap_during_gte(self):
        # Hash-only verification would accept an identically copied file;
        # the verified private source inode must stay fixed as well.
        def replace_inode_then_return(*args, **kwargs):
            original = self.source / "map02.decoded.bin"
            staged = self.source / "private-local-map02-replacement.tmp"
            staged.write_bytes(original.read_bytes())
            os.replace(staged, original)
            return {"frame": 7, "submitted_faces_checked": 1}

        self.checked_bundle.side_effect = replace_inode_then_return
        with self.assertRaisesRegex(ValueError, "asset changed"):
            verify_window_source_join(self.source, self.native)

    def test_rejects_decoded_map_content_mutation_during_gte(self):
        def mutate_then_return(*args, **kwargs):
            original = self.source / "map02.decoded.bin"
            with original.open("r+b") as stream:
                stream.seek(MAP_BYTES - 1)
                stream.write(b"\x40")
            return {"frame": 7, "submitted_faces_checked": 1}

        self.checked_bundle.side_effect = mutate_then_return
        with self.assertRaisesRegex(ValueError, "asset changed"):
            verify_window_source_join(self.source, self.native)

    def test_publish_reverify_exclusive_sha_and_0600(self):
        result = publish_window_source_witness(self.source, self.native)
        self.assertEqual(result["verified_source_ft4_subsequence"], 1)
        final = self.source / MANIFEST
        self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o600)
        report = verify_published_window_source_witness(
            self.source, self.native)
        self.assertTrue(report["native_window_file_tree_bound"])
        self.assertFalse(report["full_original_scene_authenticated"])
        manifest = json.loads(final.read_bytes())
        self.assertEqual(
            manifest["native_window_all_files_sha256"],
            verify_window_source_join(self.source, self.native)[
                "native_window_all_files_sha256"])
        with self.assertRaises(ValueError):
            publish_window_source_witness(self.source, self.native)

    def test_cryptographic_claim_or_frame_mismatch_rejected(self):
        for field, value in (
            ("source_bundle_manifest_sha256", "0" * 64),
            ("native_window_index_sha256", "0" * 64),
            ("source_frame", 9),
            ("gpu_draw_frame", 8),
            ("source_events_in_addprim_order", False),
            ("one_clear_otag_one_draw_otag", 1),
        ):
            old = self.claim[field]
            self.claim[field] = value
            self.save_claim()
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_window_source_join(self.source, self.native)
            self.claim[field] = old
        self.save_claim()

    def test_rejects_changed_original_gpu_ft4_packet(self):
        first, second = self.fixture.events[:2]
        for e in (first, second):
            e["ft4"]["tpage"] = 1
        self.save_native()
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            verify_window_source_join(self.source, self.native)

    def test_rejects_modified_texture_vram_even_with_valid_window_structure(self):
        path = self.window / "gpu-0000-vram.bin"
        data = bytearray(path.read_bytes())
        data[:2] = b"\x01\x00"  # source 4-bpp word was zero
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "texture/CLUT"):
            verify_window_source_join(self.source, self.native)

    def test_rejects_ambiguous_duplicate_gpu_ft4_packets(self):
        first_ft4 = self.fixture.events[0]["ft4"]
        for event in self.fixture.events[2:]:
            event["ft4"] = dict(first_ft4)
            event["primitive_type"] = 2
        self.save_native()
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            verify_window_source_join(self.source, self.native)

    def test_two_source_faces_obey_relative_ot_depth_order(self):
        # The first draw changes VRAM word 0. Isolate the second
        # synthetic CLUT on a different row, so the source palette remains
        # constant rather than weakening the real material-equivalence gate.
        second_packet = {
            "tpage": 1, "clut": 64,
            "xy": [4, 4, 6, 4, 6, 6, 4, 6],
            "uv": [0, 0, 1, 0, 0, 1, 1, 1],
        }
        for event in self.fixture.events[2:]:
            event["ft4"] = dict(second_packet)
            event["primitive_type"] = 2
        self.save_native()
        self.source_event["gte"]["raw_otz"] = 8
        second = {
            "gte": {"perimeter_xy": [[4, 4], [6, 4], [4, 6], [6, 6]],
                    "raw_otz": 6},
            "texture": dict(self.source_event["texture"], tpage=1, clut=64),
        }
        self.source_events = jsonline(self.source_event) + jsonline(second)
        (self.source / "gpu-events.jsonl").write_bytes(self.source_events)
        self.claim["source_events_sha256"] = sha(self.source_events)
        self.save_claim()
        self.checked_bundle.return_value = {
            "frame": 7, "submitted_faces_checked": 2,
        }
        verified = verify_window_source_join(self.source, self.native)
        self.assertEqual(verified["source_ft4_exact_matches"], 2)
        self.assertTrue(verified["source_ft4_relative_ot_order_checked"])
        # Same source packets and native bytes, but an impossible original
        # OT depth ordering: the higher depth second face should draw first.
        self.source_event["gte"]["raw_otz"] = 5
        self.source_events = jsonline(self.source_event) + jsonline(second)
        (self.source / "gpu-events.jsonl").write_bytes(self.source_events)
        self.claim["source_events_sha256"] = sha(self.source_events)
        self.save_claim()
        with self.assertRaisesRegex(ValueError, "relative DrawOTag order"):
            verify_window_source_join(self.source, self.native)

    def test_refuses_false_source_gte_and_postpublish_tampering(self):
        self.checked_bundle.side_effect = ValueError("GTE source verification failed")
        with self.assertRaisesRegex(ValueError, "GTE source"):
            publish_window_source_witness(self.source, self.native)
        self.assertFalse((self.source / MANIFEST).exists())
        self.checked_bundle.side_effect = None
        publish_window_source_witness(self.source, self.native)
        path = self.window / "gpu-0003-vram.bin"
        data = bytearray(path.read_bytes())
        data[0] ^= 1
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            verify_published_window_source_witness(self.source, self.native)


class PrivateSourceWindowCliRedactionTests(unittest.TestCase):
    def test_source_join_cli_never_logs_private_capture_paths(self):
        private_path = "/private/owned-vandal-hearts/MAP02/raw-vram.bin"
        with patch("sys.argv", ["window-source-join", private_path, "/private/windows"]), \
             patch.object(source_module, "verify_window_source_join",
                          side_effect=ValueError("bad private source: " + private_path)), \
             redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as outcome:
                source_module.main()
        self.assertEqual(outcome.exception.code, 2)
        self.assertIn("private MAP02 source/native window join unavailable",
                      error.getvalue())
        self.assertNotIn(private_path, error.getvalue())

    def test_window_witness_publish_and_verify_cli_redact_private_paths(self):
        private_path = "/private/owned-vandal-hearts/MAP02/game-image.bin"
        for publish in (False, True):
            with self.subTest(publish=publish):
                argv = ["window-witness", private_path, "/private/windows"]
                if publish:
                    argv.append("--publish")
                function = (
                    "publish_window_source_witness" if publish
                    else "verify_published_window_source_witness"
                )
                with patch("sys.argv", argv), \
                     patch.object(witness_module, function,
                                  side_effect=ValueError("private asset: " + private_path)), \
                     redirect_stderr(io.StringIO()) as error:
                    with self.assertRaises(SystemExit) as outcome:
                        witness_module.main()
                self.assertEqual(outcome.exception.code, 2)
                self.assertIn("private MAP02 native window witness unavailable",
                              error.getvalue())
                self.assertNotIn(private_path, error.getvalue())


if __name__ == "__main__":
    unittest.main()
