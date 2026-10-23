#!/usr/bin/env python3
"""Build and stage a private, no-media BizHawk 2.11 Linux Octoshock runtime.

This tool is owner-local only. It never accepts or opens a disc, BIOS, BK2,
capture plan, screenshot, or other game data. The resulting runtime is staged
outside the Git checkout and remains unready for gameplay until the separate
private capture protocol passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

UPSTREAM_URL = "https://github.com/TASEmulators/BizHawk.git"
UPSTREAM_COMMIT = "427556b5ef3ac437eba754d90c5e7e9096c9a8df"
UPSTREAM_OCTOSHOCK_TREE = "24f43550ff70776a86a2d7b64d09993dd09021d9"
UPSTREAM_SOURCE_COUNT = 41
BIZHAWK_URL = "https://github.com/TASEmulators/BizHawk/releases/download/2.11/BizHawk-2.11-linux-x64.tar.gz"
BIZHAWK_ARCHIVE_SHA256 = "cdaf9650d880bae660d63a388430f630b8d8a96b1ba59ebf0e0195a645c3bab8"
NATIVE_MODULE_NAME = "liboctoshock.dll.so"
MANIFEST_SCHEMA = "vh.map02.owner-local-runtime.v1"
PATCH_NAMES = (
    "posix-export.patch",
    "posix-header-order.patch",
    "posix-deinterlacer-include.patch",
    "posix-local-buffer.patch",
)
REQUIRED_TOOLS = (
    "git", "cmake", "c++", "make", "curl", "tar", "file", "readelf",
    "nm", "ldd", "dotnet", "mono", "mcs", "xvfb-run", "timeout",
)


class OwnerStageError(RuntimeError):
    """A safe, user-facing failure in the owner-local runtime staging path."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _has_git_ancestor(path: Path) -> bool:
    current = Path(path).resolve(strict=True)
    for parent in (current, *current.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_symlink():
            return True
    return False


def resolve_output_root(value: Path, checkout_root: Path) -> Path:
    """Require a new absolute output directory outside every Git checkout."""
    raw = Path(value)
    if not raw.is_absolute() or raw.is_symlink() or raw.exists():
        raise ValueError("output root must be an absolute, nonexistent ordinary path")
    parent = raw.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("output root parent must be an existing ordinary directory")
    resolved_parent = parent.resolve(strict=True)
    candidate = resolved_parent / raw.name
    checkout = Path(checkout_root).resolve(strict=True)
    if candidate == checkout or checkout in candidate.parents:
        raise ValueError("owner runtime output must be outside the Git checkout")
    if _has_git_ancestor(resolved_parent):
        raise ValueError("owner runtime output must not be under a Git checkout")
    if candidate.exists() or candidate.is_symlink():
        raise ValueError("owner runtime output already exists; refusing overwrite")
    return candidate


def validate_tar_members(members: Iterable[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    """Reject unsafe paths, links, devices and duplicate normalized archive paths."""
    safe: list[tarfile.TarInfo] = []
    seen: set[str] = set()
    for member in members:
        if not isinstance(member.name, str) or not member.name:
            raise ValueError("official archive contains an empty member name")
        original = PurePosixPath(member.name)
        normalized = posixpath.normpath(member.name)
        path = PurePosixPath(normalized)
        if original.is_absolute() or path.is_absolute() or ".." in original.parts or ".." in path.parts:
            raise ValueError("official archive contains a path traversal member")
        if normalized in ("", "."):
            if member.isdir():
                continue
            raise ValueError("official archive contains an invalid root member")
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise ValueError("official archive contains a link or special file")
        if not (member.isdir() or member.isfile()):
            raise ValueError("official archive contains an unsupported member type")
        if normalized in seen:
            raise ValueError("official archive contains duplicate normalized paths")
        seen.add(normalized)
        member.name = normalized
        safe.append(member)
    return safe


def safe_extract_archive(archive_path: Path, destination: Path) -> None:
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("archive extraction destination must not already exist")
    destination.mkdir(mode=0o700, parents=True)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = validate_tar_members(archive.getmembers())
            archive.extractall(destination, members=members)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def find_bizhawk_root(extracted_root: Path) -> Path:
    """Find exactly one usable official BizHawk root in the extracted archive."""
    root = Path(extracted_root).resolve(strict=True)
    candidates = [
        item for item in root.rglob("EmuHawk.exe")
        if item.is_file() and not item.is_symlink()
    ]
    if len(candidates) != 1:
        raise ValueError("official archive must contain exactly one regular EmuHawk.exe")
    runtime = candidates[0].parent.resolve(strict=True)
    required = (
        runtime / "EmuHawk.exe",
        runtime / "EmuHawkMono.sh",
        runtime / "dll" / "BizHawk.Client.Common.dll",
        runtime / "dll" / "BizHawk.Emulation.Common.dll",
        runtime / "dll" / "BizHawk.Emulation.Cores.dll",
    )
    for path in required:
        if path.is_symlink() or not path.is_file():
            raise ValueError("official BizHawk runtime is missing a required regular file")
    if not runtime.is_relative_to(root):
        raise ValueError("official BizHawk runtime root escapes the extracted archive")
    return runtime


def _run(
    argv: Iterable[str | Path],
    *,
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [str(item) for item in argv]
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\nCOMMAND FAILURE: " + Path(command[0]).name + "\n")
            log.write(type(exc).__name__ + "\n")
        raise OwnerStageError("owner-local runtime build command could not complete") from None
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\nCOMMAND: " + Path(command[0]).name + "\n")
        log.write(result.stdout or "")
        if result.stdout and not result.stdout.endswith("\n"):
            log.write("\n")
        log.write("EXIT: " + str(result.returncode) + "\n")
    if check and result.returncode != 0:
        raise OwnerStageError(
            "owner-local runtime build failed in " + Path(command[0]).name
            + "; the private local work log was retained"
        )
    return result


def _require_tools() -> None:
    missing = [name for name in REQUIRED_TOOLS if shutil.which(name) is None]
    if missing:
        raise OwnerStageError(
            "Linux x86_64 runtime staging requires build tools that are not installed: "
            + ", ".join(missing)
        )
    if not sys.platform.startswith("linux") or platform.machine().lower() not in ("x86_64", "amd64"):
        raise OwnerStageError("owner-local staging currently supports Linux x86_64 only")


def _tool_version(name: str) -> str:
    options = {
        "git": ["git", "--version"],
        "cmake": ["cmake", "--version"],
        "c++": ["c++", "--version"],
        "dotnet": ["dotnet", "--version"],
        "mono": ["mono", "--version"],
        "mcs": ["mcs", "--version"],
        "python": [sys.executable, "--version"],
    }.get(name, [name, "--version"])
    try:
        result = subprocess.run(
            options, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", shell=False, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    first = (result.stdout or "").splitlines()
    return first[0][:160] if first else "version-unavailable"


def _audit_native_module(
    library: Path,
    upstream: Path,
    repo_root: Path,
    log_path: Path,
) -> int:
    file_output = _run(["file", library], cwd=repo_root, log_path=log_path).stdout
    header = _run(["readelf", "-h", library], cwd=repo_root, log_path=log_path).stdout
    if "ELF 64-bit" not in file_output or "x86-64" not in file_output.lower():
        raise OwnerStageError("built native module is not an ELF64 x86_64 shared library")
    if "ELF64" not in header or "X86-64" not in header.upper():
        raise OwnerStageError("native module ELF header does not identify x86_64")

    export_text = _run(
        ["nm", "-D", "--defined-only", library], cwd=repo_root, log_path=log_path
    ).stdout
    exports = {line.split()[-1] for line in export_text.splitlines() if line.split()}
    managed_dir = upstream / "src/BizHawk.Emulation.Cores/Consoles/Sony/PSX"
    bindings_path = managed_dir / "OctoshockDll.cs"
    if not bindings_path.is_file():
        raise OwnerStageError("pinned upstream managed Octoshock declarations are missing")
    bindings = bindings_path.read_text(encoding="utf-8")
    declared = set(re.findall(
        r"public static extern [^ ]+ (shock_[A-Za-z0-9_]+)\(", bindings
    ))
    referenced: set[str] = set()
    for source in managed_dir.rglob("*.cs"):
        referenced.update(re.findall(
            r"OctoshockDll\.(shock_[A-Za-z0-9_]+)\(",
            source.read_text(encoding="utf-8", errors="replace"),
        ))
    if not declared or referenced - declared:
        raise OwnerStageError("managed Octoshock call/declaration set is inconsistent")

    known_path = repo_root / "tools/map02_linux_octoshock/known-unimplemented-managed-imports.txt"
    known_lines = [line.strip() for line in known_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if known_lines != sorted(set(known_lines)) or len(known_lines) != 1:
        raise OwnerStageError("pinned unimplemented-import exception list changed")
    known = set(known_lines)
    native_sources = upstream / "psx/octoshock"
    native_text = "\n".join(
        source.read_text(encoding="utf-8", errors="replace")
        for source in native_sources.rglob("*")
        if source.is_file() and source.suffix.lower() in (".h", ".cpp")
    )
    for symbol in known:
        if symbol in referenced or symbol in native_text or symbol in exports:
            raise OwnerStageError("pinned unimplemented-import exception is no longer valid")
    required = declared - known
    if not required or required - exports:
        raise OwnerStageError("native module is missing a required managed P/Invoke export")

    dependency_check = _run(
        ["ldd", "-r", library], cwd=repo_root, log_path=log_path, check=False
    )
    if dependency_check.returncode != 0 or re.search(
        r"undefined symbol|not found", dependency_check.stdout, re.IGNORECASE
    ):
        raise OwnerStageError("native module has unresolved runtime dependencies")
    return len(required)


def _find_mono_reference_paths() -> tuple[Path, Path]:
    mono_root = Path("/usr/lib/mono")
    if not mono_root.is_dir():
        raise OwnerStageError("Mono API reference directories are unavailable")
    posix_candidates = sorted(
        path for path in mono_root.rglob("Mono.Posix.dll")
        if "/4.5-api/" in path.as_posix() and path.is_file() and not path.is_symlink()
    )
    netstandard = Path("/usr/lib/mono/4.8-api/Facades/netstandard.dll")
    if not posix_candidates or not netstandard.is_file() or netstandard.is_symlink():
        raise OwnerStageError("Mono.Posix or netstandard reference assembly is unavailable")
    return posix_candidates[0], netstandard


def _build_witness_plugin(
    repo_root: Path,
    runtime_root: Path,
    workdir: Path,
    log_path: Path,
) -> Path:
    source = repo_root / "tools/map02_runtime_core_witness"
    copied_source = workdir / "witness-project"
    shutil.copytree(
        source,
        copied_source,
        ignore=shutil.ignore_patterns("bin", "obj", ".git", "__pycache__"),
    )
    posix, netstandard = _find_mono_reference_paths()
    output = workdir / "witness-bin"
    intermediate = workdir / "witness-obj"
    output.mkdir(mode=0o700)
    intermediate.mkdir(mode=0o700)
    env = os.environ.copy()
    env["FrameworkPathOverride"] = "/usr/lib/mono/4.8-api"
    _run(
        [
            "dotnet", "build", copied_source / "VhMap02CoreWitness.csproj",
            "-c", "Release", "--nologo", "-v:minimal",
            "-p:VH_BIZHAWK_RELEASE_ROOT=" + str(runtime_root),
            "-p:VH_MAP02_UNIX_BUILD=true",
            "-p:VH_MONO_POSIX_PATH=" + str(posix),
            "-p:VH_MONO_NETSTANDARD_PATH=" + str(netstandard),
            "-p:BaseOutputPath=" + str(output) + os.sep,
            "-p:BaseIntermediateOutputPath=" + str(intermediate) + os.sep,
            "-p:MSBuildProjectExtensionsPath=" + str(intermediate) + os.sep,
        ],
        cwd=copied_source,
        env=env,
        log_path=log_path,
        timeout=600,
    )
    candidates = sorted(output.rglob("VhMap02CoreWitness.dll"))
    if len(candidates) != 1 or not candidates[0].is_file() or candidates[0].is_symlink():
        raise OwnerStageError("owner witness External Tool DLL was not built exactly once")
    return candidates[0]


def _smoke_test_runtime(
    repo_root: Path,
    runtime_root: Path,
    build_dir: Path,
    workdir: Path,
    log_path: Path,
) -> None:
    mono_env = os.environ.copy()
    mono_env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(runtime_root / "dll"), str(runtime_root), "/usr/lib/x86_64-linux-gnu"]
    )
    mono_env["MONO_CRASH_NOFILE"] = "1"
    mono_env["MONO_WINFORMS_XIM_STYLE"] = "disabled"

    abi_exe = workdir / "octoshock-abi-smoke.exe"
    _run(
        ["mcs", "-out:" + str(abi_exe), repo_root / "tools/map02_linux_octoshock/abi_smoke.cs"],
        cwd=repo_root, log_path=log_path,
    )
    abi_env = os.environ.copy()
    abi_env["LD_LIBRARY_PATH"] = str(build_dir) + os.pathsep + abi_env.get("LD_LIBRARY_PATH", "")
    _run(["mono", abi_exe], cwd=repo_root, env=abi_env, log_path=log_path)

    _, netstandard = _find_mono_reference_paths()
    binding_exe = workdir / "official-bizhawk-octoshock-binding-smoke.exe"
    _run(
        [
            "mcs", "-unsafe", "-r:" + str(netstandard),
            "-r:" + str(runtime_root / "dll/BizHawk.Emulation.Cores.dll"),
            "-r:" + str(runtime_root / "dll/BizHawk.Emulation.Common.dll"),
            "-out:" + str(binding_exe),
            repo_root / "tools/map02_linux_octoshock/official_managed_binding_smoke.cs",
        ],
        cwd=repo_root, log_path=log_path,
    )
    binding_env = dict(mono_env)
    binding_env["MONO_PATH"] = str(runtime_root / "dll")
    _run(["mono", binding_exe], cwd=repo_root, env=binding_env, log_path=log_path)

    private_home = workdir / "emuhawk-home"
    private_home.mkdir(mode=0o700)
    smoke_env = dict(mono_env)
    smoke_env["HOME"] = str(private_home)
    _run(
        [
            "timeout", "45s", "xvfb-run", "-a",
            runtime_root / "EmuHawkMono.sh", "--help",
        ],
        cwd=runtime_root,
        env=smoke_env,
        log_path=log_path,
        timeout=60,
    )


def _write_runtime_records(
    runtime_root: Path,
    *,
    core_hash: str,
    native_hash: str,
    witness_hash: str,
    archive_hash: str,
    export_count: int,
    log_path: Path,
    workdir: Path,
    stage_root: Path,
    output_root: Path,
    keep_workdir: bool,
) -> None:
    module_paths = sorted(
        path.relative_to(runtime_root).as_posix()
        for path in runtime_root.rglob(NATIVE_MODULE_NAME)
        if path.is_file() and not path.is_symlink()
    )
    if not module_paths:
        raise OwnerStageError("staged native module was not found in runtime")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "project": "Vandal Hearts Remake — MAP02",
        "source": {
            "repository": UPSTREAM_URL,
            "commit": UPSTREAM_COMMIT,
            "octoshock_tree": UPSTREAM_OCTOSHOCK_TREE,
            "source_file_count": UPSTREAM_SOURCE_COUNT,
        },
        "official_bizhawk": {
            "version": "2.11",
            "archive_url": BIZHAWK_URL,
            "archive_sha256": archive_hash,
            "core_assembly_sha256": core_hash,
        },
        "native_octoshock": {
            "filename": NATIVE_MODULE_NAME,
            "sha256": native_hash,
            "managed_exports_verified": export_count,
            "installed_relative_paths": module_paths,
        },
        "experimental_witness_plugin": {
            "filename": "ExternalTools/VhMap02CoreWitness.dll",
            "sha256": witness_hash,
        },
        "smoke_tests": {
            "native_abi": "pass",
            "official_managed_binding_synthetic_firmware": "pass",
            "emuhawk_no_media_startup": "pass",
        },
        "game_media_used": False,
        "bios_used": False,
        "bk2_used": False,
        "game_loaded": False,
        "psx_capture_ready": False,
        "capture_readiness_note": "Build and no-media smoke only; a private two-cold-launch MAP02 audit is still required.",
        "workdir_retained": keep_workdir,
    }
    manifest_path = runtime_root / "map02-owner-runtime-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)

    pins = (
        "export VH_MAP02_CORE_EXPECTED_CORE_ASSEMBLY_SHA256=" + core_hash + "\n"
        "export VH_MAP02_CORE_EXPECTED_NATIVE_MODULE_SHA256=" + native_hash + "\n"
        "export VH_MAP02_PRIVATE_WITNESS_DLL_SHA256=" + witness_hash + "\n"
        "export VH_MAP02_CORE_EXPECTED_DLL_SHA256=" + witness_hash + "\n"
    )
    pins_path = runtime_root / "map02-owner-runtime-pins.env"
    pins_path.write_text(pins, encoding="ascii")
    os.chmod(pins_path, 0o600)

    readme = (
        "OWNER-LOCAL MAP02 RUNTIME — BIZHAWK 2.11 LINUX X86_64\n"
        "This directory contains a checksum-verified official BizHawk 2.11 runtime, "
        "a source-built Octoshock module and the experimental core-witness External Tool.\n"
        "The build and smoke tests used no disc, BIOS, BK2 or gameplay data. "
        "This runtime is NOT evidence that PSX boot or MAP02 capture works.\n"
        "Keep this directory owner-private. Never upload it or its binaries to public GitHub.\n"
        "Runtime pins and build provenance are in map02-owner-runtime-manifest.json "
        "and map02-owner-runtime-pins.env.\n"
        "Use the repository's private capture launcher only after direct BIN identity, "
        "CUE/BIN identity and the BK2-matched BIOS have been verified.\n"
        "Before private capture, re-run the owner-local integrity verifier against "
        "this directory. Never interpret its PASS as gameplay proof.\n"
    )
    (runtime_root / "README-MAP02-OWNER-RUNTIME.txt").write_text(readme, encoding="utf-8")
    os.chmod(runtime_root / "README-MAP02-OWNER-RUNTIME.txt", 0o600)

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    for original, replacement in (
        (str(workdir), "<WORKDIR>"),
        (str(stage_root), "<STAGED_RUNTIME>"),
        (str(output_root), "<OWNER_RUNTIME>"),
        (str(Path.home()), "<HOME>"),
    ):
        log_text = log_text.replace(original, replacement)
    build_log = runtime_root / "map02-owner-runtime-build.log"
    build_log.write_text(log_text, encoding="utf-8")
    os.chmod(build_log, 0o600)


def build_and_stage(output_value: Path, *, keep_workdir: bool = False) -> dict[str, object]:
    _require_tools()
    repo_root = Path(__file__).resolve().parents[2]
    output_root = resolve_output_root(output_value, repo_root)
    workdir = output_root.with_name(output_root.name + ".work")
    if workdir.exists() or workdir.is_symlink():
        raise ValueError("owner build work directory already exists; refusing overwrite")
    if _has_git_ancestor(output_root.parent):
        raise ValueError("owner runtime output parent must be outside a Git checkout")
    workdir.mkdir(mode=0o700)
    log_path = workdir / "map02-owner-runtime-build.log"
    log_path.write_text("MAP02 owner-local runtime build log; no game media is accepted by this tool.\n", encoding="utf-8")
    os.chmod(log_path, 0o600)
    stage_root: Path | None = None
    succeeded = False
    try:
        upstream = workdir / "bizhawk-upstream"
        _run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", UPSTREAM_URL, upstream],
            cwd=repo_root, log_path=log_path, timeout=600,
        )
        _run(["git", "-C", upstream, "checkout", "--detach", UPSTREAM_COMMIT],
             cwd=repo_root, log_path=log_path, timeout=300)
        actual_commit = _run(["git", "-C", upstream, "rev-parse", "HEAD"],
                             cwd=repo_root, log_path=log_path).stdout.strip()
        actual_tree = _run(["git", "-C", upstream, "rev-parse", "HEAD:psx/octoshock"],
                           cwd=repo_root, log_path=log_path).stdout.strip()
        if actual_commit != UPSTREAM_COMMIT or actual_tree != UPSTREAM_OCTOSHOCK_TREE:
            raise OwnerStageError("pinned upstream source identity mismatch")
        _run(
            [sys.executable, repo_root / "tools/map02_linux_octoshock/verify_source_manifest.py",
             "--source-root", upstream],
            cwd=repo_root, log_path=log_path,
        )

        for patch_name in PATCH_NAMES:
            patch = repo_root / "tools/map02_linux_octoshock" / patch_name
            _run(["git", "-C", upstream, "apply", "--ignore-space-change", "--check", patch],
                 cwd=repo_root, log_path=log_path)
            _run(["git", "-C", upstream, "apply", "--ignore-space-change", patch],
                 cwd=repo_root, log_path=log_path)
        _run(
            [
                sys.executable,
                repo_root / "tools/map02_linux_octoshock/apply_posix_compiler_sanity.py",
                upstream / "psx/octoshock/emuware/emuware.h",
            ],
            cwd=repo_root, log_path=log_path,
        )

        build_dir = workdir / "octoshock-build"
        _run(
            [
                "cmake", "-S", repo_root / "tools/map02_linux_octoshock",
                "-B", build_dir, "-DCMAKE_BUILD_TYPE=Release",
                "-DOCTOSH_SOURCE_DIR=" + str(upstream / "psx/octoshock"),
            ],
            cwd=repo_root, log_path=log_path,
        )
        _run(["cmake", "--build", build_dir, "--parallel", "2"],
             cwd=repo_root, log_path=log_path, timeout=900)
        library = build_dir / NATIVE_MODULE_NAME
        if not library.is_file() or library.is_symlink():
            raise OwnerStageError("native Octoshock build output is missing")
        native_hash = sha256_file(library)
        export_count = _audit_native_module(library, upstream, repo_root, log_path)

        archive = workdir / "BizHawk-2.11-linux-x64.tar.gz"
        _run(
            [
                "curl", "--fail", "--location", "--silent", "--show-error",
                BIZHAWK_URL, "--output", archive,
            ],
            cwd=repo_root, log_path=log_path, timeout=600,
        )
        archive_hash = sha256_file(archive)
        if archive_hash != BIZHAWK_ARCHIVE_SHA256:
            raise OwnerStageError("official BizHawk 2.11 archive SHA-256 mismatch")
        extracted = workdir / "official-bizhawk-extracted"
        safe_extract_archive(archive, extracted)
        official_root = find_bizhawk_root(extracted)

        stage_root = Path(tempfile.mkdtemp(
            prefix="." + output_root.name + ".staging-",
            dir=str(output_root.parent),
        ))
        os.chmod(stage_root, 0o700)
        shutil.copytree(official_root, stage_root, dirs_exist_ok=True, symlinks=False)
        # copytree copies the upstream root's mode onto the existing destination.
        # Restore the owner-only directory boundary before any DLL is staged.
        os.chmod(stage_root, 0o700)
        if (stage_root / "EmuHawk.exe").is_symlink():
            raise OwnerStageError("staged EmuHawk.exe unexpectedly became a symlink")
        core_assemblies = sorted(
            path for path in stage_root.rglob("BizHawk.Emulation.Cores.dll")
            if path.is_file() and not path.is_symlink()
        )
        if not core_assemblies:
            raise OwnerStageError("staged official BizHawk core assembly is missing")
        core_hashes = {sha256_file(path) for path in core_assemblies}
        if len(core_hashes) != 1:
            raise OwnerStageError("official BizHawk core assembly copies differ")
        core_hash = next(iter(core_hashes))

        module_paths: list[Path] = []
        for assembly in core_assemblies:
            directory = assembly.parent
            target = directory / NATIVE_MODULE_NAME
            if target.exists() or target.is_symlink():
                raise OwnerStageError("refusing to overwrite an existing native module")
            shutil.copyfile(library, target)
            os.chmod(target, 0o755)
            if sha256_file(target) != native_hash:
                raise OwnerStageError("staged native module checksum mismatch")
            module_paths.append(target)

        witness_source = _build_witness_plugin(repo_root, stage_root, workdir, log_path)
        external_tools = stage_root / "ExternalTools"
        if external_tools.is_symlink():
            raise OwnerStageError("ExternalTools directory must not be a symlink")
        external_tools.mkdir(mode=0o755, exist_ok=True)
        witness_target = external_tools / "VhMap02CoreWitness.dll"
        if witness_target.exists() or witness_target.is_symlink():
            raise OwnerStageError("refusing to overwrite an existing witness plugin")
        shutil.copyfile(witness_source, witness_target)
        os.chmod(witness_target, 0o644)
        witness_hash = sha256_file(witness_target)

        _smoke_test_runtime(repo_root, stage_root, build_dir, workdir, log_path)
        _write_runtime_records(
            stage_root,
            core_hash=core_hash,
            native_hash=native_hash,
            witness_hash=witness_hash,
            archive_hash=archive_hash,
            export_count=export_count,
            log_path=log_path,
            workdir=workdir,
            stage_root=stage_root,
            output_root=output_root,
            keep_workdir=keep_workdir,
        )
        # Fail closed before promotion if stored hashes, mode or no-media
        # state differ from the independently checked manifest.
        _run(
            [sys.executable,
             repo_root / "tools/map02_linux_octoshock/verify_owner_runtime.py",
             stage_root],
            cwd=repo_root, log_path=log_path,
        )
        os.replace(stage_root, output_root)
        stage_root = None
        succeeded = True
        manifest = json.loads((output_root / "map02-owner-runtime-manifest.json").read_text(encoding="utf-8"))
        return manifest
    finally:
        if stage_root is not None:
            shutil.rmtree(stage_root, ignore_errors=True)
        if succeeded and not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and stage a private no-media BizHawk 2.11 Linux x86_64 Octoshock runtime."
    )
    parser.add_argument(
        "--output-root", required=True, type=Path,
        help="new absolute runtime directory outside every Git checkout; it must not already exist",
    )
    parser.add_argument(
        "--keep-workdir", action="store_true",
        help="retain the private build work directory for local diagnosis; never commit it",
    )
    args = parser.parse_args()
    try:
        manifest = build_and_stage(args.output_root, keep_workdir=args.keep_workdir)
    except (OSError, ValueError, OwnerStageError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print("VH_MAP02_OWNER_RUNTIME_STAGE_FAILED media_used=0 capture_ready=0")
        print("Reason: " + str(exc), file=sys.stderr)
        return 1
    print(
        "VH_MAP02_OWNER_RUNTIME_STAGE_PASS "
        "native_module_sha256=" + str(manifest["native_octoshock"]["sha256"]) + " "
        "core_assembly_sha256=" + str(manifest["official_bizhawk"]["core_assembly_sha256"]) + " "
        "witness_plugin_sha256=" + str(manifest["experimental_witness_plugin"]["sha256"]) + " "
        "game_media_used=0 capture_ready=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
