#!/usr/bin/env python3
"""Private static ELF readiness check for MAP02 GPU/FT4/PutPixel instrumentation.

A prelaunch *hint*: exact nm symbols and second-coordinate C environment
literals must exist in the same ELF. Neither their presence nor an SHA proves
that the probe executes or that native journal data comes from the game.
No bytes/paths/game resources are uploaded or printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from tools.preflight_map02_private_dda_capture import _executable_fingerprint
from tools.map02_linux_elf_process_image import require_elf_image

REQUIRED_SYMBOLS = frozenset((
    "VH_CaptureEvent", "VH_Map02PixelScopeSet",
    "VH_Map02PixelScopeClear", "VH_PixelSampleRecord",
))
SECOND_COORDINATE_SELECTORS = (
    b"VH_MAP02_PUTPIXEL_X2\x00", b"VH_MAP02_PUTPIXEL_Y2\x00",
)
_SYM = re.compile(r"^[0-9A-Fa-f]*\s+([TtWw])\s+(VH_[A-Za-z0-9_]+)$")


def inspect_binary(path, *, nm="nm"):
    path = Path(path).absolute()
    before = _executable_fingerprint(path)
    # Check on a single open file descriptor; os.pread does not seek.
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(path, flags)
    try:
        require_elf_image(fd)
        # For tests and stripped ELF, this scans bounded file contents.
        # A string's presence is NEVER sufficient evidence of code behavior.
        size = before["executable_bytes"]
        if size > 1024 * 1024 * 1024:
            raise ValueError("private executable exceeds limit")
        payload = bytearray()
        while len(payload) < size:
            data = os.read(fd, min(1024 * 1024, size - len(payload)))
            if not data:
                raise ValueError("private ELF changed while inspecting")
            payload.extend(data)
        if hashlib.sha256(payload).hexdigest() != before["executable_sha256"]:
            raise ValueError("private ELF SHA changed while inspecting")
        coordinate_selectors = all(item in payload for item in SECOND_COORDINATE_SELECTORS)
        del payload
        # Never invoke the executable. nm reads ELF metadata only. No shell.
        nm_path = shutil.which(nm)
        if not nm_path:
            raise ValueError("required native ELF symbol inspector nm unavailable")
        try:
            result = subprocess.run(
                [nm_path, "-a", "--defined-only", str(path)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=20, check=False,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("native ELF symbol inspection unavailable") from exc
        if result.returncode != 0 or len(result.stdout) > 8 * 1024 * 1024:
            raise ValueError("native ELF symbol table unavailable or stripped")
        defined = set()
        for line in result.stdout.splitlines():
            match = _SYM.fullmatch(line.strip())
            if match:
                defined.add(match.group(2))
        matching = REQUIRED_SYMBOLS & defined
        if (len(matching) != len(REQUIRED_SYMBOLS) or
                not coordinate_selectors):
            raise ValueError("required native GPU/FT4/two-word PutPixel probe evidence missing")
        # One more exact SHA check catches pathname replacement by the time
        # nm ran. The actual launch has its own separate pinned FD check.
        after = _executable_fingerprint(path)
        if after != before:
            raise ValueError("private ELF executable changed during symbol inspection")
        return {
            "schema": "vh.map02.private-pc-elf-static-readiness.v1",
            "executable_sha256": before["executable_sha256"],
            "required_probe_symbols_checked": len(REQUIRED_SYMBOLS),
            "required_probe_symbols_present": True,
            "second_coordinate_selectors_present": True,
            "static_probe_readiness_only": True,
            "native_probes_executed": False,
            "original_pc_port_authenticated": False,
            "retail_map02_gameplay_authenticated": False,
            "native_process_to_gpu_log_causality_authenticated": False,
            "switch_rendering_verified": False,
            "hd_replacement_authorized": False,
        }
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_elf_executable", type=Path)
    args = parser.parse_args()
    try:
        result = inspect_binary(args.private_elf_executable)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
