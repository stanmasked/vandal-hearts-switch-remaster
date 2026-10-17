#!/usr/bin/env python3
"""Private source-bound build receipt for an opt-in original MAP02 PC ELF.

This records a *locally* completed build, NOT proof that the resulting ELF
executed or rendered MAP02. The verifier rechecks the complete pinned build
graph, original source, actual ELF bytes/symbols and unmodified 0600 inputs.
Never stores the game image, gameplay bytes, executable or compiler logs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_cycle_make_plan import (
    audit, preflight, BUILD,
)
from tools.check_map02_cycle_elf import audit_cycle_elf
from tools.check_map02_original_font_c import verify_generated_original_font
from tools.check_map02_private_pc_inputs import verify_private_pc_inputs
from tools.map02_local_capture_handoff import _sha_file, verify_pinned_upstream
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_frame_bundle import fields, parse_json

NAME = "map02-full-pc-build-receipt.json"
SCHEMA = "vh.map02.private-source-bound-full-elf.v1"
KEYS = (
    "schema", "pc_executable_sha256",
    "source_bound_make_command_sha256",
    "private_build_inputs_sha256",
    "pinned_original_source_sha256",
    "private_retail_inputs_binding_sha256",
    "required_original_cycle_and_gpu_symbols",
    "full_elf_linked", "actual_gameplay_executed",
    "original_map02_rendering_proven",
    "physical_ps1_equivalence_proven", "hd_substitution_enabled",
)
HEX = set("0123456789abcdef")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _checks(record):
    fields(record, KEYS, NAME)
    if (record["schema"] != SCHEMA or
            record["full_elf_linked"] is not True or
            record["actual_gameplay_executed"] is not False or
            record["original_map02_rendering_proven"] is not False or
            record["physical_ps1_equivalence_proven"] is not False or
            record["hd_substitution_enabled"] is not False):
        raise ValueError("unsupported or overstated private PC build receipt")
    for key in ("pc_executable_sha256", "source_bound_make_command_sha256",
                "private_build_inputs_sha256", "pinned_original_source_sha256",
                "private_retail_inputs_binding_sha256"):
        value = record[key]
        if type(value) is not str or len(value) != 64 or set(value) - HEX:
            raise ValueError("invalid private PC build SHA256: " + key)
    if (type(record["required_original_cycle_and_gpu_symbols"]) is not int or
            record["required_original_cycle_and_gpu_symbols"] <= 0):
        raise ValueError("invalid original CD/GPU observer symbol count")
    return record


def _safe_binary(binary, upstream):
    binary = Path(binary).absolute()
    expected = Path(upstream).absolute() / "platform/pc" / BUILD / "vandalhearts_pc"
    if binary != expected or binary.is_symlink():
        raise ValueError("MAP02 ELF must be the original dedicated build target")
    return binary


def create_build_receipt(report_dir, pc_binary, upstream, bundle,
                         *, build_result, krom_source=None):
    root = _private_directory(report_dir)
    if any(root.iterdir()):
        raise ValueError("MAP02 build report directory must start empty")
    binary = _safe_binary(pc_binary, upstream)
    if type(build_result) is not dict or build_result.get(
            "full_elf_linked") is not True:
        raise ValueError("no confirmed local PC ELF build to record")
    planned = audit(upstream, bundle)
    checked = audit_cycle_elf(binary)
    verify_generated_original_font(upstream, bundle, krom_source=krom_source)
    from tools.check_map02_cycle_make_plan import preflight
    preflight(upstream, bundle)
    from tools.verify_map02_native_gpu_capture import private_file
    manifest_bytes = private_file(
        _private_directory(bundle), "map02_cycle_build_inputs.json",
        max_bytes=8192)
    record = _checks({
        "schema": SCHEMA,
        "pc_executable_sha256": _sha_file(binary),
        "source_bound_make_command_sha256":
            planned["full_game_link_command_sha256"],
        "private_build_inputs_sha256": sha(manifest_bytes),
        "pinned_original_source_sha256": verify_pinned_upstream(upstream),
        "private_retail_inputs_binding_sha256": verify_private_pc_inputs(
            upstream, krom_source=krom_source)["private_build_inputs_binding_sha256"],
        "required_original_cycle_and_gpu_symbols":
            checked["required_symbols_present"],
        "full_elf_linked": True,
        "actual_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
        "hd_substitution_enabled": False,
    })
    for key in ("pc_executable_sha256",
                "source_bound_make_command_sha256",
                "required_original_cycle_and_gpu_symbols",
                "private_retail_inputs_binding_sha256"):
        if record[key] != build_result.get(key):
            raise ValueError("local full ELF build differs from build result: " + key)
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY |
                         getattr(os, "O_NOFOLLOW", 0))
    fd = -1
    try:
        fd = os.open(NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=descriptor)
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            if count <= 0:
                raise ValueError("MAP02 build report was not fully written")
            offset += count
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.fsync(descriptor)
        if private_file(root, NAME, max_bytes=4096) != raw:
            raise ValueError("source-bound private PC build report readback changed")
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(descriptor)
    return {"private_build_receipt_sha256": sha(raw),
            "retail_gameplay_executed": False}


def verify_build_receipt(report_dir, pc_binary, upstream, bundle,
                         *, krom_source=None):
    root = _private_directory(report_dir)
    if {entry.name for entry in root.iterdir()} != {NAME}:
        raise ValueError("private PC build report must contain exactly one receipt")
    binary = _safe_binary(pc_binary, upstream)
    raw = private_file(root, NAME, max_bytes=4096)
    if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError("noncanonical private PC build report")
    record = _checks(parse_json(raw[:-1], NAME))
    canonical = (json.dumps(record, sort_keys=True, separators=(",", ":"))
                 + "\n").encode("utf-8")
    if canonical != raw:
        raise ValueError("noncanonical private PC build bytes")
    planned = audit(upstream, bundle)
    checked = audit_cycle_elf(binary)
    verify_generated_original_font(upstream, bundle, krom_source=krom_source)
    manifest_bytes = private_file(
        _private_directory(bundle), "map02_cycle_build_inputs.json",
        max_bytes=8192)
    actual = {
        "pc_executable_sha256": _sha_file(binary),
        "source_bound_make_command_sha256":
            planned["full_game_link_command_sha256"],
        "private_build_inputs_sha256": sha(manifest_bytes),
        "pinned_original_source_sha256": verify_pinned_upstream(upstream),
        "private_retail_inputs_binding_sha256": verify_private_pc_inputs(
            upstream, krom_source=krom_source)["private_build_inputs_binding_sha256"],
        "required_original_cycle_and_gpu_symbols":
            checked["required_symbols_present"],
    }
    if any(actual[k] != record[k] for k in actual):
        raise ValueError("original MAP02 executable/source differs from built receipt")
    if private_file(root, NAME, max_bytes=4096) != raw:
        raise ValueError("private PC build receipt changed during verification")
    return {"private_build_receipt_sha256": sha(raw),
            "source_pinned_full_elf_bytes_checked": True,
            "retail_gameplay_executed": False,
            "original_map02_rendering_proven": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_build_receipt_directory", type=Path)
    p.add_argument("original_pc_executable", type=Path)
    p.add_argument("pinned_original_checkout", type=Path)
    p.add_argument("prepared_private_bundle", type=Path)
    p.add_argument("--krom-source", type=Path,
                   help="original private KROMDAT.BIN or owned PS1 BIOS")
    a = p.parse_args()
    try:
        result = verify_build_receipt(
            a.private_build_receipt_directory, a.original_pc_executable,
            a.pinned_original_checkout, a.prepared_private_bundle,
            krom_source=a.krom_source)
    except ValueError as exc:
        p.error(str(exc))
    except (OSError, subprocess.TimeoutExpired):
        # OSError and TimeoutExpired can render user-owned argv/paths.
        p.error("private PC build receipt filesystem or command verification failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
