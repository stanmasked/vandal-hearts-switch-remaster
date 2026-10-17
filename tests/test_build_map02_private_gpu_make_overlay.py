"""Asset-free end-to-end checks of immutable C/Make input binding."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import build_map02_private_gpu_make_overlay as sealed
from tools import prepare_map02_private_gpu_make_overlay as builder
from tools import verify_map02_private_gpu_make_overlay as auditor


@unittest.skipUnless(sys.platform == "linux" and
                     shutil.which("make") and shutil.which("gcc"),
                     "Linux sealed memfd, GNU Make and GCC required")
class SealedMakeOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-sealed-make-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "public"
        self.pc = self.upstream / "platform" / "pc"
        (self.pc / "src").mkdir(parents=True)
        self.output = self.root / "overlay"
        self.output.mkdir()
        self.manifest = self.root / "receipt.json"
        self.manifest.write_text("{}")
        self.makefile = (
            "REGION ?= us\nBUILD_DIR ?= build\nCC := gcc\n"
            "M32 := -m64\nSAN :=\nPORT_WARN := -Wall\n"
            "$(BUILD_DIR)/libgpu.o: src/libgpu.c\n"
            "\t$(CC) -c -o $@ $<\n"
            "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c\n"
            "\t$(CC) -c -o $@ $<\n"
        ).encode()
        (self.pc / "Makefile").write_bytes(self.makefile)
        (self.pc / "src/libgpu.c").write_text("int old_gpu;\n")
        (self.pc / "src/pc_raster.c").write_text("int old_raster;\n")
        self.generated = {
            builder.GENERATED_MAKE: builder.make_overlay(self.output).encode(),
            builder.GENERATED_GPU: b"int vh_gpu_value(void){return 7;}\n",
            builder.GENERATED_RASTER: b"int vh_raster_value(void){return 8;}\n",
        }
        for name, content in self.generated.items():
            (self.output / name).write_bytes(content)
        self.replay = {
            "generated_sha256": {name: hashlib.sha256(data).hexdigest()
                                 for name, data in self.generated.items()},
            "pinned_public_pc_commit": builder.PINNED_UPSTREAM_REF,
            "receipt_exactly_replayed": True,
        }
        patches = [
            patch.object(auditor, "replay", return_value=self.replay),
            patch.object(builder, "git_blob_sha1",
                         return_value=builder.PINNED_BLOB_SHA1[builder.MAKE_REL]),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def run_build(self, name="build-map02-sealed"):
        return sealed.compile_overlay(
            self.upstream, self.output, self.manifest, build_dir=name)

    def test_compiles_two_original_make_targets_using_sealed_inputs(self):
        result = self.run_build()
        self.assertEqual(result["sealed_inputs"], 4)
        self.assertTrue(result["verified_source_bytes_used_for_compilation"])
        self.assertFalse(result["all_headers_sealed"])
        self.assertFalse(result["compiler_execution_attested"])
        self.assertFalse(result["hd_replacement_authorized"])
        self.assertEqual(set(result["objects_sha256"]), {"libgpu.o", "pc_raster.o"})
        for name, expected_symbol in (
            ("libgpu.o", "vh_gpu_value"), ("pc_raster.o", "vh_raster_value")):
            target = self.pc / "build-map02-sealed" / name
            self.assertTrue(target.stat().st_size > 0)
            symbols = subprocess.run(["nm", "--defined-only", str(target)],
                                     capture_output=True, text=True, check=True)
            self.assertIn(expected_symbol, symbols.stdout)
            self.assertNotIn("old_gpu", symbols.stdout)
            self.assertNotIn("old_raster", symbols.stdout)
        self.assertNotIn(str(self.upstream), str(result))
        self.assertNotIn(str(self.output), str(result))

    def test_modified_generated_source_is_refused_before_make(self):
        path = self.output / builder.GENERATED_GPU
        path.write_bytes(b"#error altered-before-sealing\n")
        with patch.object(sealed.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "changed before sealing"):
                self.run_build()
            run.assert_not_called()

    def test_changed_source_while_make_runs_compiles_sealed_snapshot(self):
        real_run = subprocess.run
        path = self.output / builder.GENERATED_GPU
        injected = []

        def inject(*args, **kwargs):
            original = path.read_bytes()
            path.write_bytes(b"#error source-was-replaced-after-sealing\n")
            try:
                completed = real_run(*args, **kwargs)
            finally:
                path.write_bytes(original)
            injected.append(True)
            return completed

        with patch.object(sealed.subprocess, "run", side_effect=inject):
            result = self.run_build("build-map02-swap")
        self.assertTrue(injected)
        self.assertEqual(len(result["objects_sha256"]), 2)

    def test_invalid_and_existing_build_directories_fail_closed(self):
        for name in ("build", "build-map02-", "build-map02-x/../y",
                     "build-map02-sneaky path"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "directory name invalid"):
                    self.run_build(name)
        (self.pc / "build-map02-existing").mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_build("build-map02-existing")

    def test_seals_prohibit_mutation_of_memfd(self):
        import fcntl
        import os
        fd = sealed._sealed_fd(b"immutable", "vh-test-seals")
        try:
            self.assertEqual(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & sealed.SEALS,
                             sealed.SEALS)
            with self.assertRaises(OSError):
                os.write(fd, b"attack")
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
