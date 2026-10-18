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
        (self.pc / "src/map02_fixture.h").write_text(
            "#define VH_TEST_GPU 7\n#define VH_TEST_RASTER 8\n")
        self.generated = {
            builder.GENERATED_MAKE: builder.make_overlay(self.output).encode(),
            builder.GENERATED_GPU: b'#include "map02_fixture.h"\nint vh_gpu_value(void){return VH_TEST_GPU;}\n',
            builder.GENERATED_RASTER: b'#include "map02_fixture.h"\nint vh_raster_value(void){return VH_TEST_RASTER;}\n',
        }
        for name, content in self.generated.items():
            (self.output / name).write_bytes(content)
        self.replay = {
            "generated_sha256": {name: hashlib.sha256(data).hexdigest()
                                 for name, data in self.generated.items()},
            "pinned_public_pc_commit": builder.PINNED_UPSTREAM_REF,
            "receipt_exactly_replayed": True,
        }
        self.tracked = {"platform/pc/src/map02_fixture.h":
                        builder.git_blob_sha1(
                            (self.pc / "src/map02_fixture.h").read_bytes())}
        real_blob = builder.git_blob_sha1
        self.original_git_blob_sha1 = real_blob
        patches = [
            patch.object(auditor, "replay", return_value=self.replay),
            patch.object(sealed, "_tracked_header_blobs", return_value=self.tracked),
            patch.object(builder, "git_blob_sha1", side_effect=lambda b:
                         builder.PINNED_BLOB_SHA1[builder.MAKE_REL]
                         if b == self.makefile else real_blob(b)),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def run_build(self, name="build-map02-sealed"):
        return sealed.compile_overlay(
            self.upstream, self.output, self.manifest, build_dir=name)

    def test_compiles_two_original_make_targets_using_sealed_inputs(self):
        result = self.run_build()
        self.assertEqual(result["sealed_inputs"], 7)
        self.assertEqual(result["pinned_headers_sealed"], 1)
        self.assertGreaterEqual(result["header_include_directory_watches"], 4)
        self.assertTrue(result["header_path_mutations_rejected"])
        self.assertEqual(set(result["compiler_tool_sha256"]), {"driver", "cc1", "as"})
        self.assertTrue(result["compiler_tools_before_after_match"])
        self.assertGreaterEqual(result["system_header_count"], 1)
        self.assertEqual(len(result["system_header_set_sha256"]), 64)
        self.assertTrue(result["system_header_bytes_before_after_match"])
        self.assertEqual(set(result["preprocessed_sha256"]), {"libgpu", "pc_raster"})
        self.assertEqual(result["pinned_headers_checked"], 1)
        self.assertTrue(result["staged_header_hashes_verified"])
        self.assertTrue(result["compiled_from_sealed_preprocessor_output"])
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

    def test_header_replacement_after_preprocessing_does_not_change_objects(self):
        real_run = subprocess.run
        header = self.pc / "src/map02_fixture.h"
        original = header.read_bytes()
        changed = []

        def inject(args, **kwargs):
            if "map02-private-gpu-objects" in args:
                header.write_text(
                    "#define VH_TEST_GPU 999\n#define VH_TEST_RASTER 999\n"
                    "#error modified-header-after-preprocessing\n")
                try:
                    result = real_run(args, **kwargs)
                finally:
                    header.write_bytes(original)
                changed.append(True)
                return result
            return real_run(args, **kwargs)

        with patch.object(sealed.subprocess, "run", side_effect=inject):
            self.run_build("build-map02-header-swap")
        self.assertEqual(changed, [True])
        for name, symbol in (("libgpu.o", "vh_gpu_value"),
                             ("pc_raster.o", "vh_raster_value")):
            obj = self.pc / "build-map02-header-swap" / name
            listing = subprocess.run(["nm", "--defined-only", str(obj)],
                                     capture_output=True, text=True, check=True)
            self.assertIn(symbol, listing.stdout)

    def test_preprocessor_failure_aborts_before_object_compilation(self):
        damaged = b"#error broken header\\n"
        (self.pc / "src/map02_fixture.h").write_bytes(damaged)
        self.tracked["platform/pc/src/map02_fixture.h"] = (
            self.original_git_blob_sha1(damaged))
        with self.assertRaisesRegex(ValueError, "sealed Make compilation failed"):
            self.run_build("build-map02-broken-header")
        self.assertFalse((self.pc / "build-map02-broken-header/libgpu.o").exists())

    def test_tracked_header_tamper_rejected_before_make(self):
        (self.pc / "src/map02_fixture.h").write_text("#define VH_TEST_GPU 999\n")
        actual_run = subprocess.run
        make_invoked = []
        def only_allow_compiler_queries(args, **kwargs):
            if ("map02-private-gpu-preprocess" in args
                    or "map02-private-gpu-dependencies" in args
                    or "map02-private-gpu-objects" in args):
                make_invoked.append(True)
                raise AssertionError("Make ran after a failed header audit")
            return actual_run(args, **kwargs)
        with patch.object(sealed.subprocess, "run",
                          side_effect=only_allow_compiler_queries):
            with self.assertRaisesRegex(ValueError, "header differs from Git blob"):
                self.run_build("build-map02-header-corrupt")
        self.assertFalse(make_invoked)

    def test_staged_header_mutation_is_refused(self):
        check = sealed._recheck_headers

        def damage(stage, digests, files):
            header = stage / "platform/pc/src/map02_fixture.h"
            header.unlink()
            header.write_text("#define VH_TEST_GPU 999\n")
            return check(stage, digests, files)

        with patch.object(sealed, "_recheck_headers", side_effect=damage):
            with self.assertRaisesRegex(ValueError, "staged header inventory changed"):
                self.run_build("build-map02-header-staged-tamper")

    def test_extra_header_in_snapshot_is_refused(self):
        check = sealed._recheck_headers

        def inject(stage, digests, files):
            (stage / "platform/pc/src/unrecorded.h").write_text(
                "#define SECRET_OVERRIDE 1\n")
            return check(stage, digests, files)

        with patch.object(sealed, "_recheck_headers", side_effect=inject):
            with self.assertRaisesRegex(ValueError, "header inventory changed"):
                self.run_build("build-map02-untracked-header")

    def test_symlinked_header_in_snapshot_is_refused(self):
        check = sealed._recheck_headers

        def inject(stage, digests, files):
            destination = stage / "platform/pc/src/unrecorded.h"
            destination.symlink_to(stage / "platform/pc/src/map02_fixture.h")
            return check(stage, digests, files)

        with patch.object(sealed, "_recheck_headers", side_effect=inject):
            with self.assertRaisesRegex(ValueError, "header inventory changed"):
                self.run_build("build-map02-symlink-header")

    def test_header_memfd_cannot_be_modified_before_preprocessing(self):
        actual_stage = sealed._stage_headers
        attempted = []

        def verify(upstream, stage, files, stack):
            result = actual_stage(upstream, stage, files, stack)
            path = stage / "platform/pc/src/map02_fixture.h"
            self.assertTrue(path.is_symlink())
            self.assertTrue(path.readlink().as_posix().startswith("/proc/self/fd/"))
            with self.assertRaises(OSError):
                path.write_bytes(b"#define VH_TEST_GPU 999\n")
            attempted.append(True)
            return result

        with patch.object(sealed, "_stage_headers", side_effect=verify):
            result = self.run_build("build-map02-immutable-header")
        self.assertEqual(attempted, [True])
        self.assertEqual(result["pinned_headers_sealed"], 1)

    def test_header_link_redirect_during_preprocessing_rejected(self):
        actual = sealed._recheck_headers

        def redirect(stage, digests, files):
            header = stage / "platform/pc/src/map02_fixture.h"
            header.unlink()
            header.symlink_to("/proc/self/fd/0")
            return actual(stage, digests, files)

        with patch.object(sealed, "_recheck_headers", side_effect=redirect):
            with self.assertRaisesRegex(ValueError, "header link redirected"):
                self.run_build("build-map02-header-redirect")

    def test_swapped_and_restored_header_link_during_preprocess_rejected(self):
        real_run = subprocess.run
        swapped = []

        def inject(args, **kwargs):
            if "map02-private-gpu-preprocess" in args:
                includes = next(x.split("=", 1)[1] for x in args
                                if x.startswith("VH_MAP02_PRIVATE_INCLUDE_FLAGS="))
                header = Path(includes.split(" -I")[1]) / "map02_fixture.h"
                original = header.readlink()
                header.unlink()
                header.symlink_to("/proc/self/fd/0")
                header.unlink()
                header.symlink_to(original)
                swapped.append(True)
            return real_run(args, **kwargs)

        with patch.object(sealed.subprocess, "run", side_effect=inject):
            with self.assertRaisesRegex(ValueError, "include paths changed"):
                self.run_build("build-map02-temporary-link")
        self.assertEqual(swapped, [True])
        self.assertFalse((self.pc / "build-map02-temporary-link/libgpu.o").exists())

    def test_added_and_removed_header_during_preprocess_rejected(self):
        real_run = subprocess.run
        changed = []

        def inject(args, **kwargs):
            if "map02-private-gpu-preprocess" in args:
                includes = next(x.split("=", 1)[1] for x in args
                                if x.startswith("VH_MAP02_PRIVATE_INCLUDE_FLAGS="))
                extra = Path(includes.split(" -I")[1]) / "undocumented.h"
                extra.write_bytes(b"#define ATTACK 1\\n")
                extra.unlink()
                changed.append(True)
            return real_run(args, **kwargs)

        with patch.object(sealed.subprocess, "run", side_effect=inject):
            with self.assertRaisesRegex(ValueError, "include paths changed"):
                self.run_build("build-map02-temporary-extra")
        self.assertEqual(changed, [True])
        self.assertFalse((self.pc / "build-map02-temporary-extra/libgpu.o").exists())

    def test_compiler_binary_fingerprint_mismatch_refused(self):
        original = sealed._compiler_evidence
        count = []

        def replace_second():
            driver, witness = original()
            count.append(True)
            if len(count) == 2:
                witness = dict(witness)
                witness["cc1"] = "0" * 64
            return driver, witness

        with patch.object(sealed, "_compiler_evidence", side_effect=replace_second):
            with self.assertRaisesRegex(ValueError, "compiler binaries changed"):
                self.run_build("build-map02-compiler-tamper")
        self.assertEqual(len(count), 2)

    def test_system_header_digest_mismatch_refused(self):
        original = sealed._system_header_evidence
        count = []

        def change_second(*args):
            result = original(*args)
            count.append(True)
            if len(count) == 2:
                result = dict(result)
                result["sha256"] = "0" * 64
            return result

        with patch.object(sealed, "_system_header_evidence", side_effect=change_second):
            with self.assertRaisesRegex(ValueError, "system header dependencies changed"):
                self.run_build("build-map02-system-header-tamper")
        self.assertEqual(len(count), 2)

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
