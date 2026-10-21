"""Invented PNG pixels and marker counters; no game data or real scenes."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.verify_map02_private_visual_candidates import verify, png_header_and_crc


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def invented_png(rgb):
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
            chunk(b"IDAT", zlib.compress(bytes((0,)) + bytes(rgb))) +
            chunk(b"IEND", b""))


class PrivateVisualCandidateTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.pictures = self.root / "private-shots"
        self.pictures.mkdir()
        self.inspection = self.root / "inspection.json"
        self.markers = self.root / "markers.txt"
        self.manifest = self.root / "manifest.json"
        self.inspection.write_text(json.dumps({
            "schema": "vh.psx.bizhawk.private-bk2-input-inspection.v1",
            "game": "Vandal Hearts (USA)", "platform": "PSX", "core": "Octoshock",
            "input_log_frame_count": 3000,
            "original_ps1_game_image_authenticated": False,
            "map02_scene_frame_identified": False,
        }), encoding="utf-8")
        self.markers.write_text("other private log\n" + "\n".join(
            f"VH_PRIVATE_REPLAY_MARKER counter={x} candidate_input={x-1} mode=PLAY scene=unverified"
            for x in (100, 200, 300)) + "\n", encoding="utf-8")
        self.images = [invented_png((x, 0, 0)) for x in (0, 1, 2)]
        self.shots = [self.observation(i, n, label) for i, (n, label) in enumerate([
            (100, "pre_map02"), (200, "map02_candidate"), (300, "post_map02")])]
        self.save_manifest()

    def observation(self, i, counter, label):
        name = f"synthetic-{i}.png"
        image = self.images[i]
        (self.pictures / name).write_bytes(image)
        return {"emulator_counter": counter, "movie_input_candidate": counter - 1,
                "label": label, "png_file": name, "sha256": hashlib.sha256(image).hexdigest()}

    def save_manifest(self):
        self.manifest.write_text(json.dumps({
            "schema": "vh.map02.private-visual-candidates.v1",
            "observations": self.shots,
        }), encoding="utf-8")

    def call(self):
        return verify(self.inspection, self.markers, self.manifest, self.pictures)

    def test_three_consistent_synthetic_screenshots(self):
        result = self.call()
        self.assertEqual(result["integrity_checked_png_count"], 3)
        self.assertEqual(result["manual_candidate_interval_counter_exclusive_inclusive"], [100, 200])
        self.assertTrue(result["png_envelopes_crcs_sha256_match"])
        for key in ("visual_scene_content_authenticated", "original_ps1_game_authenticated",
                    "input_to_emulator_video_alignment_verified", "map02_scene_frame_identified",
                    "ps1_gpu_vram_captured", "private_screenshots_uploaded"):
            self.assertFalse(result[key])
        self.assertNotIn("synthetic-", str(result))

    def test_png_check_rejects_corrupted_crc(self):
        corrupted = bytearray(self.images[0])
        corrupted[22] ^= 1
        with self.assertRaises(ValueError):
            png_header_and_crc(bytes(corrupted))

    def test_png_check_rejects_missing_iend(self):
        with self.assertRaises(ValueError):
            png_header_and_crc(self.images[0][:-12])

    def test_changed_image_hash_refused(self):
        (self.pictures / self.shots[1]["png_file"]).write_bytes(invented_png((7, 8, 9)))
        with self.assertRaises(ValueError):
            self.call()

    def test_manual_scene_label_does_not_upgrade_provenance(self):
        self.shots[-1]["label"] = "map02_candidate"
        self.save_manifest()
        self.assertFalse(self.call()["map02_scene_frame_identified"])

    def test_reject_wrong_frame_candidate(self):
        self.shots[1]["movie_input_candidate"] = 201
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_unrecorded_counter(self):
        self.shots[1]["emulator_counter"] = 205
        self.shots[1]["movie_input_candidate"] = 204
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_unsorted_screenshot_counters(self):
        self.shots[1], self.shots[2] = self.shots[2], self.shots[1]
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_missing_before_scene(self):
        self.shots[0]["label"] = "map02_candidate"
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_traversal_image_filename(self):
        self.shots[1]["png_file"] = "../secret.png"
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_symlink_image(self):
        image = self.pictures / self.shots[1]["png_file"]
        backup = self.root / "backing.png"
        backup.write_bytes(image.read_bytes())
        image.unlink()
        image.symlink_to(backup)
        with self.assertRaises((ValueError, OSError)):
            self.call()

    def test_reject_modified_marker(self):
        self.markers.write_text(self.markers.read_text().replace("counter=200", "counter=201"))
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_duplicate_image_name(self):
        self.shots[2]["png_file"] = self.shots[1]["png_file"]
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.call()

    def test_reject_unsupported_manifest_field(self):
        self.manifest.write_text(json.dumps({"schema": "vh.map02.private-visual-candidates.v1",
                                              "observations": self.shots,
                                              "authenticated": True}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call()


if __name__ == "__main__":
    unittest.main()
