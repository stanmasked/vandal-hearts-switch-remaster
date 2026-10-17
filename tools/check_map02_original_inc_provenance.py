#!/usr/bin/env python3
"""Check locally generated original US C initializer includes byte-for-byte.

Run the exact source-pinned *public original* PC include generator on a
user-owned US PS-X EXE in a new private temporary directory, then compare
each generated include with the caller's existing private assets/*.inc.
No input/output bytes, temporary paths, file-specific hashes, or original
code-generated files are published, printed or copied into the git tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

FILES = ("801009bc.inc", "80100e9c.inc", "801012e4.inc")
GENERATOR = "platform/pc/tools/gen_psx_includes.py"
GENERATOR_BLOB_SHA1 = "5d4093dbfdf9aeec6a2d29711eb7b7741b4d98ca"
MAX_OWNED_EXE_BYTES = 8 * 1024 * 1024


def _identity(info):
    # Fail closed on replaced-but-identical inodes and in-place modification.
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _snapshot_exe(exe, private):
    """Copy from an O_NOFOLLOW descriptor, not a mutable path for the child."""
    output = private / "owned-us-exe.snapshot"
    digest = hashlib.sha256()
    try:
        fd = os.open(exe, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as source:
            initial = os.fstat(source.fileno())
            if (not stat.S_ISREG(initial.st_mode)
                    or initial.st_uid != os.geteuid()
                    or initial.st_nlink != 1
                    or not (0x800 < initial.st_size <= MAX_OWNED_EXE_BYTES)):
                raise ValueError("original US executable snapshot metadata invalid")
            with output.open("xb") as dest:
                output.chmod(0o600)
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                    dest.write(block)
            if _identity(os.fstat(source.fileno())) != _identity(initial):
                raise ValueError("original US executable changed during snapshot")
        if _identity(os.stat(exe, follow_symlinks=False)) != _identity(initial):
            raise ValueError("original US executable changed during snapshot")
    except OSError:
        raise ValueError("original US executable cannot be safely snapshotted") from None
    return output, digest.hexdigest(), _identity(initial)


def _verify_exe_unchanged(exe, sha256, identity):
    try:
        if exe.is_symlink() or _identity(exe.stat()) != identity:
            raise ValueError("original US executable changed during regeneration")
        digest = hashlib.sha256()
        with exe.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != sha256 or _identity(exe.stat()) != identity:
            raise ValueError("original US executable changed during regeneration")
    except OSError:
        raise ValueError("original US executable changed during regeneration") from None



def _original_blob_sha1(data):
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data
    ).hexdigest()


def check_original_includes(upstream, *, timeout=20):
    upstream = Path(upstream).absolute()
    if upstream.is_symlink() or not upstream.is_dir():
        raise ValueError("original pinned US checkout is unavailable")
    generator = upstream / GENERATOR
    if generator.is_symlink() or not generator.is_file():
        raise ValueError("pinned original include generator missing or linked")
    generator_identity = _identity(generator.stat())
    source = generator.read_bytes()
    if _original_blob_sha1(source) != GENERATOR_BLOB_SHA1:
        raise ValueError("original include generator differs from pinned source")
    exe = upstream / "SLUS_004.47"
    if exe.is_symlink() or not exe.is_file():
        raise ValueError("original US executable missing or linked")
    root = upstream / "assets"
    if root.is_symlink() or not root.is_dir():
        raise ValueError("original asset include directory missing or linked")
    original = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("original generated include missing or linked: " + name)
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or not (8 <= info.st_size <= 128 * 1024)):
            raise ValueError("original generated include metadata invalid: " + name)
        original[name] = (path.read_bytes(), _identity(info))
        if _identity(path.stat()) != original[name][1]:
            raise ValueError("original include changed during initial read: " + name)
    with tempfile.TemporaryDirectory(prefix="vh-map02-checked-inc-") as dirname:
        private = Path(dirname)
        private.chmod(0o700)
        # Execute an exact byte snapshot of the pinned generator, never its
        # replaceable checkout path. The owned EXE is likewise captured from
        # one verified descriptor and never passed by live path to the child.
        pinned_copy = private / "pinned-generator.py"
        pinned_copy.write_bytes(source)
        pinned_copy.chmod(0o600)
        snapshot, snapshot_hash, exe_identity = _snapshot_exe(exe, private)
        generated = private / "generated"
        generated.mkdir(mode=0o700)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(pinned_copy), str(snapshot), str(generated)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout, check=False,
                env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            # TimeoutExpired.__str__ contains argv with private paths.
            raise ValueError("original US include generation timed out") from None
        except OSError:
            raise ValueError("original US include generator could not launch") from None
        if proc.returncode:
            raise ValueError("original US include generator refused owned input")
        if {p.name for p in generated.iterdir()} != set(FILES):
            raise ValueError("original US generator did not produce three exact includes")
        for name in FILES:
            path = generated / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("original generated include has invalid type: " + name)
            info = path.stat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                    or not (8 <= info.st_size <= 128 * 1024)
                    or path.read_bytes() != original[name][0]):
                raise ValueError("original generated include differs from owned US EXE: " + name)
        _verify_exe_unchanged(exe, snapshot_hash, exe_identity)
    # Detect same-byte replacement as well as in-place content changes.
    for name in FILES:
        path = root / name
        if (path.is_symlink() or not path.is_file()
                or _identity(path.stat()) != original[name][1]
                or path.read_bytes() != original[name][0]
                or _identity(path.stat()) != original[name][1]):
            raise ValueError("original include changed during regeneration: " + name)
    if (generator.is_symlink()
            or _identity(generator.stat()) != generator_identity
            or _original_blob_sha1(generator.read_bytes()) != GENERATOR_BLOB_SHA1
            or _identity(generator.stat()) != generator_identity):
        raise ValueError("original include generator changed during verification")
    return {
        "schema": "vh.map02.original-us-exe-generated-includes.v1",
        "pinned_original_generator_verified": True,
        "asset_includes_regenerated_and_identical": len(FILES),
        "original_user_game_bytes_disclosed": False,
        "complete_original_game_data_proven": False,
        "real_map02_gameplay_observed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_pinned_original_checkout", type=Path)
    a = parser.parse_args()
    try:
        result = check_original_includes(a.private_pinned_original_checkout)
    except ValueError as exc:
        parser.error(str(exc))
    except OSError:
        # OSError may embed paths to user-owned copyrighted input files.
        parser.error("original US include filesystem verification failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
