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

from tools.map02_private_core_witness_audit import read_witness
from tools.map02_private_disc_movie_preflight import (
    _assert_stable, _open_stable, _resolve_private_file,
)

SCHEMA = "vh.map02.owner-process-to-core-witness-review.v1"
MAGIC = "VH_MAP02_OWNER_EMUHAWK_PROCESS_START_V1"
NAME = "vh_emuhawk_process_identity.txt"
FILETIME_UNIX_EPOCH_OFFSET = 504911232000000000
MIN_TICKS = 621355968000000000
MAX_TICKS = 725811840000000000
MAX_BYTES = 180
POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*\Z")


def windows_process_start_ticks(pid: int) -> int:
    """Read the real kernel process birth time, as .NET DateTime UTC ticks."""
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
    kernel.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
    ]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)  # limited query only
    if not handle:
        raise OSError("cannot query owned EmuHawk process creation time")
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
        kernel.CloseHandle(handle)


def record_started_process(pid: int, owner_private_dir: Path) -> None:
    """Exclusively create a 0600 owner-local launch receipt while PID is alive."""
    directory = Path(owner_private_dir)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise ValueError("owner-private capture directory must already exist")
    # The parent capture launcher has already created this specific directory
    # as owner-only and rejects any Git checkout input/output directories.
    if (directory / ".git").exists():
        raise ValueError("process identity receipt must be outside Git")
    ticks = windows_process_start_ticks(pid)
    path = directory / NAME
    payload = (
        f"{MAGIC}\nprocess_id={pid}\n"
        f"process_start_utc_ticks={ticks}\n"
    ).encode("ascii")
    if len(payload) > MAX_BYTES:
        raise ValueError("private process receipt outside size bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
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
    witness = (read_witness(paths[1]), read_witness(paths[3]))
    if started[0] == started[1] or witness[0][:2] == witness[1][:2]:
        raise ValueError("private capture attempts reuse the same reported process")
    for expected, actual in zip(started, witness):
        if expected != actual[:2]:
            raise ValueError("runtime core witness does not match launched EmuHawk PID and birth time")
    return {
        "schema": SCHEMA,
        "owner_private_capture_attempts": 2,
        "runtime_core_witnesses_bound_to_launched_process_identity": True,
        "reported_emuhawk_processes_distinct": True,
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
