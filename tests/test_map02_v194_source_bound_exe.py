#!/usr/bin/env python3
"""MAP02 v194: source-built PS-X EXE must match the true native input."""
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

from test_map02_v193_guest_exe_identity import make_witness
from tools.apply_map02_v183_native_ram_values import make_variants
from tools.check_map02_v193_guest_exe_identity import (
    EXE_NAME, MANIFEST as EXE_RECEIPTS, audit_executable,
)
from tools.check_map02_v194_source_bound_exe import (
    PASS_MARKER, audit_canonical_source,
)


def seed_source_witness(directory: Path, label: str = "CORRECT") -> None:
    make_witness(directory)
    exe = make_variants()[label]
    (directory / EXE_NAME).write_bytes(exe)
    digest = hashlib.sha256(exe).hexdigest()
    entries = [
        f"mode={mode} before={digest} after={digest}"
        for mode in range(10)
    ]
    (directory / EXE_RECEIPTS).write_text(
        "\n".join(entries) + "\n", encoding="ascii"
    )


class V194NativeSourceExecutable(unittest.TestCase):
    def test_ten_real_exits_exact_canonical_signed_source_regeneration(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            seed_source_witness(directory)
            original = (directory / EXE_NAME).read_bytes()
            self.assertEqual(audit_canonical_source(directory), (10, 3, 20))
            self.assertEqual((directory / EXE_NAME).read_bytes(), original)

    def test_catches_self_consistent_but_wrong_mips_executable(self):
        # v193 alone accepts an unchanged but wrong file when all ten receipt
        # hashes agree with that swapped source. v194 must independently
        # reconstruct and reject both deliberate wrong-instruction variants.
        for label in ("MISSING_SW", "MISSING_LW"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                directory = Path(td)
                seed_source_witness(directory, label)
                self.assertEqual(audit_executable(directory), (10, 20, 10))
                with self.assertRaisesRegex(ValueError, "checked-in source"):
                    audit_canonical_source(directory)

    def test_refuses_mutation_between_source_rebuild_and_parent_proof(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            seed_source_witness(directory)
            exe_path = directory / EXE_NAME
            original = exe_path.read_bytes()

            def flip_exe(parent: Path):
                exe_path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                return 10, 20, 10

            with patch(
                "tools.check_map02_v194_source_bound_exe.audit_executable",
                side_effect=flip_exe,
            ):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    audit_canonical_source(directory)

    def test_refuses_noncanonical_generator_result(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            seed_source_witness(directory)
            with patch(
                "tools.check_map02_v194_source_bound_exe.make_variants",
                return_value={"CORRECT": b"PS-X EXE"},
            ):
                with self.assertRaisesRegex(ValueError, "variant set"):
                    audit_canonical_source(directory)

    def test_pinned_native_ci_checks_source_after_guest_sha_chain(self):
        native = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v194-source-bound-exe.yml").read_text()
        self.assertIn(PASS_MARKER, native)
        self.assertIn("test_map02_v194_source_bound_exe.py", native)
        self.assertIn("check_map02_v194_source_bound_exe --verify-dir proof/private", native)
        self.assertLess(
            native.index("VH193_NATIVE_GUEST_EXE_IDENTITY_PASS modes=10"),
            native.index("VH194_NATIVE_SOURCE_EXE_REBUILD_PASS modes=10"),
        )
        self.assertIn("test_map02_v193_guest_exe_identity.py", independent)
        self.assertIn("original_retail_executed=0", independent)


if __name__ == "__main__":
    unittest.main()
