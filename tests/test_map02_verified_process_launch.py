"""Real Linux child-executable observation tests; synthetic executable/assets.

Only the subsequent original GPU witness verification is mocked in this unit
fixture. We actually compile a native ELF and read /proc/<child>/exe to
prove the OS launches the prepared executable instead of a claimed pathname.
"""
import json
import os
import io
from contextlib import redirect_stderr
from pathlib import Path
import tools.map02_verified_process_launch as launcher
import subprocess
import shutil
import unittest
from unittest.mock import patch

from tests.test_map02_local_capture_handoff import LocalMap02CaptureHandoffTests
from tools.map02_verified_process_launch import (
    RECEIPT, launch_observed_pc, verify_observed_process,
    _validate_receipt,
)


class VerifiedProcessLaunchTests(unittest.TestCase):
    def setUp(self):
        fixture = LocalMap02CaptureHandoffTests(
            methodName="test_prelaunch_plan_and_verified_handoff_are_private_and_bound")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.handoff = fixture.handoff
        self.binary = fixture.binary
        self.owned = fixture.game
        self.upstream = fixture.upstream
        self.native = fixture.windows
        self.scoped = fixture.scoped
        code = """#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    FILE *disc;
    (void)argv;
    if (argc > 1) return 2;
    if (getenv("VH_TEST_SKIP_DISC_FD")) { sleep(1); return 0; }
    disc = fopen(getenv("VH_DISC_IMAGE"), "rb");
    if (!disc) return 3;
    if (fgetc(disc) != 'f') { fclose(disc); return 5; }
    sleep(1); /* real procfs inspection requires a live descriptor */
    if (fclose(disc) != 0) return 4;
    return 0;
}
"""
        source = self.binary.with_suffix(".c")
        source.write_text(code)
        subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        str(source), "-o", str(self.binary)],
                       check=True, capture_output=True, text=True)
        self.binary.chmod(0o700)
        self.checked = {
            "capture_session_linked": True,
            "capture_session_sha256": "b" * 64,
            "all_native_window_file_bytes_sha256": "c" * 64,
            "global_draw_ordinals_checked": 2,
        }
        self.join_patch = patch(
            "tools.map02_verified_process_launch.verify_window_scoped_join",
            return_value=self.checked)
        self.join = self.join_patch.start()
        self.addCleanup(self.join_patch.stop)
        fixture.prepare()

    def run_capture(self, *args):
        return launch_observed_pc(
            self.handoff, self.native, self.scoped, self.binary,
            self.owned, upstream=self.upstream,
            x=10, y=20, timeout=8, arguments=args)

    def audit(self):
        return verify_observed_process(
            self.handoff, self.native, self.scoped, self.binary,
            self.owned, upstream=self.upstream)

    def test_launcher_cli_withholds_private_path_from_native_failures(self):
        private_path = str(self.binary)
        args = [
            "map02-process", "run", str(self.handoff), str(self.native),
            str(self.scoped), "--pc-binary", private_path,
            "--owned-game-image", str(self.owned),
            "--upstream-checkout", str(self.upstream),
            "--x", "10", "--y", "20",
        ]
        for error in (
                OSError("cannot open private ELF " + private_path),
                subprocess.TimeoutExpired(
                    [private_path, "run"], 30,
                    output=("private " + private_path).encode())):
            with self.subTest(fault=type(error).__name__):
                output = io.StringIO()
                with (patch("sys.argv", args),
                      patch.object(launcher, "launch_observed_pc",
                                   side_effect=error),
                      redirect_stderr(output)):
                    with self.assertRaises(SystemExit) as caught:
                        launcher.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("execution unavailable", output.getvalue())
                self.assertNotIn(private_path, output.getvalue())

    def test_genuine_child_elf_checked_against_prepared_binary(self):
        result = self.run_capture()
        self.assertTrue(result["kernel_executable_hash_matched"])
        self.assertTrue(result["game_image_fd_observed"])
        self.assertFalse(result["game_image_consumption_proven"])
        self.assertFalse(result["original_gameplay_authenticated"])
        receipt = self.handoff / RECEIPT
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        data = json.loads(receipt.read_bytes())
        self.assertEqual(data["kernel_observed_executable_sha256"],
                         json.loads((self.handoff /
                                     "gpu-local-capture-plan.json").read_bytes())[
                                         "pc_executable_sha256"])
        self.assertEqual(data["capture_session_sha256"], "b" * 64)
        self.assertTrue(data["game_image_fd_observed"])
        self.assertEqual(data["kernel_game_image_inode"], self.owned.stat().st_ino)
        self.assertEqual(self.audit()["private_process_receipt_sha256"],
                         result["private_process_receipt_sha256"])
        self.join.assert_called()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_capture()

    def test_rejects_replacement_before_exec(self):
        self.binary.write_bytes(self.binary.read_bytes() + b" appended")
        with self.assertRaisesRegex(ValueError, "differs from plan"):
            self.run_capture()
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_refuses_process_that_never_opened_planned_image(self):
        with patch.dict("os.environ", {"VH_TEST_SKIP_DISC_FD": "1"}):
            with self.assertRaisesRegex(ValueError, "never opened"):
                self.run_capture()
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_fails_closed_on_unknown_nonzero_exit(self):
        # A very short-lived child may exit before Linux /proc observation
        # records its executable. Both outcomes are correct fail-closed
        # rejections; neither may publish a process evidence receipt.
        with self.assertRaisesRegex(
                ValueError,
                "exited unsuccessfully|kernel child executable identity was not confirmed"):
            self.run_capture("unexpected")
        self.assertFalse((self.handoff / RECEIPT).exists())
        self.assertEqual(list(self.native.iterdir()), [])
        self.assertEqual(list(self.scoped.iterdir()), [])

    def test_refuses_wrong_sample_coordinate_and_source_mutation(self):
        with self.assertRaises(ValueError):
            launch_observed_pc(
                self.handoff, self.native, self.scoped,
                self.binary, self.owned, upstream=self.upstream,
                x=1024, y=0, timeout=10)
        raster = self.upstream / "platform/pc/src/pc_raster.c"
        raster.write_bytes(raster.read_bytes() + b" tampered")
        with self.assertRaisesRegex(ValueError, "differs from pinned"):
            self.run_capture()

    def test_audit_rejects_changed_process_nonce_or_binary(self):
        self.run_capture()
        original = dict(self.checked)
        self.checked["capture_session_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            self.audit()
        self.checked.update(original)
        self.binary.write_bytes(self.binary.read_bytes() + b" changed")
        with self.assertRaisesRegex(ValueError, "differs from local capture plan"):
            self.audit()

    def test_late_audit_rejects_byte_identical_receipt_or_plan_inode_swap(self):
        self.run_capture()
        for filename in (RECEIPT, "gpu-local-capture-plan.json"):
            with self.subTest(file=filename):
                path = self.handoff / filename
                backup = self.handoff.parent / ("audit-original-" + filename)
                original_bytes = path.read_bytes()
                original_inode = path.stat().st_ino

                def swap_during_gpu_audit(*args, **kwargs):
                    path.replace(backup)
                    path.write_bytes(original_bytes)
                    path.chmod(0o600)
                    self.assertNotEqual(path.stat().st_ino, original_inode)
                    return self.checked

                try:
                    with patch(
                            "tools.map02_verified_process_launch.verify_window_scoped_join",
                            side_effect=swap_during_gpu_audit):
                        with self.assertRaisesRegex(
                                ValueError, "identity changed during re-verification"):
                            self.audit()
                finally:
                    if backup.exists():
                        path.unlink(missing_ok=True)
                        backup.replace(path)
                self.assertEqual(path.stat().st_ino, original_inode)

    def test_late_audit_refuses_linked_or_exposed_receipt_and_plan(self):
        self.run_capture()
        for filename in (RECEIPT, "gpu-local-capture-plan.json"):
            with self.subTest(file=filename):
                target = self.handoff / filename
                other = self.handoff.parent / ("duplicate-" + filename)
                os.link(target, other)
                try:
                    with self.assertRaisesRegex(ValueError, "owner-only 0600"):
                        self.audit()
                finally:
                    other.unlink()
                target.chmod(0o640)
                try:
                    with self.assertRaisesRegex(ValueError, "owner-only 0600"):
                        self.audit()
                finally:
                    target.chmod(0o600)

    def test_late_audit_refuses_same_metadata_second_read_corruption(self):
        self.run_capture()
        actual_pread = os.pread
        observed_reads = []

        def corrupt_second_pass(fd, count, offset):
            result = actual_pread(fd, count, offset)
            observed_reads.append(True)
            if len(observed_reads) == 2:
                return bytes([result[0] ^ 1]) + result[1:]
            return result

        with patch("tools.verify_map02_cycle_cd_gpu_join.os.pread",
                   side_effect=corrupt_second_pass):
            with self.assertRaisesRegex(ValueError, "bytes changed between reads"):
                self.audit()
        self.assertEqual(len(observed_reads), 2)

    def test_mutated_receipt_and_synthetic_false_attestation_rejected(self):
        self.run_capture()
        receipt = self.handoff / RECEIPT
        original = json.loads(receipt.read_bytes())
        for change in (
            {"game_image_consumption_proven": True},
            {"game_image_fd_observed": False},
            {"kernel_game_image_inode": True},
            {"retail_gameplay_authenticated": True},
            {"kernel_executable_matched_plan": False},
            {"observed_pid": True},
            {"capture_session_sha256": "not-valid"},
        ):
            tampered = dict(original, **change)
            receipt.write_text(json.dumps(tampered) + "\n")
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.audit()
        self.assertRaises(ValueError, _validate_receipt, {"schema": "fake"})

    def test_final_map02_handoff_binds_live_kernel_execution_receipt(self):
        self.run_capture()
        # Only the expensive source GTE witness is mocked in this unit test.
        # Its synthetic final record must refer to the same in-process nonce.
        final = self.fixture.source / "gpu-native-window-scoped-source-witness.json"
        source = json.loads(final.read_bytes())
        source["capture_session_sha256"] = "b" * 64
        raw = (json.dumps(source, sort_keys=True) + "\n").encode()
        final.write_bytes(raw)
        self.fixture.verified.return_value = {
            "private_witness_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "global_draw_ordinals_checked": 2,
        }
        sealed = self.fixture.seal()
        self.assertTrue(sealed["live_kernel_executable_observed"])
        handoff = json.loads(
            (self.handoff / "gpu-local-capture-handoff.json").read_bytes())
        self.assertEqual(handoff["schema"], "vh.map02.local-capture-handoff.v2")
        self.assertTrue(handoff["live_kernel_executable_observed"])
        receipt = (self.handoff / RECEIPT).read_bytes()
        self.assertEqual(
            handoff["observed_execution_receipt_sha256"],
            __import__("hashlib").sha256(receipt).hexdigest())
        self.assertTrue(self.fixture.verify()["live_kernel_executable_observed"])
        self.assertFalse(handoff["owned_game_binary_executed_proven"])

    def test_final_handoff_rejects_live_process_nonce_not_matching_source_gte(self):
        self.run_capture()
        # The synthetic GTE source witness still refers to "a"*64, while
        # the real child session fixture has "b"*64.
        with self.assertRaisesRegex(ValueError, "GPU session differ"):
            self.fixture.seal()
        self.assertFalse(
            (self.handoff / "gpu-local-capture-handoff.json").exists())

    def test_opt_in_cycle_requires_private_empty_directory(self):
        cycle = self.handoff.parent / "cycle-launch"
        cycle.mkdir(mode=0o700)
        (cycle / "old.jsonl").write_text("stale")
        with self.assertRaisesRegex(ValueError, "folders must start empty"):
            launch_observed_pc(
                self.handoff, self.native, self.scoped,
                self.binary, self.owned, upstream=self.upstream,
                x=10, y=20, timeout=8, cycle_dir=cycle)
        self.assertFalse((self.handoff / RECEIPT).exists())
        (cycle / "old.jsonl").unlink()
        cycle.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "private"):
            launch_observed_pc(
                self.handoff, self.native, self.scoped,
                self.binary, self.owned, upstream=self.upstream,
                x=10, y=20, timeout=8, cycle_dir=cycle)

    def test_opt_in_cycle_cannot_accept_successful_gpu_without_cycle_receipt(self):
        cycle = self.handoff.parent / "cycle-unobserved"
        cycle.mkdir(mode=0o700)
        # The legacy synthetic child deliberately does not link cycle hooks.
        # Even when GPU verification is mocked successful, this cannot
        # become a new same-process MAP02 cycle success.
        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}):
            with self.assertRaisesRegex(ValueError, "receipt and normal-exit seal"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "private-build-receipt",
                    build_bundle_dir=self.handoff.parent / "private-build-bundle")
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_source_bound_cycle_rejects_forwarded_argv_before_spawn(self):
        cycle = self.handoff.parent / "cycle-untrusted-argv"
        cycle.mkdir(mode=0o700)
        with patch("tools.map02_verified_process_launch.subprocess.Popen") as popen:
            with self.assertRaisesRegex(ValueError, "forbids forwarded executable arguments"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    arguments=("--hd-pack=/untrusted/resource",),
                    build_receipt_dir=self.handoff.parent / "private-build-receipt",
                    build_bundle_dir=self.handoff.parent / "private-build-bundle")
        popen.assert_not_called()
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_source_bound_cycle_rejects_empty_or_nul_argument_before_spawn(self):
        cycle = self.handoff.parent / "cycle-invalid-argv"
        cycle.mkdir(mode=0o700)
        for arguments in (("",), ("value\x00other",)):
            with self.subTest(arguments=arguments):
                with patch("tools.map02_verified_process_launch.subprocess.Popen") as popen:
                    with self.assertRaisesRegex(ValueError, "invalid PC-port executable argument"):
                        launch_observed_pc(
                            self.handoff, self.native, self.scoped,
                            self.binary, self.owned, upstream=self.upstream,
                            x=10, y=20, timeout=8, cycle_dir=cycle,
                            arguments=arguments,
                            build_receipt_dir=self.handoff.parent / "receipt",
                            build_bundle_dir=self.handoff.parent / "bundle")
                popen.assert_not_called()
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_image_rejects_same_byte_inode_swap_after_fd_observation(self):
        cycle = self.handoff.parent / "cycle-image-inode-swap"
        cycle.mkdir(mode=0o700)
        old_image = self.owned.with_suffix(".saved-image")
        original_probe = launcher._kernel_observes_game_fd
        exchanged = []

        def replace_image_after_kernel_observation(pid, expected, *, excluded_fd=None):
            observed = original_probe(pid, expected, excluded_fd=excluded_fd)
            if observed and not exchanged:
                self.owned.replace(old_image)
                shutil.copyfile(old_image, self.owned)
                self.owned.chmod(0o600)
                self.assertNotEqual(self.owned.stat().st_ino, expected[1])
                exchanged.append(True)
            return observed

        try:
            with patch(
                    "tools.check_map02_cycle_elf.audit_cycle_elf",
                    return_value={"required_symbols_present": 19}), patch(
                    "tools.map02_cycle_build_provenance.verify_build_receipt",
                    return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                    "tools.map02_verified_process_launch._kernel_observes_game_fd",
                    side_effect=replace_image_after_kernel_observation):
                with self.assertRaisesRegex(
                        ValueError, "game-image identity changed during run"):
                    launch_observed_pc(
                        self.handoff, self.native, self.scoped,
                        self.binary, self.owned, upstream=self.upstream,
                        x=10, y=20, timeout=8, cycle_dir=cycle,
                        build_receipt_dir=self.handoff.parent / "receipt",
                        build_bundle_dir=self.handoff.parent / "bundle")
        finally:
            if old_image.exists():
                self.owned.unlink(missing_ok=True)
                old_image.replace(self.owned)
        self.assertTrue(exchanged)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_real_child_must_open_disc_independently_of_inherited_fd(self):
        cycle = self.handoff.parent / "cycle-inherited-only"
        cycle.mkdir(mode=0o700)
        original_popen = subprocess.Popen
        observed_inherited = []

        def child_without_cd_mount(*args, **kwargs):
            exec_fd, image_fd = kwargs["pass_fds"]
            self.assertEqual(kwargs["env"]["VH_DISC_IMAGE"],
                             f"/proc/self/fd/{image_fd}")
            observed_inherited.append(os.fstat(image_fd).st_ino)
            # The synthetic native ELF sleeps with its inherited FD alive,
            # but never calls fopen on the planned image.
            kwargs["env"]["VH_TEST_SKIP_DISC_FD"] = "1"
            return original_popen(*args, **kwargs)

        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                "tools.map02_verified_process_launch.subprocess.Popen",
                side_effect=child_without_cd_mount):
            with self.assertRaisesRegex(ValueError, "never opened the planned game-image"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "receipt",
                    build_bundle_dir=self.handoff.parent / "bundle")
        self.assertEqual(observed_inherited, [self.owned.stat().st_ino])
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_inherited_cycle_image_fd_is_not_mistaken_for_child_open(self):
        expected_stat = self.owned.stat()
        expected = (expected_stat.st_dev, expected_stat.st_ino,
                    expected_stat.st_size)
        inherited = os.open(self.owned, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            self.assertFalse(launcher._kernel_observes_game_fd(
                os.getpid(), expected, excluded_fd=inherited))
            separate_open = os.open(self.owned, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                self.assertTrue(launcher._kernel_observes_game_fd(
                    os.getpid(), expected, excluded_fd=inherited))
            finally:
                os.close(separate_open)
        finally:
            os.close(inherited)

    def test_cycle_disc_path_swap_during_spawn_cannot_redirect_child_cd_mount(self):
        cycle = self.handoff.parent / "cycle-image-spawn-race"
        cycle.mkdir(mode=0o700)
        original_popen = subprocess.Popen
        original = self.owned.with_suffix(".original-image")
        forwarded = []

        def substitute_path_at_spawn(*args, **kwargs):
            exec_fd, image_fd = kwargs["pass_fds"]
            self.assertEqual(kwargs["executable"], f"/proc/self/fd/{exec_fd}")
            self.assertEqual(kwargs["env"]["VH_DISC_IMAGE"],
                             f"/proc/self/fd/{image_fd}")
            pinned_inode = os.fstat(image_fd).st_ino
            self.owned.replace(original)
            self.owned.write_bytes(b"untrusted replacement bytes, not the original image")
            self.owned.chmod(0o600)
            self.assertNotEqual(self.owned.stat().st_ino, pinned_inode)
            forwarded.append(pinned_inode)
            # The child reads a sentinel 'f' from the original inode. A
            # reopened mutable pathname would read 'u' and exit with code 5.
            return original_popen(*args, **kwargs)

        try:
            with patch(
                    "tools.check_map02_cycle_elf.audit_cycle_elf",
                    return_value={"required_symbols_present": 19}), patch(
                    "tools.map02_cycle_build_provenance.verify_build_receipt",
                    return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                    "tools.map02_verified_process_launch.subprocess.Popen",
                    side_effect=substitute_path_at_spawn):
                with self.assertRaisesRegex(ValueError, "game-image identity changed during run"):
                    launch_observed_pc(
                        self.handoff, self.native, self.scoped,
                        self.binary, self.owned, upstream=self.upstream,
                        x=10, y=20, timeout=8, cycle_dir=cycle,
                        build_receipt_dir=self.handoff.parent / "receipt",
                        build_bundle_dir=self.handoff.parent / "bundle")
        finally:
            if original.exists():
                self.owned.unlink(missing_ok=True)
                original.replace(self.owned)
        self.assertEqual(len(forwarded), 1)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_spawn_error_closes_both_pinned_descriptors(self):
        cycle = self.handoff.parent / "cycle-spawn-closed"
        cycle.mkdir(mode=0o700)
        passed_fds = []

        def fail_popen(*args, **kwargs):
            passed_fds.extend(kwargs["pass_fds"])
            for descriptor in passed_fds:
                os.fstat(descriptor)  # still open while Popen is called
            raise ValueError("synthetic spawn failure")

        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                "tools.map02_verified_process_launch.subprocess.Popen",
                side_effect=fail_popen):
            with self.assertRaisesRegex(ValueError, "synthetic spawn failure"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "receipt",
                    build_bundle_dir=self.handoff.parent / "bundle")
        self.assertEqual(len(passed_fds), 2)
        for descriptor in passed_fds:
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_image_rejects_changed_second_read_without_metadata_change(self):
        original_pread = os.pread
        calls = []

        def flip_second_pass(fd, length, offset):
            block = original_pread(fd, length, offset)
            calls.append(True)
            if len(calls) == 2:
                return bytes([block[0] ^ 1]) + block[1:]
            return block

        with patch("tools.map02_verified_process_launch.os.pread",
                   side_effect=flip_second_pass):
            with self.assertRaisesRegex(ValueError, "bytes changed between read passes"):
                launcher._stable_owned_cycle_image(self.owned)
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_image_rejects_private_file_hardlinks_and_symlinks(self):
        owned_alias = self.owned.with_suffix(".alias")
        os.link(self.owned, owned_alias)
        try:
            with self.assertRaisesRegex(ValueError, "not exclusively owned"):
                launcher._stable_owned_cycle_image(self.owned)
        finally:
            owned_alias.unlink()
        owned_alias.symlink_to(self.owned)
        try:
            with self.assertRaisesRegex(ValueError, "input unavailable"):
                launcher._stable_owned_cycle_image(owned_alias)
        finally:
            owned_alias.unlink()
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_fd_rejects_inode_swapped_after_original_plan(self):
        from tools.check_map02_linked_font_elf import stable_owned_elf_sha256
        expected = stable_owned_elf_sha256(self.binary)
        initial_stat = self.binary.stat()
        saved = self.binary.with_suffix(".original-elf")
        try:
            self.binary.replace(saved)
            shutil.copyfile(saved, self.binary)
            self.binary.chmod(0o700)
            with self.assertRaisesRegex(ValueError, "inode changed before exec"):
                launcher._open_pinned_cycle_exec_fd(
                    self.binary, expected, initial_stat)
        finally:
            if saved.exists():
                self.binary.unlink(missing_ok=True)
                saved.replace(self.binary)

    def test_cycle_pre_exec_rejects_unstable_elf_digest(self):
        cycle = self.handoff.parent / "cycle-unstable-pre-elf"
        cycle.mkdir(mode=0o700)
        with patch(
                "tools.check_map02_linked_font_elf.stable_owned_elf_sha256",
                side_effect=ValueError("private ELF digest bytes changed between read passes")
        ), patch("tools.map02_verified_process_launch.subprocess.Popen") as popen:
            with self.assertRaisesRegex(ValueError, "bytes changed between read passes"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "private-receipt",
                    build_bundle_dir=self.handoff.parent / "private-bundle")
        popen.assert_not_called()
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_post_exec_rejects_unstable_elf_digest(self):
        cycle = self.handoff.parent / "cycle-unstable-post-elf"
        cycle.mkdir(mode=0o700)
        from tools.check_map02_linked_font_elf import stable_owned_elf_sha256
        original_digest = stable_owned_elf_sha256(self.binary)
        with patch(
                "tools.check_map02_linked_font_elf.stable_owned_elf_sha256",
                side_effect=[original_digest, ValueError(
                    "private ELF digest bytes changed between read passes")]), patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}):
            with self.assertRaisesRegex(ValueError, "bytes changed between read passes"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "private-receipt",
                    build_bundle_dir=self.handoff.parent / "private-bundle")
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_requires_a_build_receipt_and_source_bundle_before_exec(self):
        cycle = self.handoff.parent / "cycle-no-build"
        cycle.mkdir(mode=0o700)
        with patch("tools.check_map02_cycle_elf.audit_cycle_elf",
                   return_value={"required_symbols_present": 19}):
            with self.assertRaisesRegex(ValueError, "requires both private build"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped, self.binary,
                    self.owned, upstream=self.upstream, x=10, y=20,
                    timeout=8, cycle_dir=cycle)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_refuses_wrong_build_provenance_before_exec(self):
        cycle = self.handoff.parent / "cycle-tampered-build"
        cycle.mkdir(mode=0o700)
        with patch("tools.check_map02_cycle_elf.audit_cycle_elf",
                   return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                side_effect=ValueError("original MAP02 executable/source differs")):
            with self.assertRaisesRegex(ValueError, "executable/source differs"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped, self.binary,
                    self.owned, upstream=self.upstream, x=10, y=20,
                    timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "receipt",
                    build_bundle_dir=self.handoff.parent / "bundle")
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_directory_reaches_real_child_and_nonce_is_checked(self):
        cycle = self.handoff.parent / "cycle-transport"
        cycle.mkdir(mode=0o700)
        original_popen = subprocess.Popen
        forwarded = []
        environments = []

        def observed_popen(*args, **kwargs):
            environments.append(dict(kwargs["env"]))
            forwarded.append(kwargs["env"].get("VH_MAP02_CYCLE_OUTPUT_DIR"))
            # The actual ELF is opened by /proc/self/fd, not by the mutable
            # original pathname. Popen must inherit the pinned descriptor.
            exec_fd, image_fd = kwargs["pass_fds"]
            self.assertEqual(kwargs["executable"], f"/proc/self/fd/{exec_fd}")
            self.assertEqual(kwargs["env"]["VH_DISC_IMAGE"],
                             f"/proc/self/fd/{image_fd}")
            self.assertEqual(os.fstat(exec_fd).st_ino, self.binary.stat().st_ino)
            self.assertEqual(os.fstat(image_fd).st_ino, self.owned.stat().st_ino)
            return original_popen(*args, **kwargs)

        # This test exercises only launcher wiring and nonce checking:
        # the expensive cycle receipt is intentionally mocked. The actual
        # synthetic child is not linked to the original gameplay loader.
        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}) as structural, patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}) as build_verified, patch(
                "tools.verify_map02_cycle_cd_gpu_join._cycle_cd_pair",
                return_value=(b"cycle-bytes", (), b"cd-bytes", ())) as receipt:
            with patch.dict(os.environ, {
                    "VH_HD_PACK": "/untrusted/hd-backgrounds",
                    "VH_HD_VIDEOS": "/untrusted/hd-video",
                    "VH_HDPACK": "1",
                    "VH_LANG": "test-language",
                    "VH_LANGPACK": "/untrusted/localized",
                    "VH_INTERNAL_SCALE": "4",
                    "VH_ACCURATE": "0",
                    "VH_RASTER_THREADS": "8",
                    "VH_MAP02_PROBE_FRAME": "999",
                    "VH_ALLOW_UNVERIFIED_EXE": "1",
                    "VH_PSX_EXE": "/untrusted/other-psx.exe",
                    "VH_REGION": "jp",
                    "VH_KROM_SOURCE": "/untrusted/other-font.bin",
                    "LD_PRELOAD": "/untrusted/inject.so",
                    "LD_AUDIT": "/untrusted/audit.so",
                    "LD_LIBRARY_PATH": "/untrusted/libraries",
                    "DYLD_INSERT_LIBRARIES": "/untrusted/plugin.dylib",
                    "PYTHONPATH": "/untrusted/python",
                    "PYTHONHOME": "/untrusted/python-home",
                    "GLIBC_TUNABLES": "glibc.malloc.check=1",
                    "GCONV_PATH": "/untrusted/charset-plugin",
                    "SDL_DYNAMIC_API": "/untrusted/sdl.so",
                    "QT_PLUGIN_PATH": "/untrusted/qt",
                    "GIO_EXTRA_MODULES": "/untrusted/gio",
                    "BASH_ENV": "/untrusted/shell-hooks",
                    "ENV": "/untrusted/shell-env",
                    "MESA_LOADER_DRIVER_OVERRIDE": "untrusted-driver",
                    "DISPLAY": ":77",
                    "XDG_RUNTIME_DIR": "/test/map02-xdg-runtime",
                    "PULSE_SERVER": "unix:/test/map02-pulse",
            }):
                with patch("tools.map02_verified_process_launch.subprocess.Popen",
                           side_effect=observed_popen):
                    result = launch_observed_pc(
                        self.handoff, self.native, self.scoped,
                        self.binary, self.owned, upstream=self.upstream,
                        x=10, y=20, timeout=8, cycle_dir=cycle,
                        build_receipt_dir=self.handoff.parent / "private-build-receipt",
                        build_bundle_dir=self.handoff.parent / "private-build-bundle")
        self.assertEqual(build_verified.call_count, 2)
        structural.assert_called_once_with(self.binary)
        self.assertEqual(len(environments), 1)
        child_env = environments[0]
        for name, expected in (
                ("VH_HDPACK", "0"), ("VH_HD_PACK", ""),
                ("VH_HD_VIDEOS", ""), ("VH_LANG", ""),
                ("VH_LANGPACK", ""), ("VH_INTERNAL_SCALE", "1"),
                ("VH_ACCURATE", "1"), ("VH_RASTER_THREADS", "1"),
                ("VH_MAP02_PROBE_FRAME", "7")):
            with self.subTest(variable=name):
                self.assertEqual(child_env.get(name), expected)
        for variable in (
                "VH_ALLOW_UNVERIFIED_EXE", "VH_KROM_SOURCE", "LD_PRELOAD",
                "LD_AUDIT", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
                "PYTHONPATH", "PYTHONHOME", "GLIBC_TUNABLES",
                "GCONV_PATH", "SDL_DYNAMIC_API", "QT_PLUGIN_PATH",
                "GIO_EXTRA_MODULES", "BASH_ENV", "ENV",
                "MESA_LOADER_DRIVER_OVERRIDE"):
            with self.subTest(blocked_environment=variable):
                self.assertNotIn(variable, child_env)
        self.assertEqual(child_env.get("DISPLAY"), ":77")
        self.assertEqual(child_env.get("XDG_RUNTIME_DIR"),
                         "/test/map02-xdg-runtime")
        self.assertEqual(child_env.get("PULSE_SERVER"),
                         "unix:/test/map02-pulse")
        self.assertEqual(child_env.get("VH_REGION"), "us")
        self.assertEqual(child_env.get("VH_PSX_EXE"),
                         str(self.upstream / "SLUS_004.47"))
        self.assertTrue(result["kernel_executable_hash_matched"])
        self.assertEqual(forwarded, [str(cycle)])
        self.assertEqual(receipt.call_count, 2)
        self.assertTrue((self.handoff / RECEIPT).exists())

    def test_cycle_wrong_cd_crc_refuses_kernel_receipt_publication(self):
        cycle = self.handoff.parent / "cycle-wrong-cd"
        cycle.mkdir(mode=0o700)
        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                "tools.verify_map02_cycle_cd_gpu_join._cycle_cd_pair",
                side_effect=ValueError("ordered cycle CRC32 and original CdRead receipt differ")):
            with self.assertRaisesRegex(ValueError, "CRC32 and original CdRead"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "receipt",
                    build_bundle_dir=self.handoff.parent / "bundle")
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_cd_pair_inode_or_bytes_change_before_publish_refused(self):
        cycle = self.handoff.parent / "cycle-cd-pair-replaced"
        cycle.mkdir(mode=0o700)
        original_proof = (b"cycle", ("inode-cycle",), b"original-cd", ("inode-cd",))
        changed_proof = (b"cycle", ("inode-cycle",), b"original-cd", ("different-inode",))
        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                "tools.verify_map02_cycle_cd_gpu_join._cycle_cd_pair",
                side_effect=[original_proof, changed_proof]) as verifier:
            with self.assertRaisesRegex(ValueError, "changed before process publication"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "receipt",
                    build_bundle_dir=self.handoff.parent / "bundle")
        self.assertEqual(verifier.call_count, 2)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_rejects_identical_bytes_replacement_during_spawn(self):
        cycle = self.handoff.parent / "cycle-inode-race"
        cycle.mkdir(mode=0o700)
        original_popen = subprocess.Popen
        saved = self.binary.with_suffix(".original-elf")
        forwarded_inode = []

        def replace_path_before_exec(*args, **kwargs):
            descriptor, image_fd = kwargs["pass_fds"]
            self.assertEqual(kwargs["executable"], f"/proc/self/fd/{descriptor}")
            self.assertEqual(kwargs["env"]["VH_DISC_IMAGE"], f"/proc/self/fd/{image_fd}")
            expected_inode = os.fstat(descriptor).st_ino
            self.binary.replace(saved)
            # Identical executable bytes but a DIFFERENT inode. The child
            # must be bound to the already-open descriptor, not this file.
            shutil.copyfile(saved, self.binary)
            self.binary.chmod(0o700)
            self.assertNotEqual(self.binary.stat().st_ino, expected_inode)
            forwarded_inode.append(expected_inode)
            return original_popen(*args, **kwargs)

        try:
            with patch(
                    "tools.check_map02_cycle_elf.audit_cycle_elf",
                    return_value={"required_symbols_present": 19}), patch(
                    "tools.map02_cycle_build_provenance.verify_build_receipt",
                    return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                    "tools.map02_verified_process_launch.subprocess.Popen",
                    side_effect=replace_path_before_exec):
                with self.assertRaisesRegex(ValueError, "pathname replaced during run"):
                    launch_observed_pc(
                        self.handoff, self.native, self.scoped,
                        self.binary, self.owned, upstream=self.upstream,
                        x=10, y=20, timeout=8, cycle_dir=cycle,
                        build_receipt_dir=self.handoff.parent / "private-build-receipt",
                        build_bundle_dir=self.handoff.parent / "private-build-bundle")
        finally:
            if saved.exists():
                self.binary.unlink(missing_ok=True)
                saved.replace(self.binary)
        self.assertEqual(len(forwarded_inode), 1)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_cycle_fails_if_source_bound_build_receipt_changes_during_child(self):
        cycle = self.handoff.parent / "cycle-build-edited-in-run"
        cycle.mkdir(mode=0o700)
        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                side_effect=[
                    {"source_pinned_full_elf_bytes_checked": True,
                     "private_build_receipt_sha256": "a" * 64},
                    {"source_pinned_full_elf_bytes_checked": True,
                     "private_build_receipt_sha256": "b" * 64},
                ]):
            with self.assertRaisesRegex(ValueError, "changed during run"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped, self.binary,
                    self.owned, upstream=self.upstream, x=10, y=20,
                    timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "receipt",
                    build_bundle_dir=self.handoff.parent / "bundle")
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_mismatched_cycle_nonce_rejects_kernel_receipt(self):
        cycle = self.handoff.parent / "cycle-wrong-nonce"
        cycle.mkdir(mode=0o700)
        with patch(
                "tools.check_map02_cycle_elf.audit_cycle_elf",
                return_value={"required_symbols_present": 19}), patch(
                "tools.map02_cycle_build_provenance.verify_build_receipt",
                return_value={"source_pinned_full_elf_bytes_checked": True}), patch(
                "tools.verify_map02_cycle_cd_gpu_join._cycle_cd_pair",
                side_effect=ValueError("single-process cycle nonce differs from GPU/scoped witness")):
            with self.assertRaisesRegex(ValueError, "cycle nonce differs"):
                launch_observed_pc(
                    self.handoff, self.native, self.scoped,
                    self.binary, self.owned, upstream=self.upstream,
                    x=10, y=20, timeout=8, cycle_dir=cycle,
                    build_receipt_dir=self.handoff.parent / "private-build-receipt",
                    build_bundle_dir=self.handoff.parent / "private-build-bundle")
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_rejects_uninstrumented_child_before_cycle_mode_exec(self):
        cycle = self.handoff.parent / "cycle-structural"
        cycle.mkdir(mode=0o700)
        # This really executes nm/readelf on the synthetic owned ELF:
        # a program that opens the correct disc is not the original cycle.
        with self.assertRaisesRegex(ValueError, "lacks required symbol"):
            launch_observed_pc(
                self.handoff, self.native, self.scoped,
                self.binary, self.owned, upstream=self.upstream,
                x=10, y=20, timeout=8, cycle_dir=cycle)
        self.assertFalse((self.handoff / RECEIPT).exists())

    def test_refuses_nonempty_capture_directory_before_exec(self):
        (self.native / "previous-run").write_text("no")
        with self.assertRaisesRegex(ValueError, "must start empty"):
            self.run_capture()
        self.assertFalse((self.handoff / RECEIPT).exists())


if __name__ == "__main__":
    unittest.main()
