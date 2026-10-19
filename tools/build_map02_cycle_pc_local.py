#!/usr/bin/env python3
"""Local-only full PC ELF build from the source-pinned MAP02 cycle Make overlay.

The user's owned retail inputs and decompilation data are required locally.
No game content, compiler log, executable or raw address is uploaded, printed
or written to the GitHub working tree by this script. This does not execute
the game, authenticate a MAP02 frame, or enable HD substitution.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_cycle_make_plan import BUILD, audit, clean_make_environment
from tools.check_map02_cycle_elf import audit_cycle_elf
from tools.check_map02_linked_font_elf import stable_owned_elf_sha256
from tools.check_map02_original_font_c import verify_linked_original_font

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
    build_dir = pc / BUILD
    if build_dir.is_symlink():
        raise ValueError("private MAP02 build directory linked or not owner-controlled")
    if not build_dir.exists():
        # Prevent world-readable compilation objects and retail-derived data
        # from ever landing in a freshly created default-mode Make directory.
        build_dir.mkdir(mode=0o700)
    info = build_dir.stat()
    if (not build_dir.is_dir() or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("private MAP02 build directory must be owner 0700")
    folder_identity = (info.st_dev, info.st_ino, info.st_uid,
                       stat.S_IMODE(info.st_mode))
    target = build_dir / BINARY_NAME
    # Fail BEFORE any compiler invocation if this is a prior binary, a
    # symlink or a wrong symlink target. Do not unlink somebody else's file.
    if target.exists() or target.is_symlink():
        raise ValueError("private cycle executable already exists; no replacement allowed")
    font_output = pc / BUILD / "map02_pinned_kanji_font.c"
    font_object = pc / BUILD / "pc_kanji_font.o"
    if font_output.exists() or font_output.is_symlink():
        raise ValueError("private generated KROM source already exists; no replacement allowed")
    # An object with a future timestamp could otherwise bypass compilation
    # of the new pinned font C even though its source file is freshly built.
    if font_object.exists() or font_object.is_symlink():
        raise ValueError("private KROM object already exists; no reuse allowed")
    # This dedicated build MUST begin empty. Otherwise GNU Make may reuse an
    # old object whose timestamp is newer than its freshly prepared source
    # without actually compiling all source-pinned observers. Checking only
    # the resulting ELF symbols cannot independently certify every .o byte.
    # Never delete or overwrite caller-owned files on a reused build attempt.
    if any(build_dir.iterdir()):
        raise ValueError("private MAP02 build directory must be empty before full link")
    command = [
        make, "-j1", "-f", "Makefile", "-f", str(bundle / "map02_cycle.mk"),
        "link", "BUILD_DIR=" + BUILD, "REGION=us",
        "NO_WEBP=1", "NO_HDVIDEO=1",
    ]
    # Use a validated source path only; never trust an inherited font override.
    env = clean_make_environment()
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
    # A successful return is not sufficient if the original owned output
    # directory was replaced while Make was compiling proprietary content.
    if build_dir.is_symlink() or not build_dir.is_dir():
        raise ValueError("private MAP02 build directory replaced during link")
    new_info = build_dir.stat()
    if (new_info.st_dev, new_info.st_ino, new_info.st_uid,
            stat.S_IMODE(new_info.st_mode)) != folder_identity:
        raise ValueError("private MAP02 build directory replaced during link")
    if target.is_symlink() or not target.is_file():
        raise ValueError("full source-pinned PC link returned without an executable")
    if not target.stat().st_mode & stat.S_IXUSR:
        raise ValueError("built PC ELF does not have owner execute permission")
    # Reconstruct the exact 209-glyph output independently of the script that
    # Make executed; reject altered, stale or symlinked generated private C.
    verify_linked_original_font(upstream, bundle, target, krom_source=krom_source)
    verified = audit_cycle_elf(target)
    # Check that the generated overlay did not mutate during the build.
    from tools.check_map02_cycle_make_plan import preflight
    preflight(upstream, bundle)
    if verify_private_pc_inputs(upstream, krom_source=krom_source) != original_inputs:
        raise ValueError("private original US inputs changed during PC build")
    elf_digest = stable_owned_elf_sha256(target)
    result = {
        "schema": "vh.map02.private-full-pc-elf-build.v1",
        "pc_executable_sha256": elf_digest,
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
    except ValueError:
        # Deep source/retail input validation can raise ValueError with a
        # user-owned path or excerpt. Never publish it via command output.
        p.error("private full PC build input or provenance verification failed")
    except OSError:
        # Native file errors may embed owned executable, BIOS or SDK paths.
        p.error("private full PC build filesystem verification failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
