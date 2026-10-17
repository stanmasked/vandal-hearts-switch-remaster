#!/usr/bin/env python3
"""Local-only full PC ELF build from the source-pinned MAP02 cycle Make overlay.

The user's owned retail inputs and decompilation data are required locally.
No game content, compiler log, executable or raw address is uploaded, printed
or written to the GitHub working tree by this script. This does not execute
the game, authenticate a MAP02 frame, or enable HD substitution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_cycle_make_plan import BUILD, audit
from tools.check_map02_cycle_elf import audit_cycle_elf

BINARY_NAME = "vandalhearts_pc"


def build_full_pc(upstream, bundle, *, timeout=1200, make="make", report_dir=None,
                  krom_source=None):
    timeout = int(timeout)
    if not 30 <= timeout <= 7200:
        raise ValueError("full PC link timeout must be between 30 and 7200 seconds")
    upstream, bundle = Path(upstream).absolute(), Path(bundle).absolute()
    planned = audit(upstream, bundle, make=make)
    from tools.check_map02_private_pc_inputs import verify_private_pc_inputs
    original_inputs = verify_private_pc_inputs(upstream, krom_source=krom_source)
    pc = upstream / "platform/pc"
    target = pc / BUILD / BINARY_NAME
    # Fail BEFORE any compiler invocation if this is a prior binary, a
    # symlink or a wrong symlink target. Do not unlink somebody else's file.
    if target.exists() or target.is_symlink():
        raise ValueError("private cycle executable already exists; no replacement allowed")
    command = [
        make, "-j1", "-f", "Makefile", "-f", str(bundle / "map02_cycle.mk"),
        "link", "BUILD_DIR=" + BUILD, "REGION=us",
        "NO_WEBP=1", "NO_HDVIDEO=1",
    ]
    # Use a validated source path only; never trust an inherited font override.
    env = os.environ.copy()
    env.pop("VH_KROM_SOURCE", None)
    env.pop("VH_ALLOW_UNVERIFIED_EXE", None)
    # Original generators consult these environment variables outside GNU
    # Make as well: never accept stale region or an unrelated PS-X EXE.
    env["VH_REGION"] = "us"
    env["VH_PSX_EXE"] = str(upstream / "SLUS_004.47")
    # The private pinned script lives outside upstream and cannot infer the
    # caller's owned KROM path from its own __file__. Set the validated source
    # explicitly even when no --krom-source override was supplied.
    env["VH_KROM_SOURCE"] = str(
        Path(krom_source).absolute() if krom_source is not None else
        upstream / "external/psy-q/3.6/PSYQ/BIN/KROMDAT.BIN")
    try:
        built = subprocess.run(
            command, cwd=pc, env=env, capture_output=True, text=True,
            timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("local source-pinned full PC link exceeded timeout") from exc
    if built.returncode:
        # Compiler stderr may contain paths to private image or EXE, so
        # neither that text nor stdout is returned or logged by this tool.
        raise ValueError("private full PC game link failed; compiler output withheld")
    if target.is_symlink() or not target.is_file():
        raise ValueError("full source-pinned PC link returned without an executable")
    if not target.stat().st_mode & stat.S_IXUSR:
        raise ValueError("built PC ELF does not have owner execute permission")
    verified = audit_cycle_elf(target)
    # Check that the generated overlay did not mutate during the build.
    from tools.check_map02_cycle_make_plan import preflight
    preflight(upstream, bundle)
    if verify_private_pc_inputs(upstream, krom_source=krom_source) != original_inputs:
        raise ValueError("private original US inputs changed during PC build")
    with target.open("rb") as stream:
        h = hashlib.sha256()
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    result = {
        "schema": "vh.map02.private-full-pc-elf-build.v1",
        "pc_executable_sha256": h.hexdigest(),
        "private_retail_inputs_binding_sha256":
            original_inputs["private_build_inputs_binding_sha256"],
        "source_bound_make_command_sha256":
            planned["full_game_link_command_sha256"],
        "required_original_cycle_and_gpu_symbols": verified[
            "required_symbols_present"],
        "full_elf_linked": True,
        "actual_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
        "hd_substitution_enabled": False,
    }
    if report_dir is not None:
        from tools.map02_cycle_build_provenance import create_build_receipt
        receipt = create_build_receipt(
            report_dir, target, upstream, bundle, build_result=result,
            krom_source=krom_source)
        result.update(receipt)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_original_pc_checkout", type=Path)
    p.add_argument("private_prepared_bundle", type=Path)
    p.add_argument("--timeout", type=int, default=1200)
    p.add_argument("--krom-source", type=Path,
                   help="private original PsyQ KROMDAT or owned PS1 BIOS path")
    p.add_argument("--report-dir", required=True, type=Path,
                   help="new empty owned 0700 directory for private ELF build receipt")
    a = p.parse_args()
    try:
        result = build_full_pc(a.pinned_original_pc_checkout,
                               a.private_prepared_bundle,
                               timeout=a.timeout,
                               report_dir=a.report_dir,
                               krom_source=a.krom_source)
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
