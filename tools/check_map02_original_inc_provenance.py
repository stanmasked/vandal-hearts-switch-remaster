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


def _original_blob_sha1(data):
    return hashlib.sha1(
        ("blob %d\\0" % len(data)).encode("ascii") + data
    ).hexdigest()


def check_original_includes(upstream, *, timeout=20):
    upstream = Path(upstream).absolute()
    if upstream.is_symlink() or not upstream.is_dir():
        raise ValueError("original pinned US checkout is unavailable")
    generator = upstream / GENERATOR
    if generator.is_symlink() or not generator.is_file():
        raise ValueError("pinned original include generator missing or linked")
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
        original[name] = path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="vh-map02-checked-inc-") as dirname:
        private = Path(dirname)
        private.chmod(0o700)
        # The generator is checked by git-blob digest BEFORE execution.
        # Suppress both streams to avoid leaking private caller paths/data.
        proc = subprocess.run(
            [sys.executable, "-I", str(generator), str(exe), str(private)],
            capture_output=True, timeout=timeout, check=False,
            env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if proc.returncode:
            raise ValueError("original US include generator refused owned input")
        if {p.name for p in private.iterdir()} != set(FILES):
            raise ValueError("original US generator did not produce three exact includes")
        for name in FILES:
            path = private / name
            if (path.is_symlink() or not path.is_file()
                    or path.stat().st_size > 128 * 1024
                    or path.read_bytes() != original[name]):
                raise ValueError("original generated include differs from owned US EXE: " + name)
    # Verify original private include did not change while generator ran.
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != original[name]:
            raise ValueError("original include changed during regeneration: " + name)
    if _original_blob_sha1(generator.read_bytes()) != GENERATOR_BLOB_SHA1:
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
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
