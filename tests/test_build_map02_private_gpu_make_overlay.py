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
        self.assertGreaterEqual(result["compiler_shared_object_count"], 1)
        self.assertEqual(len(result["compiler_shared_object_set_sha256"]), 64)
        self.assertTrue(result["compiler_shared_objects_before_after_match"])
        self.assertTrue(all(result["compiler_runtime_processes_seen"][role] >= 1
                            for role in ("driver", "cc1", "as")))
        self.assertGreaterEqual(result["compiler_runtime_loaded_object_count"], 1)
        self.assertEqual(len(result["compiler_runtime_loaded_object_set_sha256"]), 64)
        self.assertTrue(result["compiler_runtime_mappings_correlated_to_resolved_files"])
        self.assertEqual(result["kernel_tool_exec_witnesses"], 6)
        self.assertTrue(result["kernel_tool_exec_images_match_sha256"])
        self.assertTrue(result["actual_make_children_kernel_attested"])
        self.assertTrue(all(result["kernel_make_primary_children_seen"][role] >= 1
                            for role in ("driver", "cc1", "as")))
        self.assertTrue(result["kernel_make_primary_executables_match_sha256"])
        self.assertGreaterEqual(result["kernel_make_primary_mapped_library_count"], 1)
        self.assertEqual(len(result["kernel_make_primary_mapped_library_set_sha256"]), 64)
        self.assertTrue(all(result["kernel_make_primary_mapped_library_roles"][role] >= 1
                            for role in ("driver", "cc1", "as")))
        self.assertTrue(result["kernel_make_primary_mapped_libraries_match_sha256"])
        self.assertFalse(result["separate_make_object_replay_performed"])
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
        real_trace = sealed.kernel_witness.trace_make_children
        header = self.pc / "src/map02_fixture.h"
        original = header.read_bytes()
        changed = []

        def inject(*args, **kwargs):
            header.write_text(
                "#define VH_TEST_GPU 999\n#define VH_TEST_RASTER 999\n"
                "#error modified-header-after-preprocessing\n")
            try:
                result = real_trace(*args, **kwargs)
            finally:
                header.write_bytes(original)
            changed.append(True)
            return result

        with patch.object(sealed.kernel_witness, "trace_make_children",
                          side_effect=inject):
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

    def test_compiler_shared_object_digest_mismatch_refused(self):
        original = sealed._compiler_dynamic_evidence
        invocations = []

        def alter_second(*args):
            result = original(*args)
            invocations.append(True)
            if len(invocations) == 2:
                result = dict(result)
                result["sha256"] = "0" * 64
            return result

        with patch.object(sealed, "_compiler_dynamic_evidence", side_effect=alter_second):
            with self.assertRaisesRegex(ValueError, "shared objects changed"):
                self.run_build("build-map02-shared-objects-changed")
        self.assertEqual(invocations, [True, True])

    def test_missing_shared_library_refuses_inventory(self):
        real_run = subprocess.run

        def fake_ldd(args, **kwargs):
            if args and str(args[0]).endswith("/ldd"):
                return subprocess.CompletedProcess(
                    args, 0, stdout="libmissing.so => not found\\n", stderr="")
            return real_run(args, **kwargs)

        driver = shutil.which("cc", path="/usr/bin:/bin")
        with patch.object(sealed.subprocess, "run", side_effect=fake_ldd):
            with self.assertRaisesRegex(ValueError, "shared-object record malformed"):
                sealed._compiler_dynamic_evidence(driver)

    def test_runtime_loader_refuses_pid_mismatch_despite_valid_libraries(self):
        witness = self.root / "runtime-foreign-pid"
        witness.mkdir()
        library = self.root / "known-library.so"
        library.write_bytes(b"known contents")
        (witness / "trace.123").write_text(
            "456: initialize program: /usr/bin/gcc\n"
            "456: calling init: " + str(library) + "\n")
        with self.assertRaisesRegex(ValueError, "loader PID mismatch"):
            sealed._runtime_loader_evidence(
                witness, "/usr/bin/gcc", {
                    str(library): hashlib.sha256(library.read_bytes()).hexdigest()})

    def test_runtime_loader_refuses_spoofed_cc1_basename(self):
        witness = self.root / "runtime-wrong-cc1"
        witness.mkdir()
        tools = self.root / "other-tools"
        tools.mkdir()
        foreign = tools / "cc1"
        foreign.write_bytes(b"untrusted executable")
        library = self.root / "runtime-good-library.so"
        library.write_bytes(b"known contents")
        (witness / "trace.321").write_text(
            "321: initialize program: " + str(foreign) + "\n"
            "321: calling init: " + str(library) + "\n")
        with self.assertRaisesRegex(ValueError, "executable identity mismatch"):
            sealed._runtime_loader_evidence(
                witness, "/usr/bin/gcc", {
                    str(library): hashlib.sha256(library.read_bytes()).hexdigest()},
                {"driver": "/usr/bin/gcc", "cc1": "/usr/bin/gcc",
                 "as": "/usr/bin/as"})

    def test_runtime_loader_accepts_relative_assembler_with_restricted_path(self):
        witness = self.root / "runtime-relative-as"
        witness.mkdir()
        lib = self.root / "mapped-fixture.so"
        lib.write_bytes(b"test library")
        executable = self.root / "cc1"
        executable.write_bytes(b"known compiler")
        for pid, name in ((111, "/usr/bin/gcc"),
                          (222, str(executable)), (333, "as")):
            (witness / ("trace." + str(pid))).write_text(
                str(pid) + ": initialize program: " + name + "\n"
                + str(pid) + ": calling init: " + str(lib) + "\n")
        result = sealed._runtime_loader_evidence(
            witness, "/usr/bin/gcc",
            {str(lib): hashlib.sha256(lib.read_bytes()).hexdigest()},
            {"driver": "/usr/bin/gcc", "cc1": str(executable),
             "as": shutil.which("as", path="/usr/bin:/bin")})
        self.assertEqual(result["processes"],
                         {"driver": 1, "cc1": 1, "as": 1})

    def test_runtime_loader_refuses_missing_assembler_process(self):
        witness = self.root / "runtime-missing-as"
        witness.mkdir()
        library = self.root / "synthetic-system.so"
        library.write_bytes(b"test library")
        (witness / "trace.123").write_text(
            "123: initialize program: /usr/bin/gcc\n"
            "123: calling init: " + str(library) + "\n")
        with self.assertRaisesRegex(ValueError, "process witness missing"):
            sealed._runtime_loader_evidence(
                witness, "/usr/bin/gcc", {
                    str(library): hashlib.sha256(library.read_bytes()).hexdigest()})

    def test_runtime_loader_refuses_unrecognized_mapped_library(self):
        witness = self.root / "runtime-extra-library"
        witness.mkdir()
        foreign = self.root / "unexpected-runtime-library.so"
        foreign.write_bytes(b"external library")
        (witness / "trace.123").write_text(
            "123: initialize program: /usr/bin/gcc\n"
            "123: calling init: " + str(foreign) + "\n")
        with self.assertRaisesRegex(ValueError, "unrecognized shared object"):
            sealed._runtime_loader_evidence(witness, "/usr/bin/gcc", {})

    def test_runtime_loader_refuses_changed_mapped_library_bytes(self):
        witness = self.root / "runtime-modified-library"
        witness.mkdir()
        library = self.root / "tampered-runtime-library.so"
        library.write_bytes(b"before")
        expected = hashlib.sha256(library.read_bytes()).hexdigest()
        library.write_bytes(b"after")
        (witness / "trace.321").write_text(
            "321: initialize program: /usr/bin/gcc\n"
            "321: calling init: " + str(library) + "\n")
        with self.assertRaisesRegex(ValueError, "shared-object hash mismatch"):
            sealed._runtime_loader_evidence(
                witness, "/usr/bin/gcc", {str(library): expected})

    def test_runtime_loader_refuses_ambiguous_process_identity(self):
        witness = self.root / "runtime-ambiguous-process"
        witness.mkdir()
        (witness / "trace.321").write_text(
            "321: initialize program: /usr/bin/gcc\n"
            "321: initialize program: /usr/bin/as\n")
        with self.assertRaisesRegex(ValueError, "program identity ambiguous"):
            sealed._runtime_loader_evidence(witness, "/usr/bin/gcc", {})

    def test_runtime_loader_refuses_non_numeric_trace_filename(self):
        witness = self.root / "runtime-invalid-log"
        witness.mkdir()
        (witness / "trace.injected").write_text(
            "321: initialize program: /usr/bin/gcc\n")
        with self.assertRaisesRegex(ValueError, "log name invalid"):
            sealed._runtime_loader_evidence(witness, "/usr/bin/gcc", {})

    def test_kernel_mapped_library_accepts_real_linux_inode(self):
        from tools.map02_kernel_make_witness import _mapped_shared_objects
        import os
        library = next((Path(x) for x in
                        sealed._compiler_dynamic_evidence(
                            sealed._compiler_evidence()[0])["_resolved_files"]
                        if ".so" in Path(x).name), None)
        self.assertIsNotNone(library)
        st = library.stat()
        digest = hashlib.sha256(library.read_bytes()).hexdigest()
        text = ("7ff00000-7ff10000 r-xp 00000000 "
                + format(os.major(st.st_dev), "02x") + ":"
                + format(os.minor(st.st_dev), "02x") + " "
                + str(st.st_ino) + " " + str(library) + "\\n")
        self.assertEqual(_mapped_shared_objects(text, {str(library): digest}),
                         {str(library): digest})

    def test_kernel_mapped_library_refuses_digest_mismatch(self):
        from tools.map02_kernel_make_witness import _mapped_shared_objects
        import os
        library = next((Path(x) for x in
                        sealed._compiler_dynamic_evidence(
                            sealed._compiler_evidence()[0])["_resolved_files"]
                        if ".so" in Path(x).name), None)
        self.assertIsNotNone(library)
        st = library.stat()
        text = ("7ff00000-7ff10000 r-xp 00000000 "
                + format(os.major(st.st_dev), "02x") + ":"
                + format(os.minor(st.st_dev), "02x") + " "
                + str(st.st_ino) + " " + str(library) + "\\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            _mapped_shared_objects(text, {str(library): "0" * 64})

    def test_kernel_mapped_library_refuses_wrong_inode(self):
        from tools.map02_kernel_make_witness import _mapped_shared_objects
        import os
        library = next((Path(x) for x in
                        sealed._compiler_dynamic_evidence(
                            sealed._compiler_evidence()[0])["_resolved_files"]
                        if ".so" in Path(x).name), None)
        self.assertIsNotNone(library)
        st = library.stat()
        text = ("7ff00000-7ff10000 r-xp 00000000 "
                + format(os.major(st.st_dev), "02x") + ":"
                + format(os.minor(st.st_dev), "02x") + " "
                + str(st.st_ino + 1) + " " + str(library) + "\\n")
        with self.assertRaisesRegex(ValueError, "inode mismatch"):
            _mapped_shared_objects(
                text, {str(library): hashlib.sha256(library.read_bytes()).hexdigest()})

    def test_primary_make_is_traced_not_run_through_untraced_subprocess(self):
        actual = sealed.subprocess.run
        forbidden = []

        def checked_run(args, **kwargs):
            if "map02-private-gpu-objects" in args:
                forbidden.append(True)
                raise AssertionError("An untraced object compilation was attempted")
            return actual(args, **kwargs)

        with patch.object(sealed.subprocess, "run", side_effect=checked_run):
            report = self.run_build("build-map02-traced-primary-only")
        self.assertFalse(forbidden)
        self.assertTrue(report["actual_make_children_kernel_attested"])
        self.assertFalse((self.pc / "build-map02-traced-primary-only-kernel-witness").exists())

    def test_kernel_exec_image_matches_selected_gcc(self):
        driver, hashes = sealed._compiler_evidence()
        self.assertEqual(sealed._kernel_exec_image_digest(driver), hashes["driver"])

    def test_kernel_toolchain_refuses_wrong_executable_digest(self):
        driver, hashes = sealed._compiler_evidence()
        mismatched = dict(hashes)
        mismatched["driver"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "kernel compiler executable hash mismatch"):
            sealed._kernel_toolchain_evidence(
                {"driver": driver, "cc1": driver, "as": driver}, mismatched)

    def test_traced_real_make_child_inodes_and_hashes(self):
        from tools.map02_kernel_make_witness import trace_make_children
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Makefile").write_text(
                "all:\n\tcc -c -o child.o child.c\n")
            (root / "child.c").write_text("int child(void) { return 7; }\n")
            compiler, digests = sealed._compiler_evidence()
            inventory = sealed._compiler_dynamic_evidence(compiler)
            counts = trace_make_children(
                ["/usr/bin/make", "all"], cwd=root,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                pass_fds=(), tools=inventory["_resolved_tools"],
                hashes=digests, timeout=30)
            self.assertTrue((root / "child.o").is_file())
            self.assertTrue(all(counts[name] >= 1 for name in ("driver", "cc1", "as")))

    def test_traced_make_child_rejects_incorrect_kernel_digest(self):
        from tools.map02_kernel_make_witness import trace_make_children
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Makefile").write_text(
                "all:\n\tcc -c -o child.o child.c\n")
            (root / "child.c").write_text("int child(void) { return 7; }\n")
            compiler, digests = sealed._compiler_evidence()
            inventory = sealed._compiler_dynamic_evidence(compiler)
            digests["cc1"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "executable hash mismatch"):
                trace_make_children(
                    ["/usr/bin/make", "all"], cwd=root,
                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                    pass_fds=(), tools=inventory["_resolved_tools"],
                    hashes=digests, timeout=30)

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

    def test_system_header_line_markers_from_preprocessed_bytes(self):
        system = self.root / "external-system.h"
        system.write_text("#define HOST_VALUE 9\n")
        preprocessed = self.root / "sample.i"
        preprocessed.write_text(
            '# 0 "<built-in>"\n'
            '# 1 "' + str(self.pc) + '//"\n'
            '# 1 "' + str(system) + '" 1 3 4\n'
            'int x;\n')
        evidence = sealed._system_header_evidence(
            (preprocessed,), self.pc, self.root / "private-headers")
        self.assertEqual(evidence["count"], 1)
        self.assertEqual(len(evidence["sha256"]), 64)

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
