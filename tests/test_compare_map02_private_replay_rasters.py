"""Synthetic-only tests: fabricated 1x1 PNGs, no BK2/disc/game images."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.compare_map02_private_replay_rasters import compare, SCHEMA


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload +
            struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def tiny_png(rgb, level=6):
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes((0,)) + bytes(rgb), level)) +
            chunk(b"IEND", b""))


class TwoReplayRasterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.inspection = self.root / "inspection.json"
        self.inspection.write_text(json.dumps({
            "schema": "vh.psx.bizhawk.private-bk2-input-inspection.v1",
            "game": "Vandal Hearts (USA)", "platform": "PSX",
            "core": "Octoshock", "input_log_frame_count": 3000,
            "original_ps1_game_image_authenticated": False,
            "map02_scene_frame_identified": False,
        }), encoding="utf-8")
        self.counters = (100, 200, 300)
        self.labels = ("pre_map02", "map02_candidate", "post_map02")
        self.runs = []
        for n in (1, 2):
            d = self.root / f"run{n}"
            d.mkdir()
            images = d / "images"
            images.mkdir()
            markers = d / "markers.txt"
            markers.write_text("some private console messages\n" + "\n".join(
                f"VH_PRIVATE_REPLAY_MARKER counter={frame} "
                f"candidate_input={frame-1} mode=PLAY scene=unverified"
                for frame in self.counters) + "\n", encoding="utf-8")
            manifest = d / "manifest.json"
            observations = []
            for index, (frame, label) in enumerate(zip(self.counters, self.labels)):
                payload = tiny_png((index + 1, 3, 7), 6 if n == 1 else 1)
                name = f"synthetic-{index}.png"
                (images / name).write_bytes(payload)
                observations.append({
                    "emulator_counter": frame,
                    "movie_input_candidate": frame - 1,
                    "label": label, "png_file": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                })
            manifest.write_text(json.dumps({
                "schema": "vh.map02.private-visual-candidates.v1",
                "observations": observations,
            }), encoding="utf-8")
            self.runs.append((markers, manifest, images, observations))

    def compare(self):
        a, b = self.runs
        return compare(self.inspection, *a[:3], *b[:3])

    def rewrite(self, index):
        markers, manifest, root, observations = self.runs[index]
        manifest.write_text(json.dumps({
            "schema": "vh.map02.private-visual-candidates.v1",
            "observations": observations,
        }), encoding="utf-8")

    def test_decoded_pixels_equal_with_different_zlib_payloads(self):
        self.assertNotEqual((self.runs[0][2] / "synthetic-0.png").read_bytes(),
                            (self.runs[1][2] / "synthetic-0.png").read_bytes())
        report = self.compare()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["paired_frames"], 3)
        self.assertTrue(report["decoded_rgba_rasters_equal"])
        self.assertTrue(report["candidate_boundary_raster_change_observed"])
        self.assertFalse(report["scene_transition_authenticated"])
        for flag in ("independent_emulator_runs_authenticated",
                     "movie_to_video_sync_authenticated",
                     "original_ps1_game_authenticated",
                     "map02_scene_frame_identified",
                     "ps1_gpu_vram_parity_proven",
                     "owner_images_or_private_hashes_uploaded"):
            self.assertFalse(report[flag])
        self.assertNotIn("png_file", report)
        self.assertNotIn("sha256", report)

    def set_frame_pixels(self, run_index, frame_index, rgb):
        _, _, images, shots = self.runs[run_index]
        data = tiny_png(rgb, 6 if run_index == 0 else 1)
        (images / shots[frame_index]["png_file"]).write_bytes(data)
        shots[frame_index]["sha256"] = hashlib.sha256(data).hexdigest()
        self.rewrite(run_index)

    def test_static_screen_in_both_runs_is_not_a_transition(self):
        # Two correctly hashed and frame-aligned sessions can still both
        # show exactly the same still screen at the putative scene boundary.
        for run in (0, 1):
            self.set_frame_pixels(run, 1, (1, 3, 7))
        with self.assertRaisesRegex(ValueError, "no decoded raster change"):
            self.compare()

    def test_latest_pre_candidate_witness_required(self):
        # The *last* pre candidate is the visual reference, not the earliest.
        for run in (0, 1):
            self.runs[run][3][1]["label"] = "pre_map02"
            self.runs[run][3][2]["label"] = "map02_candidate"
            self.rewrite(run)
        self.assertTrue(self.compare()["candidate_boundary_raster_change_observed"])
        # First pre differs from the candidate, but latest pre is identical.
        for run in (0, 1):
            self.set_frame_pixels(run, 2, (2, 3, 7))
        with self.assertRaisesRegex(ValueError, "no decoded raster change"):
            self.compare()

    def test_unchanged_post_candidate_capture_is_permitted(self):
        # This gate is deliberately scoped to pre-versus-first-candidate.
        # Later frames may legitimately be unchanged between observations.
        for run in (0, 1):
            self.set_frame_pixels(run, 2, (2, 3, 7))
        result = self.compare()
        self.assertEqual(result["paired_frames"], 3)
        self.assertFalse(result["scene_transition_authenticated"])

    def test_changed_pixel_even_with_updated_png_sha_is_rejected(self):
        _, _, root, records = self.runs[1]
        forged = tiny_png((255, 1, 1))
        (root / "synthetic-1.png").write_bytes(forged)
        records[1]["sha256"] = hashlib.sha256(forged).hexdigest()
        self.rewrite(1)
        with self.assertRaisesRegex(ValueError, "decoded PNG pixels differ"):
            self.compare()

    def test_changed_frame_marker_is_rejected(self):
        self.runs[1][3][1]["emulator_counter"] = 201
        self.runs[1][3][1]["movie_input_candidate"] = 200
        marker = self.runs[1][0]
        marker.write_text(marker.read_text().replace("counter=200 candidate_input=199", "counter=201 candidate_input=200"),
                          encoding="utf-8")
        self.rewrite(1)
        with self.assertRaisesRegex(ValueError, "unequal input-frame"):
            self.compare()

    def test_relabelled_scene_rejected_without_promoting_authenticity(self):
        self.runs[1][3][2]["label"] = "map02_candidate"
        self.rewrite(1)
        with self.assertRaisesRegex(ValueError, "unequal input-frame or scene labels"):
            self.compare()

    def test_reused_same_marker_log_rejected(self):
        a, b = self.runs
        with self.assertRaisesRegex(ValueError, "reuse one evidence source"):
            compare(self.inspection, a[0], a[1], a[2], a[0], b[1], b[2])

    def test_reused_same_image_directory_rejected(self):
        a, b = self.runs
        with self.assertRaisesRegex(ValueError, "reuse one evidence source"):
            compare(self.inspection, a[0], a[1], a[2], b[0], b[1], a[2])

    def test_missing_png_fails_closed(self):
        (self.runs[1][2] / "synthetic-2.png").unlink()
        with self.assertRaises((OSError, ValueError)):
            self.compare()

    def test_symlink_png_fails_closed(self):
        target = self.runs[1][2] / "synthetic-0.png"
        saved = target.with_suffix(".saved")
        target.rename(saved)
        target.symlink_to(saved)
        with self.assertRaises((OSError, ValueError)):
            self.compare()

    def test_corrupted_stream_even_with_manifest_digest_rejected(self):
        _, _, root, records = self.runs[1]
        data = (b"\x89PNG\r\n\x1a\n" +
                chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", b"not a valid zlib stream") +
                chunk(b"IEND", b""))
        (root / "synthetic-1.png").write_bytes(data)
        records[1]["sha256"] = hashlib.sha256(data).hexdigest()
        self.rewrite(1)
        with self.assertRaises(ValueError):
            self.compare()

    def test_reused_one_manifest_fails_closed(self):
        a, b = self.runs
        with self.assertRaisesRegex(ValueError, "reuse one evidence source"):
            compare(self.inspection, a[0], a[1], a[2], b[0], a[1], b[2])


if __name__ == "__main__":
    unittest.main()
