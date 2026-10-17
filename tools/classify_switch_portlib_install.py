#!/usr/bin/env python3
"""Classify a FAILED optional devkitPro portlib install without hiding failure.

A third-party HTTP 403 is not evidence that the Switch game code failed.
This helper prints the source of the blocker and always returns non-zero.
Native libnx/audout builds remain a separate, supported CI route.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MAX_LOG = 256 * 1024
PACKAGES = {"switch-sdl2", "switch-openal-soft"}
HTTP_403 = re.compile(
    r"(?:http(?:/[\d.]+)?\s*403|"
    r"(?:returned|request(?:ed)?|response|status)[^\n]{0,65}\b403\b|"
    r"\b403\s+Forbidden\b)", re.IGNORECASE)
NETWORK = re.compile(
    r"(timed out|timeout|could not resolve host|"
    r"temporary failure in name resolution|connection refused|"
    r"failed to synchronize|transfer failed|connection reset)", re.IGNORECASE)
NOT_FOUND = re.compile(
    r"(target not found|package not found|404\s+not found)", re.IGNORECASE)


class PortlibInstallError(ValueError):
    pass


def classify(package: str, log: str) -> dict:
    if package not in PACKAGES:
        raise PortlibInstallError("unsupported optional Switch dependency")
    if HTTP_403.search(log):
        code = "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403"
        action = (
            "devkitPro package mirror returned HTTP 403; do not treat this "
            "as a compiler or game-audio regression. Keep this job failed. "
            "Use separately tested native libnx/audout workflow until "
            "package access is restored."
        )
    elif NOT_FOUND.search(log):
        code = "OPTIONAL_DEVKITPRO_PACKAGE_NOT_FOUND"
        action = "Check the exact package name and currently supported devkitPro repository."
    elif NETWORK.search(log):
        code = "EXTERNAL_DEVKITPRO_PACKAGE_NETWORK_FAILURE"
        action = "Check devkitPro mirror reachability and retry in a future independent run."
    else:
        code = "UNCLASSIFIED_OPTIONAL_PACKAGE_INSTALL_FAILURE"
        action = "Inspect the original installation log for package-manager or image errors."
    return {
        "result": "OPTIONAL_DEPENDENCY_NOT_INSTALLED",
        "failure_code": code,
        "package": package,
        "hardware_status": "HARDWARE NOT TESTED",
        "compile_performed": False,
        "dependency_accepted": False,
        "recommended_action": action,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", required=True)
    p.add_argument("--log", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if args.package not in PACKAGES:
            raise PortlibInstallError("unexpected package name")
        if not args.log.is_file() or args.log.is_symlink():
            raise PortlibInstallError("installation log missing or symlinked")
        if args.log.stat().st_size > MAX_LOG:
            raise PortlibInstallError("installation log exceeds 256 KiB")
        raw = args.log.read_bytes()
        report = classify(args.package, raw.decode("utf-8", errors="replace"))
    except (PortlibInstallError, OSError) as exc:
        print(json.dumps({"result": "INVALID_INSTALL_LOG", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2))
    print(
        "::error title=Optional Switch dependency unavailable::"
        + report["failure_code"] + ": " + report["recommended_action"]
    )
    # This is deliberately a hard CI failure, never a successful substitute.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
