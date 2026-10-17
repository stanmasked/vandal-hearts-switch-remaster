#!/usr/bin/env python3
"""Opt-in Linux launcher: match a live child /proc/PID/exe to prepared MAP02 PC binary.

Execute a single user-owned instrumented PC-port binary WITHOUT a shell.
Read /proc/<child PID>/exe while it is alive; require its kernel-reported
device, inode and SHA-256 to match the pre-run plan and binary. On successful
exit, verify full native GPU window/PutPixel/BlendG1/VRAM observation with its
fresh in-process nonce, then exclusively publish a private execution receipt.

This is bounded OS process observation, not secure attestation: it does NOT
prove executable bytes are immutable during execution, prevent another
execve, identify loaded game assets, or demonstrate genuine retail MAP02.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from tools.map02_local_capture_handoff import (
    PLAN, _sha, _sha_file, _publish, _validate_plan, verify_pinned_upstream,
)
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_window_scoped_join import verify_window_scoped_join

RECEIPT = "gpu-local-executed-process.json"
SCHEMA = "vh.map02.local-executed-process.v1"
REQUIRED = (
    "schema", "gpu_draw_frame", "local_plan_sha256",
    "kernel_observed_executable_sha256", "kernel_executable_device",
    "kernel_executable_inode", "observed_pid",
    "pc_process_exit_code", "capture_session_sha256",
    "native_window_all_files_sha256",
    "selected_pixel_x", "selected_pixel_y",
    "kernel_executable_matched_plan", "same_process_gpu_scoped_nonce_checked",
    "game_image_consumption_proven", "retail_gameplay_authenticated",
    "physical_ps1_equivalence_proven",
)


def _fingerprint_kernel_exe(pid):
    """Read kernel procfs link for our live child. Fail closed if unavailable."""
    path = f"/proc/{pid}/exe"
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("kernel process executable is not regular")
        sha = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb") as stream:
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    break
                sha.update(chunk)
        after = os.fstat(fd)
        if (before.st_dev != after.st_dev or
                before.st_ino != after.st_ino or
                before.st_size != after.st_size or
                before.st_mtime_ns != after.st_mtime_ns):
            raise ValueError("process executable changed during kernel observation")
        return before.st_dev, before.st_ino, sha.hexdigest()
    finally:
        os.close(fd)


def _validate_receipt(raw):
    record = raw if type(raw) is dict else parse_json(raw, RECEIPT)
    fields(record, REQUIRED, RECEIPT)
    if (record["schema"] != SCHEMA or
            record["kernel_executable_matched_plan"] is not True or
            record["same_process_gpu_scoped_nonce_checked"] is not True or
            record["game_image_consumption_proven"] is not False or
            record["retail_gameplay_authenticated"] is not False or
            record["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated MAP02 process evidence")
    for key in ("local_plan_sha256", "kernel_observed_executable_sha256",
                "capture_session_sha256", "native_window_all_files_sha256"):
        value = record[key]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("invalid process receipt digest " + key)
    for key, low, high in (
        ("gpu_draw_frame", 1, 2**32 - 1),
        ("kernel_executable_device", 0, 2**64 - 1),
        ("kernel_executable_inode", 1, 2**64 - 1),
        ("observed_pid", 1, 2**32 - 1),
        ("pc_process_exit_code", 0, 0),
        ("selected_pixel_x", 0, 1023),
        ("selected_pixel_y", 0, 511),
    ):
        number(record[key], key, low, high)
    return record


def launch_observed_pc(handoff_dir, native_dir, scoped_dir, pc_binary,
                       owned_game, *, upstream, x, y, timeout=900,
                       arguments=()):
    """Run the given PC binary directly; never run a shell or create game data."""
    if not sys.platform.startswith("linux") or not Path("/proc/self/exe").exists():
        raise ValueError("observed executable launch requires Linux /proc")
    handoff, native, scoped = (_private_directory(p) for p in
                               (handoff_dir, native_dir, scoped_dir))
    if len({p.resolve() for p in (handoff, native, scoped)}) != 3:
        raise ValueError("execution evidence folders must be distinct")
    if any(p.iterdir() for p in (native, scoped)):
        raise ValueError("native GPU and scoped capture folders must start empty")
    if (handoff / RECEIPT).exists() or (handoff / RECEIPT).is_symlink():
        raise ValueError("local execution receipt already exists")
    plan_raw = private_file(handoff, PLAN, max_bytes=4096)
    plan = _validate_plan(plan_raw)
    x = number(x, "sample X", 0, 1023)
    y = number(y, "sample Y", 0, 511)
    timeout = number(timeout, "execution timeout seconds", 1, 86400)
    binary = Path(pc_binary).absolute()
    if binary.is_symlink() or not binary.is_file():
        raise ValueError("PC binary missing or linked")
    info = os.stat(binary)
    if not stat.S_ISREG(info.st_mode) or not (info.st_mode & stat.S_IXUSR):
        raise ValueError("PC binary is not owner-executable")
    if (verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"] or
            _sha_file(binary) != plan["pc_executable_sha256"] or
            _sha_file(owned_game, private=True) != plan["owned_game_image_sha256"]):
        raise ValueError("original PC source, binary or game input differs from plan")
    frame = plan["target_gpu_draw_frame"]
    arguments = tuple(arguments)
    if any(type(arg) is not str or not arg or "\x00" in arg for arg in arguments):
        raise ValueError("invalid PC-port executable argument")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("VH_MAP02_")}
    env.update({
        "VH_MAP02_GPU_CAPTURE_DIR": str(native),
        "VH_MAP02_GPU_CAPTURE_FRAME": str(frame),
        "VH_MAP02_GPU_CAPTURE_WINDOW_COUNT": "2",
        "VH_MAP02_PROBE_OUTPUT_DIR": str(scoped),
        "VH_MAP02_PROBE_FRAME": str(frame),
        "VH_MAP02_PROBE_X": str(x),
        "VH_MAP02_PROBE_Y": str(y),
    })
    process = None
    observed = None
    try:
        process = subprocess.Popen(
            [str(binary), *arguments], shell=False,
            env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True)
        # A very short-lived program may exit before /proc can be sampled.
        # This must fail closed; it is NOT reason to synthesize an observation.
        deadline = time.monotonic() + min(5, timeout)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                candidate = _fingerprint_kernel_exe(process.pid)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                time.sleep(0.01)
                continue
            if candidate == (info.st_dev, info.st_ino,
                             plan["pc_executable_sha256"]):
                observed = candidate
                break
            # During Popen fork->exec, /proc may still point at parent's
            # interpreter. Give exec a small chance to complete.
            time.sleep(0.01)
        if observed is None:
            raise ValueError("kernel child executable identity was not confirmed")
        if process.wait(timeout=timeout) != 0:
            raise ValueError("instrumented PC-port process exited unsuccessfully")
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    if (_sha_file(binary) != plan["pc_executable_sha256"] or
            _sha_file(owned_game, private=True) != plan["owned_game_image_sha256"] or
            verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"] or
            private_file(handoff, PLAN, max_bytes=4096) != plan_raw):
        raise ValueError("original PC executable, owned input or plan changed during run")
    checked = verify_window_scoped_join(native, scoped, target_frame=frame)
    if checked["capture_session_linked"] is not True:
        raise ValueError("original GPU/scoped process session not linked")
    receipt = _validate_receipt({
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "local_plan_sha256": _sha(plan_raw),
        "kernel_observed_executable_sha256": observed[2],
        "kernel_executable_device": observed[0],
        "kernel_executable_inode": observed[1],
        "observed_pid": process.pid,
        "pc_process_exit_code": 0,
        "capture_session_sha256": checked["capture_session_sha256"],
        "native_window_all_files_sha256":
            checked["all_native_window_file_bytes_sha256"],
        "selected_pixel_x": x, "selected_pixel_y": y,
        "kernel_executable_matched_plan": True,
        "same_process_gpu_scoped_nonce_checked": True,
        "game_image_consumption_proven": False,
        "retail_gameplay_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    })
    raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    _publish(handoff, RECEIPT, raw)
    return {
        "private_process_receipt_sha256": _sha(raw),
        "kernel_executable_hash_matched": True,
        "gpu_draws_checked": checked["global_draw_ordinals_checked"],
        "same_process_gpu_scoped_nonce_checked": True,
        "game_image_consumption_proven": False,
        "original_gameplay_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }


def verify_observed_process(handoff_dir, native_dir, scoped_dir, pc_binary,
                            owned_game, *, upstream):
    handoff, native, scoped = (_private_directory(p) for p in
                               (handoff_dir, native_dir, scoped_dir))
    raw = private_file(handoff, RECEIPT, max_bytes=4096)
    receipt = _validate_receipt(raw)
    plan_raw = private_file(handoff, PLAN, max_bytes=4096)
    plan = _validate_plan(plan_raw)
    if (receipt["gpu_draw_frame"] != plan["target_gpu_draw_frame"] or
            receipt["local_plan_sha256"] != _sha(plan_raw) or
            receipt["kernel_observed_executable_sha256"] !=
            plan["pc_executable_sha256"] or
            _sha_file(pc_binary) != plan["pc_executable_sha256"] or
            _sha_file(owned_game, private=True) !=
            plan["owned_game_image_sha256"] or
            verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"]):
        raise ValueError("kernel process receipt differs from local capture plan")
    observed = verify_window_scoped_join(
        native, scoped, target_frame=receipt["gpu_draw_frame"])
    if (receipt["capture_session_sha256"] != observed["capture_session_sha256"] or
            receipt["native_window_all_files_sha256"] !=
            observed["all_native_window_file_bytes_sha256"]):
        raise ValueError("process receipt differs from captured GPU/scoped streams")
    if private_file(handoff, RECEIPT, max_bytes=4096) != raw:
        raise ValueError("process receipt modified during re-verification")
    return {"private_process_receipt_sha256": _sha(raw),
            "kernel_executable_hash_matched": True,
            "same_process_gpu_scoped_nonce_checked": True,
            "game_image_consumption_proven": False,
            "original_gameplay_authenticated": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("run", "verify"))
    p.add_argument("private_handoff_dir", type=Path)
    p.add_argument("private_native_windows", type=Path)
    p.add_argument("private_scoped_capture", type=Path)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--owned-game-image", type=Path, required=True)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--timeout", type=int, default=900)
    a, forwarded = p.parse_known_args()
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    try:
        if a.operation == "run":
            if a.x is None or a.y is None:
                raise ValueError("run requires explicit --x and --y")
            result = launch_observed_pc(
                a.private_handoff_dir, a.private_native_windows,
                a.private_scoped_capture, a.pc_binary, a.owned_game_image,
                upstream=a.upstream_checkout, x=a.x, y=a.y,
                timeout=a.timeout, arguments=forwarded)
        else:
            if forwarded:
                raise ValueError("verify does not accept executable arguments")
            result = verify_observed_process(
                a.private_handoff_dir, a.private_native_windows,
                a.private_scoped_capture, a.pc_binary, a.owned_game_image,
                upstream=a.upstream_checkout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
