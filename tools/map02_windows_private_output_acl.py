"""Fail-closed NTFS output-folder audit for *owner-local* MAP02 media.

On Windows, POSIX st_mode/st_uid and 0o700 are not a privacy proof.
Invoke the OS PowerShell ACL API, never parse localized `icacls` output.
Only the fixed allow signal may appear in public-safe reports.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).with_name("map02_windows_private_output_acl.ps1")
SUCCESS = "VH_MAP02_OWNER_PRIVATE_NTFS_ACL_OK"


def require_windows_private_output(directory: Path, *, platform: str | None = None) -> None:
    """Check owner-only NTFS DACL, incl. inherited allows, on Windows.

    A DACL allowing any additional principal (Everyone, Users,
    Authenticated Users, CREATOR OWNER, domain group, etc.) fails closed.
    Built-in Administrators and LOCAL SYSTEM are accepted for OS recovery.
    The output directory must also be checked by the caller for symlinks
    and being outside Git. Do not use this routine on game source files.
    """
    actual = os.name if platform is None else platform
    if actual != "nt":
        return
    if not SCRIPT.is_file():
        raise ValueError("private Windows ACL verifier unavailable")
    target = Path(directory)
    if not target.is_absolute() or target.is_symlink() or not target.is_dir():
        raise ValueError("private Windows output must be an absolute ordinary directory")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
             "-Directory", str(target)],
            # A console-less Windows child must not inherit a potentially
            # invalid CI/GUI stdin HANDLE. Prevents interactive prompts,
            # and keeps the PowerShell ACL decision entirely independent
            # of the launching terminal or GUI state.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False, check=False, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("private Windows output ACL could not be verified") from None
    if result.returncode != 0 or result.stdout.strip() != SUCCESS.encode("ascii"):
        raise ValueError("private Windows output ACL is not owner-only")
