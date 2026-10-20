#!/usr/bin/env python3
"""Local offline Intel-Mac acceptance receipt (synthetic game data only).

Run from a previously SHA-256-authenticated, extracted MAP02 public-only kit.
It runs the *actual* 49-case + 3-helper shell suite and emits only a bounded
host-version/test-count receipt, never user paths, identifiers or file contents.

This is self-reported local compatibility, NOT remotely trusted attestation,
PS1 retail-frame provenance, or proof of original Vandal Hearts game parity.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

SCHEMA = "vh.map02.intel-mac.local-offline-acceptance.v1"
VERIFY_SCHEMA = "vh.map02.intel-mac.offline-preexec-verify.v1"
SELF_SCHEMA = "vh.map02.intel-mac.offline-private-ft4-readiness.v1"
HELPER_SCHEMA = "vh.map02.catalina.pinned-pc-helper-macho-audit.v1"
CATALINA = "10.15.7"
MAX_TEST_OUTPUT = 24576
MAX_VERIFY_OUTPUT = 4096
VERSION_RE = re.compile(r"(?:[0-9]{1,2})\.(?:[0-9]{1,2})(?:\.[0-9]{1,2})?\Z")


def bounded_version(value: str) -> str:
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise ValueError("unsupported macOS version format")
    return value


def validate_json_stream(value: str) -> tuple:
    """Accept exactly two JSON documents; never parse arbitrary stdout."""
    if not isinstance(value, str) or len(value) > MAX_TEST_OUTPUT:
        raise ValueError("synthetic selfcheck output exceeds bounds")
    decoder = json.JSONDecoder()
    first, end = decoder.raw_decode(value.lstrip())
    second, tail = decoder.raw_decode(value.lstrip()[end:].lstrip())
    if value.lstrip()[end:].lstrip()[tail:].strip():
        raise ValueError("unexpected selfcheck output after receipts")
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ValueError("selfcheck must return two JSON receipts")
    return first, second


def validated_results(integrity: dict, selfcheck: dict, helpers: dict) -> dict:
    if not isinstance(integrity, dict) or not isinstance(selfcheck, dict) or not isinstance(helpers, dict):
        raise ValueError("invalid local acceptance receipts")
    if not (
        integrity.get("schema") == VERIFY_SCHEMA
        and type(integrity.get("file_digests_verified")) is int
        and integrity["file_digests_verified"] >= 20
        and integrity.get("public_pc_source_git_blob_verified") is True
        and integrity.get("no_unlisted_files_or_symlinks") is True
        and integrity.get("private_user_data_read") is False
        and integrity.get("kit_signature_verified") is False
    ):
        raise ValueError("extracted kit integrity not established")
    if not (
        selfcheck.get("schema") == SELF_SCHEMA
        and selfcheck.get("intel_macos_host_checked") is True
        and selfcheck.get("pinned_public_pc_raster_verified") is True
        and type(selfcheck.get("synthetic_regressions_total")) is int
        and selfcheck["synthetic_regressions_total"] == 49
        and all(
            type(selfcheck.get(name)) is int and selfcheck[name] == total
            for name, total in (
                ("private_format_timeline_tests_passed", 14),
                ("private_format_native_ft4_tests_passed", 25),
                ("private_format_real_cli_tests_passed", 3),
                ("private_format_adversarial_cli_tests_passed", 7),
            )
        )
        and selfcheck.get("synthetic_c11_ft4_frame_passed") is True
        and selfcheck.get("c11_macho_macos_minimum") == "10.15"
        and selfcheck.get("c11_macho_minimum_verified") is True
        and selfcheck.get("external_network_used") is False
        and selfcheck.get("owner_ps1_disc_or_capture_read") is False
        and selfcheck.get("real_retail_map02_authenticated") is False
        and selfcheck.get("nintendo_switch_hardware_proven") is False
    ):
        raise ValueError("owner-local synthetic FT4 suite incomplete")
    if not (
        helpers.get("schema") == HELPER_SCHEMA
        and type(helpers.get("compiled_helpers_audited")) is int
        and helpers["compiled_helpers_audited"] == 3
        and type(helpers.get("synthetic_helpers_executed")) is int
        and helpers["synthetic_helpers_executed"] == 2
        and helpers.get("private_timeline_missing_input_rejected") is True
        and helpers.get("helper_architecture") == "x86_64"
        and helpers.get("helper_macos_minimum") == "10.15"
        and helpers.get("all_helper_load_commands_verified") is True
        and helpers.get("only_system_dynamic_libraries") is True
        and helpers.get("original_ps1_assets_read") is False
        and helpers.get("retail_gameplay_authenticated") is False
    ):
        raise ValueError("generated helper Mach-O checks incomplete")
    return {
        "synthetic_tests_verified": 49,
        "compiled_pc_helpers_verified": 3,
        "offline_only": True,
        "licensed_game_data_used": False,
    }


def local_acceptance(*, require_catalina: bool = False) -> dict:
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise ValueError("Intel macOS host required")
    if sys.version_info < (3, 9):
        raise ValueError("Python 3.9 or newer required")
    host_version = bounded_version(platform.mac_ver()[0])
    actual_catalina = host_version == CATALINA
    if require_catalina and not actual_catalina:
        # A macOS 15 CI host cannot invent a successful Catalina receipt.
        raise ValueError("required actual macOS Catalina 10.15.7 not running")
    root = Path(__file__).resolve().parent.parent
    if not (root / "verify-kit.py").is_file() or not (root / "run-selfcheck.sh").is_file():
        raise ValueError("only an authenticated extracted kit is supported")

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    prior = subprocess.run(
        [sys.executable, "verify-kit.py", "--root", "."],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=25,
    )
    if prior.returncode or prior.stderr or len(prior.stdout) > MAX_VERIFY_OUTPUT:
        raise ValueError("local kit integrity check failed")
    integrity = json.loads(prior.stdout)
    if integrity.get("schema") != VERIFY_SCHEMA:
        raise ValueError("kit verifier receipt missing")
    suite = subprocess.run(
        ["sh", "run-selfcheck.sh"], cwd=str(root), env=env,
        capture_output=True, text=True, timeout=900,
    )
    if suite.returncode or suite.stderr or len(suite.stdout) > MAX_TEST_OUTPUT:
        raise ValueError("local offline FT4 checker failed")
    selfcheck, helpers = validate_json_stream(suite.stdout)
    aggregate = validated_results(integrity, selfcheck, helpers)
    return {
        "schema": SCHEMA,
        "host_os": "macOS",
        "host_architecture": "x86_64",
        "host_macos_version": host_version,
        "python_version": "{}.{}".format(*sys.version_info[:2]),
        "actual_catalina_10_15_7_selfcheck_passed": actual_catalina,
        "c11_macho_minimum": "10.15",
        "source_to_native_ft4_synthetic_verified": True,
        **aggregate,
        "owner_ps1_disc_authenticated": False,
        "original_playstation_gpu_pixels_verified": False,
        "switch_hardware_verified": False,
        "independent_trusted_machine_attestation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-catalina-10-15-7", action="store_true",
        help="fail if not actually running on macOS Catalina 10.15.7",
    )
    args = parser.parse_args()
    try:
        report = local_acceptance(require_catalina=args.require_catalina_10_15_7)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError,
            subprocess.TimeoutExpired):
        # Do not expose absolute user paths, tool stderr or frame data.
        parser.error("Intel Mac local offline MAP02 compatibility not verified")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
