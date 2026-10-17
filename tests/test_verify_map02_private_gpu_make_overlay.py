"""Asset-free independent replay of the privately generated pinned Make overlay."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_map02_private_gpu_make_overlay as builder
from tools import verify_map02_private_gpu_make_overlay as auditor


class PrivateOverlayReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-make-replay-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "public"
        self.upstream.mkdir()
        self.output = self.root / "private-overlay"
        self.receipt = self.root / "private-receipt.json"
        make = ("\n".join(builder.REQUIRED_MAKE_ANCHORS) +
                "\nBACKEND_SRCS := libgpu.c pc_raster.c\n"
                "default: $(GAME_O_FILES) $(BACKEND_OBJS)\n"
                "objs: default $(DATA_OBJS)\n"
                "link: $(DATA_OBJS)\n"
                "\t$(CC) $(GAME_O_FILES) $(BACKEND_OBJS) $(DATA_OBJS)\n"
                "$(BUILD_DIR)/libgpu.o: src/libgpu.c\n"
                "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c\n").encode()
        self.samples = {
            builder.MAKE_REL: make,
            builder.GPU_REL: b"PINNED-GPU-SOURCE",
            builder.RASTER_REL: b"PINNED-RASTER-SOURCE",
        }
        for path, payload in self.samples.items():
            file = self.upstream / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(payload)
        self.hashes = {
            self.samples[builder.MAKE_REL]: builder.PINNED_BLOB_SHA1[builder.MAKE_REL],
            self.samples[builder.GPU_REL]: builder.GPU_BLOB,
            self.samples[builder.RASTER_REL]: builder.RASTER_BLOB,
        }
        stack = [
            patch.object(builder, "_require_pinned_clean_checkout"),
            patch.object(builder, "git_blob_sha1", side_effect=lambda b: self.hashes[b]
                         if b in self.hashes else "corrupt"),
            patch.object(builder, "multi_gpu", side_effect=lambda s: "GPU[" + s + "]"),
            patch.object(builder, "multi_raster", side_effect=lambda s: "R[" + s + "]"),
            patch.object(builder, "instrument_raster_skips", side_effect=lambda s: "S[" + s + "]"),
            patch.object(builder, "instrument_vertical", side_effect=lambda s: "V[" + s + "]"),
            patch.object(builder, "instrument_span", side_effect=lambda s: "D[" + s + "]"),
        ]
        for mock in stack:
            mock.start()
            self.addCleanup(mock.stop)
        original = builder.prepare(self.upstream, self.output)
        self.receipt.write_text(json.dumps(original), encoding="utf-8")

    def check(self):
        return auditor.replay(self.upstream, self.output, self.receipt)

    def test_replays_exact_pinned_generated_sources_and_manifest(self):
        result = self.check()
        self.assertTrue(result["receipt_exactly_replayed"])
        self.assertEqual(result["generated_files_checked"], 3)
        self.assertTrue(result["full_checkout_head_verified"])
        self.assertTrue(result["full_tracked_checkout_clean"])
        for key in ("private_game_assets_read", "private_game_executable_built",
                    "retail_map02_gameplay_captured",
                    "native_process_to_gpu_log_causality_verified",
                    "hd_replacement_authorized"):
            self.assertFalse(result[key])
        serialized = json.dumps(result)
        self.assertNotIn(str(self.upstream), serialized)
        self.assertNotIn(str(self.output), serialized)

    def test_modified_generated_raster_and_make_both_rejected(self):
        for name in (builder.GENERATED_GPU, builder.GENERATED_RASTER,
                     builder.GENERATED_MAKE):
            with self.subTest(name=name):
                target = self.output / name
                original = target.read_bytes()
                target.write_bytes(original + b"# malicious edit\n")
                with self.assertRaisesRegex(ValueError, "generated file differs"):
                    self.check()
                target.write_bytes(original)
        self.assertTrue(self.check()["receipt_exactly_replayed"])

    def test_wrong_manifest_hash_and_duplicate_json_keys_rejected(self):
        original = self.receipt.read_bytes()
        bad = json.loads(original)
        bad["generated_sha256"][builder.GENERATED_GPU] = "0" * 64
        self.receipt.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            self.check()
        self.receipt.write_bytes(b'{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            self.check()
        self.receipt.write_bytes(original)

    def test_symlinked_generated_file_is_not_accepted(self):
        target = self.output / builder.GENERATED_GPU
        original = target.read_bytes()
        target.unlink()
        alternate = self.root / "another-gpu"
        alternate.write_bytes(original)
        target.symlink_to(alternate)
        with self.assertRaises((ValueError, OSError)):
            self.check()

    def test_extra_output_file_or_receipt_in_output_rejected(self):
        extra = self.output / "unrecorded-file"
        extra.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "output files differ"):
            self.check()
        extra.unlink()
        with self.assertRaisesRegex(ValueError, "receipt must live outside"):
            auditor.replay(self.upstream, self.output, self.output / "receipt.json")

    def test_changed_pinned_full_source_rejected_even_if_manifest_same(self):
        source = self.upstream / builder.GPU_REL
        source.write_bytes(b"modified original PC source")
        with self.assertRaisesRegex(ValueError, "pinned Git blob"):
            self.check()

    def test_dirty_checkout_check_blocks_replay(self):
        with patch.object(builder, "_require_pinned_clean_checkout",
                          side_effect=ValueError("pinned public PC tracked source files modified")):
            with self.assertRaisesRegex(ValueError, "tracked source"):
                self.check()


if __name__ == "__main__":
    unittest.main()
