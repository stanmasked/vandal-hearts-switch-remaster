#!/usr/bin/env python3
"""Standalone, offline verify-and-extract for the public-only MAP02 Intel kit.

Transfer this trusted source file separately from the downloadable ZIP.
Pass the *inner ZIP* SHA-256 from the pinned GitHub Actions provenance log.
Only standard-library imports. Do not execute or extract an unchecked ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import zipfile

MANIFEST_SCHEMA = "vh.map02.intel-mac.offline-evidence-kit.v1"
PUBLIC = "upstream/platform/pc/src/pc_raster.c"
PUBLIC_GIT_BLOB = "ba8a05d161ad778c0b75e452ff0a11ed163c65cd"
ROOT_FILES = {"README.md", "run-selfcheck.sh", "verify-kit.py", "files.json"}
SOURCE_DIRS = ("tools", "tests", "source")
MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_UNPACKED_BYTES = 6 * 1024 * 1024
MAX_MEMBERS = 190
ZIP_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def allowed_name(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        return False
    p = PurePosixPath(name)
    if (p.is_absolute() or p.as_posix() != name
            or any(part in ("", ".", "..") for part in p.parts)):
        return False
    if name in ROOT_FILES or name == PUBLIC:
        return True
    if len(p.parts) < 2 or p.parts[0] not in SOURCE_DIRS:
        return False
    if p.parts[0] == "tools":
        return p.suffix == ".py"
    if p.parts[0] == "source":
        return p.suffix == ".h"
    return p.suffix == ".py" or name == "tests/test_map02_vram4_frame.c"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def authenticate_zip(archive_path: Path, expected_sha256: str) -> dict:
    """Read & check the archive completely before returning any payload bytes."""
    if not isinstance(expected_sha256, str) or not ZIP_SHA256.fullmatch(expected_sha256):
        raise ValueError("expected inner ZIP SHA-256 must be lowercase 64-digit hex")
    path = Path(archive_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("ZIP source must be an unlinked regular file")
    size = path.stat().st_size
    if not 0 < size <= MAX_ZIP_BYTES:
        raise ValueError("ZIP input exceeds accepted bounds")
    compressed = path.read_bytes()
    if len(compressed) != size:
        raise ValueError("ZIP changed during reading")
    actual_sha = hashlib.sha256(compressed).hexdigest()
    if actual_sha != expected_sha256:
        raise ValueError("downloaded inner ZIP checksum mismatch")

    import io  # standard library; no packaged source imported
    found = {}
    total = 0
    with zipfile.ZipFile(io.BytesIO(compressed), "r") as source:
        members = source.infolist()
        if not 15 <= len(members) <= MAX_MEMBERS:
            raise ValueError("ZIP member count out of range")
        if source.testzip() is not None:
            raise ValueError("ZIP CRC verification failed")
        seen_folded = set()
        for info in members:
            name = info.filename
            if not allowed_name(name) or info.is_dir():
                raise ValueError("unexpected or unsafe ZIP member name")
            lower = name.casefold()
            if name in found or lower in seen_folded:
                raise ValueError("duplicate or case-colliding ZIP entry")
            seen_folded.add(lower)
            # ZIPs from the builder are UNIX regular files only.
            mode = info.external_attr >> 16
            expected_perm = 0o755 if name == "run-selfcheck.sh" else 0o644
            if (
                info.create_system != 3
                or not stat.S_ISREG(mode)
                or stat.S_IMODE(mode) != expected_perm
                or info.compress_type != zipfile.ZIP_DEFLATED
                or info.flag_bits & 0x1
                or info.file_size > MAX_MEMBER_BYTES
            ):
                raise ValueError("ZIP member mode or compression is unsafe")
            data = source.read(info)
            if len(data) != info.file_size:
                raise ValueError("ZIP file metadata and body disagree")
            total += len(data)
            if total > MAX_UNPACKED_BYTES:
                raise ValueError("ZIP uncompressed data exceeds safe limits")
            found[name] = data

    raw_manifest = found.get("files.json")
    if raw_manifest is None:
        raise ValueError("ZIP manifest not present")
    manifest = json.loads(raw_manifest.decode("utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "files", "public_pc_raster_git_blob_sha1",
        "retail_assets_included", "original_gpu_vram_included",
        "private_machine_paths_included", "macos_catalina_runtime_proven",
    }:
        raise ValueError("ZIP manifest fields changed")
    receipts = manifest["files"]
    if not isinstance(receipts, dict) or not 15 <= len(receipts) <= MAX_MEMBERS - 1:
        raise ValueError("ZIP receipt format invalid")
    if (
        manifest["schema"] != MANIFEST_SCHEMA
        or manifest["public_pc_raster_git_blob_sha1"] != PUBLIC_GIT_BLOB
        or any(manifest[k] is not False for k in (
            "retail_assets_included", "original_gpu_vram_included",
            "private_machine_paths_included", "macos_catalina_runtime_proven",
        ))
        or set(receipts) != set(found) - {"files.json"}
        or not {"README.md", "run-selfcheck.sh", "verify-kit.py", PUBLIC}.issubset(receipts)
    ):
        raise ValueError("ZIP contents contradict pinned public-only manifest")
    for name, digest in receipts.items():
        if (
            not allowed_name(name)
            or not isinstance(digest, str)
            or not ZIP_SHA256.fullmatch(digest)
            or hashlib.sha256(found[name]).hexdigest() != digest
        ):
            raise ValueError("ZIP source digest mismatch")
    if git_blob_sha1(found[PUBLIC]) != PUBLIC_GIT_BLOB:
        raise ValueError("PINNED public PC raster Git blob differs")
    return {
        "files": found,
        "sha256": actual_sha,
        "count": len(found),
    }


def verify_and_extract(archive_path: Path, expected_sha256: str,
                       destination: Path) -> dict:
    authenticated = authenticate_zip(archive_path, expected_sha256)
    dest = Path(destination).absolute()
    if dest.name in ("", ".", ".."):
        raise ValueError("destination path invalid")
    parent = dest.parent
    if not parent.is_dir():
        raise ValueError("destination parent missing")
    if parent.is_symlink():
        if not (
            parent == Path("/tmp")
            and parent.resolve(strict=True) == Path("/private/tmp")
        ):
            raise ValueError("destination parent symlink refused")
    # Canonicalize only the parent; an existing destination is refused.
    dest = parent.resolve(strict=True) / dest.name
    if dest.exists() or dest.is_symlink():
        raise ValueError("destination already exists")
    root_created = False
    try:
        dest.mkdir(mode=0o700)
        root_created = True
        for name, data in sorted(authenticated["files"].items()):
            parts = PurePosixPath(name).parts
            path = dest.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(str(path), flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            os.chmod(str(path), 0o755 if name == "run-selfcheck.sh" else 0o644)
    except BaseException:
        if root_created:
            shutil.rmtree(str(dest))
        raise
    return {
        "schema": "vh.map02.intel-mac.preextract-verify.v1",
        "inner_zip_sha256_verified": authenticated["sha256"],
        "validated_files_extracted": authenticated["count"],
        "public_pc_port_pinned": True,
        "raw_ps1_data_read": False,
        "external_network_used": False,
        "catalina_10_15_runtime_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public_only_zip", type=Path)
    parser.add_argument("trusted_inner_zip_sha256")
    parser.add_argument("new_extraction_directory", type=Path)
    args = parser.parse_args()
    try:
        report = verify_and_extract(
            args.public_only_zip,
            args.trusted_inner_zip_sha256,
            args.new_extraction_directory,
        )
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            zipfile.BadZipFile, EOFError):
        parser.error("offline MAP02 ZIP verification or extraction refused")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
