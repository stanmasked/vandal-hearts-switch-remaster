#!/usr/bin/env python3
"""Build a deterministic, asset-free Intel Mac MAP02 diagnostic ZIP.

The kit includes an AST-closed set of the checked-in Python tools/tests,
locally included C headers, one C frame fixture, and exactly one verified
PUBLIC PC-port raster source file. No user-owned disc, game asset, VRAM,
screenshots or machine-specific absolute paths are included.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from tools.map02_intel_mac_offline_selfcheck import pinned_public_raster
from tools.verify_map02_pc_vram4_equivalence import PINNED_RASTER_BLOB

SCHEMA = "vh.map02.intel-mac.offline-evidence-kit.v1"
PUBLIC_NAME = "upstream/platform/pc/src/pc_raster.c"
FIXTURE = "tests/test_map02_vram4_frame.c"
ENTRY_SCRIPTS = (
    "tools/map02_intel_mac_offline_selfcheck.py",
    "tools/map02_catalina_helper_macho_audit.py",
    "tools/verify_map02_private_pc_native_ft4.py",
)
ENTRY_TESTS = (
    "tests/test_verify_map02_private_timeline_pc_vram4.py",
    "tests/test_verify_map02_private_pc_native_ft4.py",
    "tests/test_map02_private_ft4_cli_contract.py",
    "tests/test_map02_private_ft4_cli_mutations.py",
    "tests/test_map02_intel_mac_offline_selfcheck.py",
    "tests/test_map02_intel_macos_minos.py",
    "tests/test_map02_catalina_helper_macho_audit.py",
)
PACKAGE_DIRS = ("tools", "tests", "source")
MAX_FILES = 180
MAX_SOURCE_BYTES = 4 * 1024 * 1024
INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.M)

RUNNER = """#!/bin/sh
set -eu
cd "$(dirname "$0")"
test -f upstream/platform/pc/src/pc_raster.c
python3 -m tools.map02_intel_mac_offline_selfcheck \
  upstream/platform/pc/src/pc_raster.c --deployment-target 10.15
python3 -m tools.map02_catalina_helper_macho_audit \
  upstream/platform/pc/src/pc_raster.c
"""

README = """# MAP02 offline Intel Mac compatibility kit

This is an asset-free development diagnostic, NOT the Vandal Hearts game,
not a remake release, and not a PlayStation retail source capture.

On an Intel Mac with macOS, Python 3.9+ and Apple Clang / Xcode command
line tools installed, from the extracted directory, run:

    sh run-selfcheck.sh

The script performs synthetic FT4/VRAM and source/native CLI checks,
compiles C helper binaries, and validates their x86_64 Mach-O minimum
deployment target 10.15 and system dylib dependencies. This kit includes
one hash-pinned PUBLIC pc_raster.c from VandalHearts-PcPort. It never
contacts GitHub or downloads private data while running.

The files.json manifest lists every shipped source file and SHA-256.
All paths are relative and intended for local verification. No PS1
BIN/CUE, original proprietary assets, live GPU recordings, or private
owner credentials are packaged.

