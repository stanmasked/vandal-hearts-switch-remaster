"""Asset-free MAP02 private capture readiness tests (structure, not provenance)."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.check_map02_private_capture_ready import inspect_staged_capture
from tools.verify_map02_frame_bundle import MAP_BYTES, PINNED_PC_SOURCE, VRAM_BYTES


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class PrivateCapturePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source, self.native = root / "source", root / "native"
        self.source.mkdir(mode=0o700)
        self.native.mkdir(mode=0o700)
        self.x, self.y, self.frame = 10, 20, 7
        self.offset = (self.y * 1024 + self.x) * 2
        before = bytearray(VRAM_BYTES)
        after = bytearray(VRAM_BYTES)
        before[self.offset:self.offset + 2] = (31).to_bytes(2, "little")
        after[self.offset:self.offset + 2] = (992).to_bytes(2, "little")
        (self.native / "gpu-0000-vram.bin").write_bytes(before)
        (self.native / "gpu-0001-vram.bin").write_bytes(after)
        self.decoded = bytes(MAP_BYTES)
        self.source_vram = bytes(VRAM_BYTES)
        self.events = encode({"stage": "map02_ft4_submit", "frame": 7})
        (self.source / "map02.decoded.bin").write_bytes(self.decoded)
        (self.source / "gpu-vram-le.bin").write_bytes(self.source_vram)
        (self.source / "gpu-events.jsonl").write_bytes(self.events)
        self.bundle = {
            "schema": "vh.map02.frame.v1",
            "frame": 7, "vram_snapshot_frame": 7,
            "ot_size": 64, "pc_source_commit": PINNED_PC_SOURCE,
            "decoded_map_sha256": digest(self.decoded),
            "vram_sha256": digest(self.source_vram),
            "events_sha256": digest(self.events),
        }
        self.source_file("bundle.json", self.bundle)
        a = {
            "stage": "native_vram", "step": 0, "frame": 7,
            "phase": "before", "operation": "draw",
            "snapshot": "gpu-0000-vram.bin", "rect": None,
            "dest": [0, 0], "rgb": [200, 0, 0],
            "primitive_type": 2, "semi": 1, "window": [0, 0, 0, 0],
            "draw_mode": [0, 0, 0], "upload": "",
            # Type 2 is POLY_FT4 in the source-pinned native recorder.
            # Include its complete packet metadata so the structural
            # preflight can reach the intended edge/receipt assertions.
            "ft4": {
                "tpage": 0, "clut": 0,
                "xy": [10, 20, 11, 20, 11, 21, 10, 21],
                "uv": [0, 0, 1, 0, 1, 1, 0, 1],
            },
        }
        b = dict(a, step=1, phase="after", snapshot="gpu-0001-vram.bin")
        self.native_events = encode(a) + encode(b)
        (self.native / "gpu-native-events.jsonl").write_bytes(self.native_events)
        self.receipt = {
            "schema": "vh.map02.native-capture-status.v1",
            "gpu_draw_frame": 7, "observed_hooks": 2,
            "before_hooks": 1, "after_hooks": 1,
            "draw_before_hooks": 1, "transfer_before_hooks": 0,
            "indexed_hooks": 2, "written_hooks": 2,
            "limit_reached": False, "walk_finished": True,
            "hooks_balanced": True,
            "observed_window_closed_without_detected_loss": True,
        }
        self.native_file("gpu-native-capture-status.json",
                         encode(self.receipt))
        self.pixel = {
            "stage": "native_putpixel", "step": 0, "frame": 7,
            "primitive_ordinal": 0, "primitive_type": 2,
            "x": 10, "y": 20, "before": 31, "front": 31744,
            "after": 992, "abr": 0, "semi": 1, "textured": 1,
            "accurate": 1,
        }
        self.blend = {
            "stage": "native_blendg1", "putpixel_step": 0,
            "frame": 7, "primitive_ordinal": 0, "primitive_type": 2,
            "x": 10, "y": 20, "accurate": 1, "abr": 0,
            "before": 31, "front": 31744, "after": 992,
            "blend_fg": 64512, "blend_bg": 31, "blend_result": 992,
        }
        self.edge = {
            "stage": "native_vram_edge", "frame": 7, "primitive_ordinal": 0,
            "primitive_type": 2, "x": 10, "y": 20,
            "before": 31, "after": 992,
        }
        self.pixel_raw = encode(self.pixel)
        self.blend_raw = encode(self.blend)
        self.edge_raw = encode(self.edge)
        self.native_file("putpixel-native-events.pending.jsonl", self.pixel_raw)
        self.native_file("blendg1-native-events.pending.jsonl", self.blend_raw)
        self.native_file("vram-edges-native-events.pending.jsonl", self.edge_raw)
        self.source_file("gpu-ot-order-join.json", {"test_fixture_only": True})
        self.overdraw = {
            "schema": "vh.map02.native-overdraw.v1",
            "source_frame": 7, "gpu_draw_frame": 7,
            "ot_order_manifest_sha256":
                digest((self.source / "gpu-ot-order-join.json").read_bytes()),
            "native_events_sha256": digest(self.native_events),
        }
        self.source_file("gpu-native-overdraw.json", self.overdraw)
        self.pixel_manifest = {
            "schema": "vh.map02.native-putpixel-ot.v1",
            "source_frame": 7, "gpu_draw_frame": 7,
            "overdraw_manifest_sha256":
                digest((self.source / "gpu-native-overdraw.json").read_bytes()),
            "native_events_sha256": digest(self.native_events),
            "putpixel_events_sha256": digest(self.pixel_raw),
        }
        self.source_file("gpu-putpixel-ot.json", self.pixel_manifest)

    def source_file(self, name, obj):
        (self.source / name).write_bytes(encode(obj))

    def native_file(self, name, raw):
        (self.native / name).write_bytes(raw)

    def run_preflight(self):
        return inspect_staged_capture(self.source, self.native)

    def test_accepts_structurally_coherent_private_input_without_authenticating_it(self):
        result = self.run_preflight()
        self.assertTrue(result["structural_preflight_passed"])
        self.assertTrue(result["native_capture_receipt_checked"])
        self.assertTrue(result["native_hook_loss_not_detected"])
        self.assertEqual(result["source_frame"], 7)
        self.assertEqual(result["native_draw_pairs"], 1)
        self.assertEqual(result["independently_sampled_draw_edges"], 1)
        self.assertEqual(result["verified_structure_blendg1_events"], 1)
        self.assertFalse(result["source_gte_ot_vram_fully_verified"])
        self.assertFalse(result["whole_gpu_frame_capture_proven"])
        self.assertFalse(result["original_gameplay_authenticated"])
        self.assertFalse(result["ps1_hardware_equivalence_proven"])

    def test_catches_pixel_snapshot_drift_even_when_logs_and_sha_agree(self):
        snapshot = self.native / "gpu-0001-vram.bin"
        raw = bytearray(snapshot.read_bytes())
        raw[self.offset:self.offset + 2] = (993).to_bytes(2, "little")
        snapshot.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.run_preflight()

    def test_rejects_missing_and_symlinked_snapshots(self):
        file = self.native / "gpu-0001-vram.bin"
        file.unlink()
        with self.assertRaises(ValueError):
            self.run_preflight()
        file.symlink_to(self.native / "gpu-0000-vram.bin")
        with self.assertRaises(ValueError):
            self.run_preflight()

    def test_catches_source_frame_and_provenance_drift(self):
        self.bundle["vram_snapshot_frame"] = 8
        self.source_file("bundle.json", self.bundle)
        with self.assertRaisesRegex(ValueError, "source VRAM"):
            self.run_preflight()
        self.bundle["vram_snapshot_frame"] = 7
        self.source_file("bundle.json", self.bundle)
        self.pixel_manifest["gpu_draw_frame"] = 8
        self.source_file("gpu-putpixel-ot.json", self.pixel_manifest)
        with self.assertRaises(ValueError):
            self.run_preflight()

    def test_detects_tampered_pixel_digest_and_partial_jsonl(self):
        self.native_file("putpixel-native-events.pending.jsonl", self.pixel_raw[:-1])
        with self.assertRaises(ValueError):
            self.run_preflight()
        self.native_file("putpixel-native-events.pending.jsonl", self.pixel_raw)
        self.native_file("vram-edges-native-events.pending.jsonl",
                         self.edge_raw[:-1])
        with self.assertRaises(ValueError):
            self.run_preflight()

    def test_rejects_an_unrepresented_draw_pair(self):
        a = json.loads(self.native_events.splitlines()[0])
        b = json.loads(self.native_events.splitlines()[1])
        a.update(step=2, snapshot="gpu-0002-vram.bin")
        b.update(step=3, snapshot="gpu-0003-vram.bin")
        newlog = self.native_events + encode(a) + encode(b)
        self.native_file("gpu-native-events.jsonl", newlog)
        self.pixel_manifest["native_events_sha256"] = digest(newlog)
        self.receipt.update(observed_hooks=4, before_hooks=2, after_hooks=2,
                            draw_before_hooks=2, indexed_hooks=4,
                            written_hooks=4)
        self.native_file("gpu-native-capture-status.json", encode(self.receipt))
        self.overdraw["native_events_sha256"] = digest(newlog)
        self.source_file("gpu-native-overdraw.json", self.overdraw)
        self.pixel_manifest["overdraw_manifest_sha256"] = digest(
            (self.source / "gpu-native-overdraw.json").read_bytes())
        self.source_file("gpu-putpixel-ot.json", self.pixel_manifest)
        with self.assertRaisesRegex(ValueError, "draw-pair count"):
            self.run_preflight()

    def test_rejects_duplicate_source_manifest_keys_or_game_hash_format(self):
        path = self.source / "bundle.json"
        path.write_bytes(path.read_bytes().replace(b'"frame":7',
                                                    b'"frame":7,"frame":7'))
        with self.assertRaises(ValueError):
            self.run_preflight()
        self.source_file("bundle.json", self.bundle)
        self.bundle["pc_game_binary_sha256"] = "NOT A REAL SHA"
        self.source_file("bundle.json", self.bundle)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.run_preflight()

    def test_requires_complete_terminal_receipt_without_hook_loss(self):
        (self.native / "gpu-native-capture-status.json").unlink()
        with self.assertRaises(ValueError):
            self.run_preflight()
        self.receipt["limit_reached"] = True
        self.receipt["observed_window_closed_without_detected_loss"] = False
        self.native_file("gpu-native-capture-status.json", encode(self.receipt))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.run_preflight()

    def test_refuses_world_readable_or_symlinked_capture_directories(self):
        os.chmod(self.native, 0o755)
        with self.assertRaises(ValueError):
            self.run_preflight()
        os.chmod(self.native, 0o700)
        link = self.native.parent / "alias"
        link.symlink_to(self.native, target_is_directory=True)
        with self.assertRaises(ValueError):
            inspect_staged_capture(self.source, link)


    def test_loadimage_requires_rect_and_forbids_inherited_ft4_packet(self):
        from tools.verify_map02_native_gpu_capture import validate_meta
        draw = json.loads(self.native_events.splitlines()[0])
        self.assertIsNotNone(draw["ft4"])
        transfer = dict(draw, operation="load", primitive_type=0,
                        frame=self.frame - 1,
                        rect=[0, 0, 1, 1], semi=0, upload="")
        with self.assertRaisesRegex(ValueError, "transfer requires RECT"):
            validate_meta(transfer, 0, self.frame)
        transfer["ft4"] = None
        validate_meta(transfer, 0, self.frame)

    def test_requires_transfer_snapshots_and_declared_upload_bytes(self):
        (self.native / "gpu-0000-vram.bin").rename(
            self.native / "gpu-0002-vram.bin")
        (self.native / "gpu-0001-vram.bin").rename(
            self.native / "gpu-0003-vram.bin")
        draw0, draw1 = (json.loads(x) for x in self.native_events.splitlines())
        draw0.update(step=2, snapshot="gpu-0002-vram.bin")
        draw1.update(step=3, snapshot="gpu-0003-vram.bin")
        move0 = dict(draw0, step=0, frame=6, phase="before",
                     operation="load", snapshot="gpu-0000-vram.bin",
                     rect=[0, 0, 1, 1], primitive_type=0, semi=0,
                     ft4=None, upload="")
        move1 = dict(move0, step=1, phase="after",
                     snapshot="gpu-0001-vram.bin", upload="gpu-0001-upload.bin")
        self.native_file("gpu-0000-vram.bin", bytes(VRAM_BYTES))
        self.native_file("gpu-0001-vram.bin", bytes(VRAM_BYTES))
        self.native_file("gpu-0001-upload.bin", b"\x01\x00")
        staged = b"".join(map(encode, (move0, move1, draw0, draw1)))
        self.native_file("gpu-native-events.jsonl", staged)
        self.overdraw["native_events_sha256"] = digest(staged)
        self.receipt.update(observed_hooks=4, before_hooks=2, after_hooks=2,
                            transfer_before_hooks=1, draw_before_hooks=1,
                            indexed_hooks=4, written_hooks=4)
        self.native_file("gpu-native-capture-status.json", encode(self.receipt))
        self.source_file("gpu-native-overdraw.json", self.overdraw)
        self.pixel_manifest["native_events_sha256"] = digest(staged)
        self.pixel_manifest["overdraw_manifest_sha256"] = digest(
            (self.source / "gpu-native-overdraw.json").read_bytes())
        self.source_file("gpu-putpixel-ot.json", self.pixel_manifest)
        self.assertTrue(self.run_preflight()["structural_preflight_passed"])
        (self.native / "gpu-0001-vram.bin").unlink()
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.run_preflight()
        self.native_file("gpu-0001-vram.bin", bytes(VRAM_BYTES))
        (self.native / "gpu-0001-upload.bin").unlink()
        with self.assertRaises(ValueError):
            self.run_preflight()

    def test_rejects_source_submissions_more_numerous_than_draws(self):
        events = self.events + self.events
        self.source_file("gpu-native-overdraw.json", self.overdraw)
        (self.source / "gpu-events.jsonl").write_bytes(events)
        self.bundle["events_sha256"] = digest(events)
        self.source_file("bundle.json", self.bundle)
        with self.assertRaisesRegex(ValueError, "exceed captured native draws"):
            self.run_preflight()

    def test_never_creates_a_manifest_or_promotes_pending_logs(self):
        before_source = set(self.source.iterdir())
        before_native = set(self.native.iterdir())
        self.run_preflight()
        self.assertEqual(set(self.source.iterdir()), before_source)
        self.assertEqual(set(self.native.iterdir()), before_native)


if __name__ == "__main__":
    unittest.main()
