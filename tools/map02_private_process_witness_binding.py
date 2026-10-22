#!/usr/bin/env python3
"""Owner-local process-start receipt and offline PSX core-witness binding.

Only links the PID + Windows process creation time of an EmuHawk process
launched by our private wrapper to an owner-saved External Tool receipt.
No ROM, BIOS, BK2, screenshot bytes or identifying values reach public
stdout/GitHub. This DOES NOT cryptographically authenticate the receipts.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import stat
import sys

from tools.map02_private_core_witness_audit import read_witness_record
from tools.map02_private_disc_movie_preflight import (
    _assert_stable, _open_stable, _resolve_private_file,
)

SCHEMA = "vh.map02.owner-process-to-core-witness-review.v2"
MAGIC = "VH_MAP02_OWNER_EMUHAWK_PROCESS_START_V1"
NAME = "vh_emuhawk_process_identity.txt"
FILETIME_UNIX_EPOCH_OFFSET = 504911232000000000
MIN_TICKS = 621355968000000000
MAX_TICKS = 725811840000000000
MAX_BYTES = 180
POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*\Z")


def windows_process_start_ticks(
        pid: int, *, process_handle: int | None = None) -> int:
    """Read the kernel birth time, preferring the exact Popen-owned handle.

    Passing a process handle avoids reopening a numeric PID after the child
    starts, which could otherwise race process exit and PID reuse.
    """
    if os.name != "nt":
        raise ValueError("Windows process start-time recording requires Windows")
    if type(pid) is not int or not 1 <= pid <= 2147483647:
        raise ValueError("invalid owned process ID")
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel.GetProcessId.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
    ]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    owns_handle = process_handle is None
    if owns_handle:
        handle = kernel.OpenProcess(0x1000, False, pid)  # limited query only
        if not handle:
            raise OSError("cannot query owned EmuHawk process creation time")
    else:
        try:
            raw_handle = int(process_handle)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid owned EmuHawk process handle") from None
        if raw_handle <= 0:
            raise ValueError("invalid owned EmuHawk process handle")
        handle = wintypes.HANDLE(raw_handle)
        # A valid handle is stronger than a PID lookup, but still verify the
        # handle belongs to the PID recorded beside it.
        if kernel.GetProcessId(handle) != pid:
            raise ValueError("owned EmuHawk process handle does not match PID")

    try:
        created, exited, kernel_time, user_time = (FILETIME() for _ in range(4))
        success = kernel.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited),
            ctypes.byref(kernel_time), ctypes.byref(user_time),
        )
        if not success:
            raise OSError("cannot read owned EmuHawk process creation time")
        filetime = (created.dwHighDateTime << 32) | created.dwLowDateTime
        value = filetime + FILETIME_UNIX_EPOCH_OFFSET
        if not MIN_TICKS <= value <= MAX_TICKS:
            raise ValueError("owned process birth time outside supported period")
        return value
    finally:
        if owns_handle:
            kernel.CloseHandle(handle)


def _linux_proc_start_clock_ticks(pid: int, proc_root: Path = Path("/proc")) -> int:
    """Read field 22 from Linux /proc/PID/stat without trusting the comm field.

    The command name is parenthesized and may itself contain spaces or ')',
    so parse after its final closing parenthesis, then select field 22.
    """
    source = (proc_root / str(pid) / "stat").read_text(encoding="ascii")
    close = source.rfind(")")
    if close < 0:
        raise ValueError("Linux process stat record is malformed")
    try:
        observed_pid = int(source[:source.find(" ")], 10)
        fields_after_comm = source[close + 1:].strip().split()
        # The first tail field is process state (field 3); starttime is field 22.
        start_ticks = int(fields_after_comm[19], 10)
    except (ValueError, IndexError):
        raise ValueError("Linux process start-time fields are malformed") from None
    if observed_pid != pid or start_ticks < 0:
        raise ValueError("Linux process stat identity is inconsistent")
    return start_ticks


def linux_process_start_ticks(
        pid: int, *, proc_root: Path = Path("/proc"),
        clock_ticks_per_second: int | None = None) -> int:
    """Map the kernel's stable Linux process-start clock tick to .NET UTC ticks.

    Python and the Linux External Tool use the same integer-only formula, so
    process binding does not depend on wall-clock rounding or Mono DateTime
    precision. Read the start tick twice to reject PID exit/reuse during the
    observation. This is Linux x86_64 support, not a macOS fallback.
    """
    if type(pid) is not int or not 1 <= pid <= 2_147_483_647:
        raise ValueError("invalid owned process ID")
    root = Path(proc_root)
    if clock_ticks_per_second is None:
        try:
            clock_ticks_per_second = int(os.sysconf("SC_CLK_TCK"))
        except (OSError, ValueError, AttributeError):
            raise ValueError("Linux kernel clock tick rate is unavailable") from None
    if type(clock_ticks_per_second) is not int or not 1 <= clock_ticks_per_second <= 1_000_000:
        raise ValueError("Linux kernel clock tick rate is outside bounds")
    try:
        boot_time_line = next(
            line for line in (root / "stat").read_text(encoding="ascii").splitlines()
            if line.startswith("btime ")
        )
        boot_time = int(boot_time_line.split()[1], 10)
    except (OSError, UnicodeError, ValueError, IndexError, StopIteration):
        raise ValueError("Linux kernel boot-time reference is unavailable") from None
    first = _linux_proc_start_clock_ticks(pid, root)
    second = _linux_proc_start_clock_ticks(pid, root)
    if first != second:
        raise ValueError("Linux process identity changed during observation")
    value = ((boot_time * clock_ticks_per_second + first) * 10_000_000
             // clock_ticks_per_second)
    if not MIN_TICKS <= value <= MAX_TICKS:
        raise ValueError("Linux process birth time outside supported period")
    return value


def process_start_utc_ticks(
        pid: int, *, process_handle: int | None = None) -> int:
    """Select an OS-backed process birth-time implementation, fail closed elsewhere."""
    if os.name == "nt":
        return windows_process_start_ticks(pid, process_handle=process_handle)
    if sys.platform.startswith("linux"):
        if process_handle is not None:
            raise ValueError("Linux process identity does not accept a Windows handle")
        return linux_process_start_ticks(pid)
    raise ValueError("owner process identity supports Windows and Linux x86_64 only")


def record_started_process(
        pid: int, owner_private_dir: Path, *,
        process_handle: int | None = None) -> None:
    """Exclusively record a live child using its exact process handle when available."""
    directory = Path(owner_private_dir)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise ValueError("owner-private capture directory must already exist")
    # The parent capture launcher has already created this specific directory
    # as owner-only and rejects any Git checkout input/output directories.
    if (directory / ".git").exists():
        raise ValueError("process identity receipt must be outside Git")
    ticks = process_start_utc_ticks(pid, process_handle=process_handle)
    path = directory / NAME
    payload = (
        f"{MAGIC}\nprocess_id={pid}\n"
        f"process_start_utc_ticks={ticks}\n"
    ).encode("ascii")
    if len(payload) > MAX_BYTES:
        raise ValueError("private process receipt outside size bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    # Binary mode is required on Windows so line terminators stay exact LF.
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("new private process receipt is not regular")
        if os.write(fd, payload) != len(payload):
            raise OSError("private process receipt could not be written")
        os.fsync(fd)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def read_started_process(path: Path) -> tuple[int, int]:
    """Strict parser with stable descriptor/path, never emits identifier."""
    source = _resolve_private_file(path)
    fd, before = _open_stable(source)
    try:
        if not 0 < before.st_size <= MAX_BYTES:
            raise ValueError("private process receipt outside size bound")
        buf = b""
        while len(buf) < before.st_size:
            chunk = os.read(fd, before.st_size - len(buf))
            if not chunk:
                raise ValueError("incomplete private process receipt")
            buf += chunk
        _assert_stable(fd, source, before)
    finally:
        os.close(fd)
    try:
        lines = buf.decode("ascii").split("\n")
    except UnicodeDecodeError:
        raise ValueError("non-ASCII private process receipt") from None
    if len(lines) != 4 or lines[0] != MAGIC or lines[-1] != "":
        raise ValueError("private process receipt malformed or contains extra fields")
    pairs = []
    for line, key in zip(lines[1:3], ("process_id", "process_start_utc_ticks")):
        prefix = key + "="
        if not line.startswith(prefix):
            raise ValueError("private process receipt unexpected field")
        value = line[len(prefix):]
        if len(value) > 19 or not POSITIVE_DECIMAL.fullmatch(value):
            raise ValueError("private process receipt invalid number")
        pairs.append(int(value))
    if not 1 <= pairs[0] <= 2147483647 or not MIN_TICKS <= pairs[1] <= MAX_TICKS:
        raise ValueError("private process identity outside supported bounds")
    return pairs[0], pairs[1]


def bind_owner_private_replays(
        first_start: Path, first_core: Path,
        second_start: Path, second_core: Path) -> dict:
    """Require both exact PID/birthtime pairs, and two distinct processes.

    Text receipts can be fabricated and don't attest game/BK2 or screenshot
    origin. This rejects accidental mismatched or stale witness files.
    """
    paths = tuple(Path(p) for p in (
        first_start, first_core, second_start, second_core,
    ))
    if len(set(paths)) != 4:
        raise ValueError("four distinct private receipts are required")
    started = (read_started_process(paths[0]), read_started_process(paths[2]))
    witness = (read_witness_record(paths[1]), read_witness_record(paths[3]))
    if started[0] == started[1] or witness[0][:2] == witness[1][:2]:
        raise ValueError("private capture attempts reuse the same reported process")
    if witness[0][3] != witness[1][3]:
        raise ValueError("runtime tool assembly file hash differs across witnesses")
    if witness[0][4] != witness[1][4]:
        raise ValueError("runtime core assembly file hash differs across witnesses")
    if witness[0][5] != witness[1][5]:
        raise ValueError("native core module file hash differs across witnesses")
    for expected, actual in zip(started, witness):
        if expected != actual[:2]:
            raise ValueError("runtime core witness does not match launched EmuHawk PID and birth time")
    return {
        "schema": SCHEMA,
        "owner_private_capture_attempts": 2,
        "runtime_core_witnesses_bound_to_launched_process_identity": True,
        "reported_emuhawk_processes_distinct": True,
        "both_witnesses_report_same_tool_assembly_file_hash": True,
        "tool_assembly_file_hash_independently_pinned": False,
        "both_witnesses_report_same_runtime_core_assembly_file_hash": True,
        "runtime_core_assembly_file_hash_independently_pinned": False,
        "both_witnesses_report_same_native_core_module_file_hash": True,
        "native_core_module_file_hash_independently_pinned": False,
        "binding_authenticated_against_os_without_editable_receipts": False,
        "witnesses_linked_to_lua_or_png_by_cryptography": False,
        "active_core_claim_observed_via_manual_private_witnesses": True,
        "actual_bios_and_mounted_disc_authenticated": False,
        "original_bk2_input_or_map02_scene_authenticated": False,
        "private_ids_paths_and_media_hashes_published": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_private_launch_receipt", type=Path)
    parser.add_argument("first_private_octoshock_witness", type=Path)
    parser.add_argument("second_private_launch_receipt", type=Path)
    parser.add_argument("second_private_octoshock_witness", type=Path)
    args = parser.parse_args()
    try:
        report = bind_owner_private_replays(
            args.first_private_launch_receipt, args.first_private_octoshock_witness,
            args.second_private_launch_receipt, args.second_private_octoshock_witness,
        )
    except (OSError, ValueError, RuntimeError, TypeError):
        parser.error("private emulator process/witness binding rejected")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
