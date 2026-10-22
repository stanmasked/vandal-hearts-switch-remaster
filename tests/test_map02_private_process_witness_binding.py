"""Entirely fictional process receipts and core witnesses; no original PS1 data."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_process_witness_binding import (
    MAGIC, NAME, bind_owner_private_replays, main, read_started_process,
    record_started_process, windows_process_start_ticks,
)

BIRTH_A = 639000000000000001
BIRTH_B = 639000000000000002


def started(pid, ticks):
    return (f"{MAGIC}\nprocess_id={pid}\n"
            f"process_start_utc_ticks={ticks}\n")


def core(pid, ticks, frame=1666):
    return (
        "VH_MAP02_RUNTIME_CORE_WITNESS_V1\n"
        "system=PSX\nloaded_core=Octoshock\n"
        "core_source=IEmulator.Attributes.CoreName\n"
        f"process_id={pid}\nprocess_start_utc_ticks={ticks}\n"
        f"frame_count={frame}\nbios=unverified\n"
        "disc=unverified\nmovie_sync=unverified\n"
    )


class PrivateProcessWitnessBindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.a_start = self.root / "cold-01-process.txt"
        self.b_start = self.root / "cold-02-process.txt"
        self.a_core = self.root / "cold-01-core.txt"
        self.b_core = self.root / "cold-02-core.txt"
        self.a_start.write_text(started(3011, BIRTH_A), encoding="ascii")
        self.b_start.write_text(started(3012, BIRTH_B), encoding="ascii")
        self.a_core.write_text(core(3011, BIRTH_A), encoding="ascii")
        self.b_core.write_text(core(3012, BIRTH_B), encoding="ascii")

    def bind(self):
        return bind_owner_private_replays(
            self.a_start, self.a_core, self.b_start, self.b_core,
        )

    def test_exact_two_process_bindings_accept_with_explicit_limits(self):
        result = self.bind()
        self.assertTrue(result["runtime_core_witnesses_bound_to_launched_process_identity"])
        self.assertTrue(result["reported_emuhawk_processes_distinct"])
        self.assertFalse(result["binding_authenticated_against_os_without_editable_receipts"])
        self.assertFalse(result["witnesses_linked_to_lua_or_png_by_cryptography"])
        self.assertFalse(result["actual_bios_and_mounted_disc_authenticated"])
        self.assertFalse(result["original_bk2_input_or_map02_scene_authenticated"])
        for private in ("3011", str(BIRTH_A), str(self.root)):
            self.assertNotIn(private, json.dumps(result))

    def test_read_receipt_returns_local_only_pid_and_birth(self):
        self.assertEqual(read_started_process(self.a_start), (3011, BIRTH_A))

    def test_swapped_run_witness_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            bind_owner_private_replays(self.a_start, self.b_core,
                                       self.b_start, self.a_core)

    def test_stale_birth_time_rejected_even_when_pid_reused(self):
        self.a_core.write_text(core(3011, BIRTH_B), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.bind()

    def test_witness_from_unrelated_process_rejected(self):
        self.b_core.write_text(core(9009, BIRTH_B), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.bind()

    def test_duplicate_launch_process_identity_rejected(self):
        self.b_start.write_text(started(3011, BIRTH_A), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "reuse"):
            self.bind()

    def test_duplicate_witness_process_identity_rejected(self):
        self.b_core.write_text(core(3011, BIRTH_A), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "reuse"):
            self.bind()

    def test_malformed_receipt_and_extra_field_rejected(self):
        for value in (
            started(3011, BIRTH_A).rstrip("\n"),
            started(3011, BIRTH_A) + "rom_path=/private/original.bin\n",
            started(3011, BIRTH_A).replace("process_id=", "id="),
            started(3011, BIRTH_A).replace("process_id=3011", "process_id=+3011"),
            started(3011, BIRTH_A).replace("process_id=3011", "process_id=03011"),
        ):
            with self.subTest(text_length=len(value)):
                self.a_start.write_text(value, encoding="ascii")
                with self.assertRaises(ValueError):
                    read_started_process(self.a_start)

    def test_process_identity_bounds_rejected(self):
        for pid, ticks in ((0, BIRTH_A), (2147483648, BIRTH_A),
                           (3011, 0), (3011, 725811840000000001)):
            with self.subTest(pid=pid, ticks=ticks):
                self.a_start.write_text(started(pid, ticks), encoding="ascii")
                with self.assertRaises(ValueError):
                    read_started_process(self.a_start)

    def test_nonascii_receipt_rejected(self):
        self.a_start.write_bytes(b"\xff" + started(3011, BIRTH_A).encode("ascii"))
        with self.assertRaisesRegex(ValueError, "non-ASCII"):
            read_started_process(self.a_start)

    def test_symlinked_receipt_rejected(self):
        link = self.root / "symlink-start.txt"
        link.symlink_to(self.a_start)
        with self.assertRaisesRegex(ValueError, "nonsymlink"):
            read_started_process(link)

    def test_source_inside_git_checkout_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "Git"):
            read_started_process(self.a_start)

    def test_writer_exclusive_file_and_private_mode(self):
        with patch(
            "tools.map02_private_process_witness_binding.windows_process_start_ticks",
            return_value=BIRTH_A,
        ):
            record_started_process(3011, self.root)
            with self.assertRaises(FileExistsError):
                record_started_process(3011, self.root)
        actual = self.root / NAME
        self.assertEqual(read_started_process(actual), (3011, BIRTH_A))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(actual.stat().st_mode), 0o600)

    def test_writer_never_overwrites_symlink(self):
        (self.root / NAME).symlink_to(self.a_start)
        with patch(
            "tools.map02_private_process_witness_binding.windows_process_start_ticks",
            return_value=BIRTH_A,
        ):
            with self.assertRaises(FileExistsError):
                record_started_process(3011, self.root)
        self.assertEqual(read_started_process(self.a_start), (3011, BIRTH_A))

    def test_writer_refuses_relative_path(self):
        with self.assertRaisesRegex(ValueError, "already exist"):
            record_started_process(3011, Path("relative/not-a-private-folder"))

    def test_posix_real_os_clock_query_refused(self):
        if os.name == "nt":
            self.skipTest("valid Windows query tested separately")
        with self.assertRaisesRegex(ValueError, "requires Windows"):
            windows_process_start_ticks(3011)

    @unittest.skipUnless(os.name == "nt", "Windows process identity API only")
    def test_real_windows_owned_child_creation_time(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time;time.sleep(3)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            birth = windows_process_start_ticks(proc.pid)
            self.assertGreater(birth, 630000000000000000)
            self.assertLess(birth, 725811840000000000)
            with patch(
                "tools.map02_private_process_witness_binding.windows_process_start_ticks",
                return_value=birth,
            ):
                record_started_process(proc.pid, self.root)
            self.assertEqual(read_started_process(self.root / NAME),
                             (proc.pid, birth))
        finally:
            proc.kill()
            proc.wait()

    def test_unsafe_core_witness_false_bios_claim_rejected(self):
        self.a_core.write_text(
            core(3011, BIRTH_A).replace("bios=unverified", "bios=verified"),
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            self.bind()

    def test_cli_output_contains_no_original_identifiers(self):
        out = io.StringIO()
        with patch.object(sys, "argv", [
            "process-witness-binding", str(self.a_start), str(self.a_core),
            str(self.b_start), str(self.b_core),
        ]), contextlib.redirect_stdout(out):
            self.assertEqual(main(), 0)
        self.assertTrue(json.loads(out.getvalue())[
            "runtime_core_witnesses_bound_to_launched_process_identity"])
        for private in ("3011", str(BIRTH_A), str(self.root)):
            self.assertNotIn(private, out.getvalue())


if __name__ == "__main__":
    unittest.main()
