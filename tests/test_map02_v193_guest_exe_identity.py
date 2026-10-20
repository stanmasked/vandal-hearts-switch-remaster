#!/usr/bin/env python3
"""MAP02 v193: test synthetic PS-X EXE SHA pin against ten real-exit receipts."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_map02_v192_native_process_exits import build_fixtures
from tools.check_map02_v193_guest_exe_identity import (
    EXE_NAME, MANIFEST, PASS_MARKER, audit_executable, private_receipts,
)


def make_witness(directory: Path) -> tuple[str, ...]:
    build_fixtures(directory)
    source = directory / EXE_NAME
    data = b"PS-X EXE" + b"\x00" * 2040
    source.write_bytes(data)
    fingerprint = hashlib.sha256(data).hexdigest()
    receipts = tuple(
        f"mode={mode} before={fingerprint} after={fingerprint}"
        for mode in range(10)
    )
    (directory / MANIFEST).write_text("\n".join(receipts) + "\n", encoding="ascii")
    return receipts


class V193NativeGuestExeIdentity(unittest.TestCase):
    def test_ten_real_exit_receipts_one_guest_exe_sha(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            original = make_witness(directory)
            before = (directory / EXE_NAME).read_bytes()
            self.assertEqual(private_receipts(directory), original)
            self.assertEqual(audit_executable(directory), (10, 20, 10))
            self.assertEqual((directory / EXE_NAME).read_bytes(), before)

    def test_rejects_omissions_duplicates_wrong_modes_or_forged_sha(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            original = make_witness(directory)
            sha = original[0].split("before=", 1)[1][:64]
            altered = [
                original[1:],
                original + original[-1:],
                (original[1], original[0]) + original[2:],
                original[:2] + (original[2].replace("mode=2", "mode=8"),) + original[3:],
                (original[0].replace(sha, "f" * 64, 1),) + original[1:],
                original[:5] + (original[5].replace("after=", "after=" + "0"),) + original[6:],
                original[:7] + (" PREFIX " + original[7],) + original[8:],
            ]
            for i, forged in enumerate(altered):
                with self.subTest(case=i):
                    (directory / MANIFEST).write_text("\n".join(forged) + "\n")
                    with self.assertRaises(ValueError):
                        audit_executable(directory)

    def test_refuses_guest_executable_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            make_witness(directory)
            (directory / EXE_NAME).write_bytes(b"PS-X EXE" + b"\x01" * 2040)
            with self.assertRaisesRegex(ValueError, "digest differs"):
                audit_executable(directory)

    def test_refuses_symlink_manifest_and_symlink_executable(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            make_witness(directory)
            file_path = directory / MANIFEST
            target = directory / "receipts-original"
            file_path.rename(target)
            file_path.symlink_to(target)
            with self.assertRaises(ValueError):
                private_receipts(directory)
            file_path.unlink()
            file_path.write_bytes(b"X" * 2049)
            with self.assertRaises(ValueError):
                private_receipts(directory)
            file_path.unlink()
            file_path.write_bytes(target.read_bytes())
            exe = directory / EXE_NAME
            exe_original = directory / "guest-original"
            exe.rename(exe_original)
            exe.symlink_to(exe_original)
            with self.assertRaises(ValueError):
                audit_executable(directory)

    def test_detects_change_while_parent_verifier_is_running(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            make_witness(directory)
            old_exe = directory / EXE_NAME
            original = old_exe.read_bytes()

            def corrupt_guest(parent):
                old_exe.write_bytes(original[:-1] + b"!")
                return (10, 9, 10)

            with patch(
                "tools.check_map02_v193_guest_exe_identity.verify_exits",
                side_effect=corrupt_guest,
            ):
                with self.assertRaisesRegex(ValueError, "changed after exit audit"):
                    audit_executable(directory)

    def test_pin_exe_in_real_native_shell_before_and_after_every_run(self):
        native = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v193-guest-exe-identity.yml").read_text()
        self.assertEqual(native.count('exe_before="$(sha256sum "proof/private/V183_RAM_CORRECT.EXE"'), 2)
        self.assertEqual(native.count('exe_after="$(sha256sum "proof/private/V183_RAM_CORRECT.EXE"'), 2)
        self.assertEqual(native.count('>> proof/private/v193-native-exe-receipts.txt'), 2)
        self.assertIn("check_map02_v193_guest_exe_identity --verify-dir proof/private", native)
        self.assertIn(PASS_MARKER, native)
        self.assertLess(
            native.index("VH192_NATIVE_PROCESS_EXIT_RECEIPTS_PASS modes=10"),
            native.index("VH193_NATIVE_GUEST_EXE_IDENTITY_PASS modes=10"),
        )
        self.assertIn("test_map02_v192_native_process_exits.py", independent)
        self.assertIn("original_retail_executed=0", independent)


if __name__ == "__main__":
    unittest.main()