A green result on macOS 15 Intel does not prove operation on macOS
10.15.7, original game geometry/pixels, or a Nintendo Switch console.
"""


def checked_member(value: str) -> str:
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError("unsafe archive member name")
    p = PurePosixPath(value)
    if (p.as_posix() != value or any(x in ("", ".", "..") for x in p.parts)
            or len(p.parts) < 2 or p.parts[0] not in PACKAGE_DIRS):
        raise ValueError("archive member must stay in approved source roots")
    if p.suffix not in (".py", ".h", ".c"):
        raise ValueError("archive member suffix refused")
    if p.parts[0] == "source" and p.suffix != ".h":
        raise ValueError("only C headers are approved under source/")
    if p.parts[0] == "tests" and p.suffix == ".c" and value != FIXTURE:
        raise ValueError("only reviewed FT4 frame C fixture approved")
    if p.parts[0] == "tools" and p.suffix != ".py":
        raise ValueError("only Python tools are approved")
    return value


def secure_file(root: Path, name: str) -> bytes:
    checked_member(name)
    path = root.joinpath(*PurePosixPath(name).parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError("source path is absent or symlinked")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > 1024 * 1024:
        raise ValueError("source path is not a bounded regular file")
    data = path.read_bytes()
    if b"\0" in data or len(data) != st.st_size:
        raise ValueError("binary or altered source not permitted")
    return data


def _imports(source: str) -> set:
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(x.name for x in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                raise ValueError("relative Python imports are not supported in kit")
            if node.module:
                names.add(node.module)
                if node.module in ("tools", "tests"):
                    names.update(node.module + "." + x.name for x in node.names)
    return names


def _python_module(root: Path, value: str) -> str | None:
    if value.startswith("tools."):
        candidate = "tools/" + value[len("tools."):].replace(".", "/") + ".py"
    elif value.startswith("tests."):
        candidate = "tests/" + value[len("tests."):].replace(".", "/") + ".py"
    elif value.startswith("test_"):
        candidate = "tests/" + value + ".py"
    else:
        return None
    checked_member(candidate)
    file = root / candidate
    if not file.is_file() or file.is_symlink():
        raise ValueError("locally imported test/tool module missing")
    return candidate


def source_closure(root: Path) -> dict:
    root = root.resolve(strict=True)
    pending = list(ENTRY_SCRIPTS + ENTRY_TESTS + (FIXTURE,))
    seen = {}
    while pending:
        name = checked_member(pending.pop())
        if name in seen:
            continue
        data = secure_file(root, name)
        seen[name] = data
        if len(seen) > MAX_FILES or sum(map(len, seen.values())) > MAX_SOURCE_BYTES:
            raise ValueError("source dependency closure exceeds safe limits")
        if name.endswith(".py"):
            for module in sorted(_imports(data.decode("utf-8"))):
                dependency = _python_module(root, module)
                if dependency and dependency not in seen:
                    pending.append(dependency)
        else:
            for include in INCLUDE_RE.findall(data.decode("utf-8")):
                base = PurePosixPath(name).parent
                # Normalize relative includes with a real pathlib join,
                # then enforce that every resolved file is approved.
                resolved = (root / str(base) / include).resolve(strict=True)
                try:
                    rel = resolved.relative_to(root).as_posix()
                except ValueError as exc:
                    raise ValueError("C include escapes approved checkout") from exc
                checked_member(rel)
                if rel not in seen:
                    pending.append(rel)
    return dict(sorted(seen.items()))


def bundle(root: Path, public_raster: Path, destination: Path) -> dict:
    root = Path(root).resolve(strict=True)
    public = pinned_public_raster(public_raster)
    sources = source_closure(root)
    public_bytes = public.read_bytes()
    if b"\0" in public_bytes:
        raise ValueError("unexpected binary public raster")
    payload = dict(sources)
    payload[PUBLIC_NAME] = public_bytes
    file_receipts = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(payload.items())
    }
    manifest = {
        "schema": SCHEMA,
        "files": file_receipts,
        "public_pc_raster_git_blob_sha1": PINNED_RASTER_BLOB,
        "retail_assets_included": False,
        "original_gpu_vram_included": False,
        "private_machine_paths_included": False,
        "macos_catalina_runtime_proven": False,
    }
    payload["files.json"] = (
        json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    payload["README.md"] = README.encode("utf-8")
    payload["run-selfcheck.sh"] = RUNNER.encode("utf-8")
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError("refusing to overwrite existing offline kit")
    if root == destination or root in destination.parents:
        raise ValueError("offline ZIP cannot be created inside source checkout")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("output directory missing or symlinked")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o755 if name == "run-selfcheck.sh" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    return {
        "schema": SCHEMA,
        "packaged_file_count": len(payload),
        "hashed_source_files": len(file_receipts),
        "zip_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "public_source_pinned": True,
        "original_ps1_assets_included": False,
        "private_data_included": False,
        "catalina_runtime_tested": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_public_pc_raster", type=Path)
    parser.add_argument("output_zip", type=Path)
    args = parser.parse_args()
    try:
        result = bundle(Path(__file__).resolve().parent.parent,
                        args.pinned_public_pc_raster, args.output_zip)
    except (OSError, ValueError, UnicodeError, SyntaxError):
        parser.error("MAP02 public-only offline bundle unavailable")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
