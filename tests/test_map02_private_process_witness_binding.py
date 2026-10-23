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
    linux_process_start_ticks, process_start_utc_ticks,
)
from tools.map02_private_process_group import run_owned_process

BIRTH_A = 639000000000000001
BIRTH_B = 639000000000000002


def started(pid, ticks):
    return (f"{MAGIC}\nprocess_id={pid}\n"
            f"process_start_utc_ticks={ticks}\n")


def core(pid, ticks, frame=1666, tool_hash="a" * 64,
         core_hash="b" * 64, native_hash="c" * 64):
    return (
        "VH_MAP02_RUNTIME_CORE_WITNESS_V3\n"
        "system=PSX\nloaded_core=Octoshock\n"
        "core_source=IEmulator.Attributes.CoreName\n"
        "runtime_core_type=BizHawk.Emulation.Cores.Sony.PSX.Octoshock\n"
        "core_assembly_sha256=" + core_hash + "\n"
        "native_core_module_name=octoshock.dll\n"
        "native_core_module_sha256=" + native_hash + "\n"
        "tool_assembly_sha256=" + tool_hash + "\n"
        f"process_id={pid}\nprocess_start_utc_ticks={ticks}\n"
        f"frame_count={frame}\nbios=unverified\n"
        "disc=unverified\nmovie_sync=unverified\n"
    )


def _lf_fixture(path: Path, text: str) -> None:
    """Model owner-local process receipts as exact LF bytes on every OS."""
    path.write_bytes(text.encode("ascii"))


class PrivateProcessWitnessBindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.a_start = self.root / "cold-01-process.txt"
        self.b_start = self.root / "cold-02-process.txt"
        self.a_core = self.root / "cold-01-core.txt"
        self.b_core = self.root / "cold-02-core.txt"
        _lf_fixture(self.a_start, started(3011, BIRTH_A))
        _lf_fixture(self.b_start, started(3012, BIRTH_B))
        _lf_fixture(self.a_core, core(3011, BIRTH_A))
        _lf_fixture(self.b_core, core(3012, BIRTH_B))

    def bind(self):
        return bind_owner_private_replays(
            self.a_start, self.a_core, self.b_start, self.b_core,
        )

    def test_exact_two_process_bindings_accept_with_explicit_limits(self):
        result = self.bind()
        self.assertTrue(result["runtime_core_witnesses_bound_to_launched_process_identity"])
        self.assertTrue(result["reported_emuhawk_processes_distinct"])
        self.assertTrue(result["both_witnesses_report_same_tool_assembly_file_hash"])
        self.assertTrue(result["both_witnesses_report_same_runtime_core_assembly_file_hash"])
        self.assertTrue(result["both_witnesses_report_same_native_core_module_file_hash"])
        self.assertFalse(result["tool_assembly_file_hash_independently_pinned"])
        self.assertFalse(result["runtime_core_assembly_file_hash_independently_pinned"])
        self.assertFalse(result["native_core_module_file_hash_independently_pinned"])
        self.assertFalse(result["binding_authenticated_against_os_without_editable_receipts"])
        self.assertFalse(result["witnesses_linked_to_lua_or_png_by_cryptography"])
        self.assertFalse(result["actual_bios_and_mounted_disc_authenticated"])
        self.assertFalse(result["original_bk2_input_or_map02_scene_authenticated"])
        for private in ("3011", str(BIRTH_A), str(self.root), "a" * 64):
            self.assertNotIn(private, json.dumps(result))

    def test_read_receipt_returns_local_only_pid_and_birth(self):
        self.assertEqual(read_started_process(self.a_start), (3011, BIRTH_A))

    def test_different_tool_assembly_hash_across_cold_runs_is_rejected(self):
        _lf_fixture(self.b_core, core(3012, BIRTH_B, tool_hash="b" * 64))
        with self.assertRaisesRegex(ValueError, "tool assembly file hash differs"):
            self.bind()

    def test_different_runtime_core_assembly_hash_across_cold_runs_is_rejected(self):
        _lf_fixture(self.b_core, core(3012, BIRTH_B, core_hash="d" * 64))
        with self.assertRaisesRegex(ValueError, "runtime core assembly file hash differs"):
            self.bind()

    def test_different_native_module_hash_across_cold_runs_is_rejected(self):
        _lf_fixture(self.b_core, core(3012, BIRTH_B, native_hash="e" * 64))
        with self.assertRaisesRegex(ValueError, "native core module file hash differs"):
            self.bind()

    def test_swapped_run_witness_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            bind_owner_private_replays(self.a_start, self.b_core,
                                       self.b_start, self.a_core)

    def test_stale_birth_time_rejected_even_when_pid_reused(self):
        _lf_fixture(self.a_core, core(3011, BIRTH_B))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.bind()

    def test_witness_from_unrelated_process_rejected(self):
        _lf_fixture(self.b_core, core(9009, BIRTH_B))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.bind()

    def test_duplicate_launch_process_identity_rejected(self):
        _lf_fixture(self.b_start, started(3011, BIRTH_A))
        with self.assertRaisesRegex(ValueError, "reuse"):
            self.bind()

    def test_duplicate_witness_process_identity_rejected(self):
        _lf_fixture(self.b_core, core(3011, BIRTH_A))
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
                _lf_fixture(self.a_start, value)
                with self.assertRaises(ValueError):
                    read_started_process(self.a_start)

    def test_process_identity_bounds_rejected(self):
        for pid, ticks in ((0, BIRTH_A), (2147483648, BIRTH_A),
                           (3011, 0), (3011, 725811840000000001)):
            with self.subTest(pid=pid, ticks=ticks):
                _lf_fixture(self.a_start, started(pid, ticks))
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
            "tools.map02_private_process_witness_binding.process_start_utc_ticks",
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
            "tools.map02_private_process_witness_binding.process_start_utc_ticks",
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

    def test_linux_start_clock_ticks_uses_proc_field_22_and_strict_boot_time(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp)
            (proc / "stat").write_text("cpu 1 2 3\nbtime 1700000000\n", encoding="ascii")
            pid_dir = proc / "3011"
            pid_dir.mkdir()
            tail = ["S"] + ["0"] * 18 + ["12345"]
            (pid_dir / "stat").write_text(
                "3011 (worker ) with parens) " + " ".join(tail) + "\n",
                encoding="ascii",
            )
            expected = 621355968000000000 + ((1700000000 * 100 + 12345) * 10_000_000) // 100
            self.assertEqual(
                linux_process_start_ticks(3011, proc_root=proc,
                                          clock_ticks_per_second=100),
                expected,
            )

    def test_linux_start_clock_rejects_pid_mismatch_and_changed_start_tick(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp)
            (proc / "stat").write_text("btime 1700000000\n", encoding="ascii")
            pid_dir = proc / "3011"
            pid_dir.mkdir()
            tail = ["S"] + ["0"] * 18 + ["12345"]
            (pid_dir / "stat").write_text(
                "9999 (worker) " + " ".join(tail) + "\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "identity is inconsistent"):
                linux_process_start_ticks(3011, proc_root=proc,
                                          clock_ticks_per_second=100)
            (pid_dir / "stat").write_text(
                "3011 (worker) " + " ".join(tail) + "\n", encoding="ascii")
            with patch(
                "tools.map02_private_process_witness_binding._linux_proc_start_clock_ticks",
                side_effect=[12345, 12346],
            ):
                with self.assertRaisesRegex(ValueError, "changed during observation"):
                    linux_process_start_ticks(3011, proc_root=proc,
                                              clock_ticks_per_second=100)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux procfs identity only")
    def test_linux_real_child_start_time_round_trips_to_private_receipt(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time;time.sleep(2)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            expected = linux_process_start_ticks(proc.pid)
            self.assertEqual(process_start_utc_ticks(proc.pid), expected)
            record_started_process(proc.pid, self.root)
            self.assertEqual(read_started_process(self.root / NAME),
                             (proc.pid, expected))
        finally:
            proc.terminate()
            proc.wait()

    @unittest.skipUnless(os.name == "nt", "Windows Popen handle identity only")
    def test_process_object_observer_records_the_owned_child_handle(self):
        observed = []

        def record(process):
            observed.append(process.pid)
            record_started_process(
                process.pid, self.root, process_handle=process._handle)

        result = run_owned_process(
            [sys.executable, "-c", "import time;time.sleep(0.5)"],
            env=os.environ.copy(), stdout=subprocess.DEVNULL, timeout=10,
            on_started_process=record,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(observed), 1)
        pid, ticks = read_started_process(self.root / NAME)
        self.assertEqual(pid, observed[0])
        self.assertGreaterEqual(ticks, 621355968000000000)
        self.assertLessEqual(ticks, 725811840000000000)

    @unittest.skipUnless(os.name == "nt", "Windows process identity API only")
    def test_real_windows_owned_child_creation_time(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time;time.sleep(3)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            birth = windows_process_start_ticks(
                proc.pid, process_handle=proc._handle)
            self.assertGreater(birth, 630000000000000000)
            self.assertLess(birth, 725811840000000000)
            with self.assertRaisesRegex(ValueError, "handle does not match PID"):
                windows_process_start_ticks(
                    proc.pid + 1, process_handle=proc._handle)
            with patch(
                "tools.map02_private_process_witness_binding.windows_process_start_ticks",
                return_value=birth,
            ):
                record_started_process(
                    proc.pid, self.root, process_handle=proc._handle)
            self.assertEqual(read_started_process(self.root / NAME),
                             (proc.pid, birth))
        finally:
            proc.kill()
            proc.wait()

    def test_unsafe_core_witness_false_bios_claim_rejected(self):
        _lf_fixture(
            self.a_core, core(3011, BIRTH_A).replace("bios=unverified", "bios=verified")
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
