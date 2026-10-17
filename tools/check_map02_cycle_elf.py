#!/usr/bin/env python3
"""Fail closed when a requested full MAP02 cycle ELF lacks original hooks.

Checks the *actual locally selected executable* for the original CD/GPU
entrypoints and every required cycle/VRAM/BlendG1 observer. This is only
a structural binary audit: exported symbols are NOT a proof of their
implementation, actual game execution, original image, or PS1 equivalence.
Works with Linux ELF executables only, never relinkable .o files.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess

# The original 209-glyph KROM-to-C source must be represented by a
# file-backed initialized DATA symbol in the final ELF, not only in a
# planned/compiled intermediate object or an uninitialized BSS placeholder.
ORIGINAL_FONT_DATA_SYMBOLS = {"pc_kanji_charset2": 209 * 30}

SYMBOLS = (
    "LoadCdFile",
    "ContinueLoadingCdFile",
    "CdRead",
    "DrawOTag",
    "vh_map02_cycle_load",
    "vh_map02_cycle_read_start",
    "vh_map02_cycle_read_finish",
    "vh_map02_cycle_loader_complete",
    "vh_map02_cycle_draw_start",
    "vh_map02_cycle_draw_finish",
    "vh_map02_capture_session_token",
    "vh_map02_cd_loader_claim",
    "vh_map02_cd_probe_format_jsonl",
    "vh_map02_scope_begin_frame",
    "vh_map02_probe_begin",
    "vh_map02_probe_blendg1",
    "vh_map02_probe_end",
    "vh_map02_edges_begin_frame",
    "vh_map02_stage_private_pair",
)

def _run(exe, path):
    command = (["readelf", "-h", str(path)] if exe == "readelf"
               else ["nm", "-g", "-S", "--defined-only", "--", str(path)])
    result = subprocess.run(
        command,
        capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise ValueError("MAP02 ELF introspection failed: " + exe)
    return result.stdout

def audit_cycle_elf(path):
    binary = Path(path).absolute()
    if binary.is_symlink() or not binary.is_file():
        raise ValueError("MAP02 cycle binary missing or symlinked")
    st = binary.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or
            not (st.st_mode & stat.S_IXUSR) or st.st_size < 256):
        raise ValueError("MAP02 cycle input is not an owned executable")
    # Reject ET_REL: partial ld -r links are not runnable evidence.
    header = _run("readelf", binary)
    if not re.search(r"^\s*Type:\s+(EXEC|DYN)\s", header, re.M):
        raise ValueError("MAP02 cycle proof requires a fully linked ELF executable")
    entry = re.search(r"^\s*Entry point address:\s*0x([0-9a-fA-F]+)\s*$",
                      header, re.M)
    if entry is None or int(entry.group(1), 16) == 0:
        raise ValueError("MAP02 cycle ELF has no executable entry point")
    if not re.search(r"^\s*Machine:\s+.*(X86-64|80386|AArch64)", header, re.M):
        raise ValueError("unsupported MAP02 PC ELF architecture")
    symbols = set()
    initialized_data = {}
    for line in _run("nm", binary).splitlines():
        parts = line.split()
        if len(parts) >= 3:
            if parts[-2] in ("T", "W"):
                symbols.add(parts[-1])
            elif parts[-2] in ("R", "D") and len(parts) >= 4:
                try:
                    initialized_data[parts[-1]] = int(parts[-3], 16)
                except ValueError:
                    continue
    missing = sorted(set(SYMBOLS) - symbols)
    if missing:
        raise ValueError(
            "MAP02 original CD/GPU cycle ELF lacks required symbol(s): " +
            ", ".join(missing))
    missing_font = sorted(
        name for name, size in ORIGINAL_FONT_DATA_SYMBOLS.items()
        if initialized_data.get(name) != size)
    if missing_font:
        raise ValueError(
            "MAP02 PC executable lacks initialized original US font data: " +
            ", ".join(missing_font))
    # Recheck identity of the file itself; callers also check its bytes
    # against their independently prepared user-owned launch plan.
    again = binary.stat()
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns) != (
            again.st_dev, again.st_ino, again.st_size,
            again.st_mtime_ns, again.st_ctime_ns):
        raise ValueError("MAP02 ELF changed during inspection")
    return {
        "schema": "vh.map02.structural-cycle-elf-audit.v1",
        "required_symbols_present": len(SYMBOLS),
        "original_us_font_initialized_data_symbols_present":
            len(ORIGINAL_FONT_DATA_SYMBOLS),
        "original_gameplay_authenticated": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_pc_executable", type=Path)
    args = p.parse_args()
    try:
        result = audit_cycle_elf(args.private_pc_executable)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
