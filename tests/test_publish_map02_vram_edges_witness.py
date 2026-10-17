"""Synthetic private SHA-bound VRAM-edge publication/verification regressions.

Upstream source/DrawOTag provenance is mocked IN THESE TESTS ONLY; this
does not authenticate a real original MAP02 game frame.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tests.test_map02_vram_edge_witness import sample, line
from tools.publish_map02_vram_edges_witness import (
    publish_vram_edges, MANIFEST, PENDING, EDGE_LOG, SCHEMA,
)
from tools.verify_map02_vram_edges_witness import verify_vram_edges


class PrivateVramEdgePublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src = base / "source"
        self.native = base / "native"
        self.src.mkdir(mode=0o700)
        self.native.mkdir(mode=0o700)
        pixels, edges = sample()
        self.pixel_raw = b"".join(map(line, pixels))
        self.edge_raw = b"".join(map(line, edges))
        self.blend_raw = b'{"stage":"native_blendg1"}\n'
        self.blend_meta = line({
            "schema": "vh.map02.native-blendg1-witness.v1",
            "pixel_ot_manifest_sha256": "0" * 64,
            "putpixel_events_sha256": hashlib.sha256(self.pixel_raw).hexdigest(),
            "blendg1_events_sha256": hashlib.sha256(self.blend_raw).hexdigest(),
        })
        (self.src / "gpu-blendg1-witness.json").write_bytes(self.blend_meta)
        (self.native / "putpixel-native-events.jsonl").write_bytes(self.pixel_raw)
        (self.native / "blendg1-native-events.jsonl").write_bytes(self.blend_raw)
        (self.native / PENDING).write_bytes(self.edge_raw)
        self.mock_result = {
            "observed_blendg1_putpixel_pairs": 1,
            "upstream_putpixel_calls": 4,
            "verified_blendg1_log_sha256": hashlib.sha256(self.blend_raw).hexdigest(),
        }
        self.pub = patch("tools.publish_map02_vram_edges_witness.verify_blendg1_witness",
                         return_value=self.mock_result)
        self.ver = patch("tools.verify_map02_vram_edges_witness.verify_blendg1_witness",
                         return_value=self.mock_result)
        self.mock_pub = self.pub.start()
        self.mock_ver = self.ver.start()
        self.addCleanup(self.pub.stop)
        self.addCleanup(self.ver.stop)

    def test_complete_private_sha_bound_publication_and_reread(self):
        report = publish_vram_edges(self.src, self.native)
        self.assertEqual(report["independently_sampled_draw_edges"], 5)
        self.assertEqual(report["unchanged_draws_without_selected_pixel_writes"], 1)
        verified = verify_vram_edges(self.src, self.native)
        self.assertTrue(verified["direct_vram_endpoint_matches_putpixel"])
        self.assertFalse(verified["original_gameplay_authenticated"])
        meta = json.loads((self.src / MANIFEST).read_bytes())
        self.assertEqual(meta["schema"], SCHEMA)
        self.assertEqual(meta["blendg1_manifest_sha256"],
                         hashlib.sha256(self.blend_meta).hexdigest())
        self.assertEqual(meta["vram_edges_sha256"],
                         hashlib.sha256(self.edge_raw).hexdigest())
        for path in (self.src / MANIFEST, self.native / EDGE_LOG):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual((self.native / EDGE_LOG).read_bytes(), self.edge_raw)
        with self.assertRaises(ValueError):
            publish_vram_edges(self.src, self.native)

    def test_refuses_modified_edges_or_digest(self):
        bad = self.edge_raw.replace(b'"before":4', b'"before":9')
        (self.native / PENDING).write_bytes(bad)
        with self.assertRaises(ValueError):
            publish_vram_edges(self.src, self.native)
        self.assertFalse((self.src / MANIFEST).exists())
        self.assertFalse((self.native / EDGE_LOG).exists())

    def test_refuses_unverified_original_pc_evidence(self):
        self.mock_pub.side_effect = ValueError("original DrawOTag mismatch")
        with self.assertRaisesRegex(ValueError, "original DrawOTag"):
            publish_vram_edges(self.src, self.native)
        self.assertFalse((self.native / EDGE_LOG).exists())

    def test_rejects_nonprivate_or_symlinked_pending(self):
        os.chmod(self.native, 0o755)
        with self.assertRaises(ValueError):
            publish_vram_edges(self.src, self.native)
        os.chmod(self.native, 0o700)
        (self.native / PENDING).unlink()
        (self.native / PENDING).symlink_to(self.native / "putpixel-native-events.jsonl")
        with self.assertRaises(ValueError):
            publish_vram_edges(self.src, self.native)

    def test_rolls_back_on_second_file_link_failure(self):
        actual = os.link
        calls = [0]

        def fail_second(source, dest):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("failure installing completion marker")
            return actual(source, dest)

        with patch("tools.publish_map02_vram_edges_witness.os.link",
                   side_effect=fail_second):
            with self.assertRaises(OSError):
                publish_vram_edges(self.src, self.native)
        self.assertFalse((self.src / MANIFEST).exists())
        self.assertFalse((self.native / EDGE_LOG).exists())
        self.assertFalse(list(self.src.glob(".*.tmp")))
        self.assertFalse(list(self.native.glob(".*.tmp")))

    def test_final_verifier_detects_sha_replacement(self):
        publish_vram_edges(self.src, self.native)
        (self.native / EDGE_LOG).write_bytes(self.edge_raw + b'\n')
        with self.assertRaises(ValueError):
            verify_vram_edges(self.src, self.native)


if __name__ == "__main__":
    unittest.main()
