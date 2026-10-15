#!/usr/bin/env python3
"""Verify an already prepared Map02 diagnostic session before compilation.

Read-only, no proprietary game bytes accessed. Compare independent session
file digests and diagnostic manifest fields; do not replace the runtime
preflight of the checkout, disc, executable and KROM/BIOS sources.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF

GENERATED_NAMES = ("game_setup.trace.c", "graphics.trace.c", "map02_trace.mk")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: Path, description: str) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"{description} must be a JSON object")
    return value


def require_digest(actual: str, expected, label: str) -> None:
    if (type(expected) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None):
        raise ValueError(f"{label}: invalid expected SHA-256")
    if actual != expected:
        raise ValueError(f"{label}: SHA-256 mismatch (session inputs changed)")


def require_path(value, expected: Path, label: str) -> None:
    if type(value) is not str or Path(value).resolve() != expected.resolve():
        raise ValueError(f"{label}: path disagrees with session directory")


def verify_session(session_directory: Path) -> dict:
    directory = session_directory.expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("session must be a directory")

    plan = read_json_object(directory / "session_plan.json", "session plan")
    if plan.get("kind") != "map02_user_executed_session_plan":
        raise ValueError("unrecognized Map02 session plan")
    if plan.get("trace_mode") != "full":
        raise ValueError("only full Map02 sessions are supported")
    if plan.get("preflight_complete") is not True:
        raise ValueError("session was not prepared with a successful preflight")
    if plan.get("build_executed") is not False or plan.get("game_executed") is not False:
        raise ValueError("session plan must not claim an execution result")

    trace = directory / "trace"
    require_path(plan.get("trace_dir"), trace, "trace")
    require_path(plan.get("capture_dir"), directory / "capture", "capture")
    require_path(plan.get("user_shell_script"),
                 directory / "build_capture_verify.sh", "shell script")
    if not trace.is_dir():
        raise ValueError("missing generated trace directory")
    if (directory / "capture").exists():
        raise ValueError("capture directory already exists; use a new session")

    build_dir = plan.get("build_dir")
    if type(build_dir) is not str or re.fullmatch(r"build-map02-[0-9a-f]{12}", build_dir) is None:
        raise ValueError("invalid session build directory")
    upstream = plan.get("upstream")
    if type(upstream) is not str or not Path(upstream).is_absolute():
        raise ValueError("invalid upstream checkout in session plan")
    expected_binary = Path(upstream) / "platform" / "pc" / build_dir / "vandalhearts_pc"
    require_path(plan.get("binary"), expected_binary, "game binary")

    expected_files = (
        ("build_capture_verify.sh", plan.get("shell_sha256")),
        ("preflight.json", plan.get("preflight_sha256")),
        ("trace/source_provenance.json", plan.get("provenance_sha256")),
    )
    for relative, expected in expected_files:
        require_digest(sha256_file(directory / relative), expected, relative)

    original_preflight = read_json_object(directory / "preflight.json", "preflight")
    if original_preflight.get("ready_for_attempt") is not True or original_preflight.get("blockers") != []:
        raise ValueError("stored session preflight did not pass")

    provenance = read_json_object(trace / "source_provenance.json", "source provenance")
    if (provenance.get("upstream_reference") != PINNED_UPSTREAM_REF
            or provenance.get("trace_mode") != "full"
            or provenance.get("allow_modified_source") is not False):
        raise ValueError("source provenance is not an unmodified pinned full trace")
    sources = provenance.get("source_files")
    if type(sources) is not dict or set(sources) != set(PINNED_BLOB_SHA1):
        raise ValueError("pinned source provenance is incomplete")
    for relative, expected_blob in PINNED_BLOB_SHA1.items():
        record = sources[relative]
        if (type(record) is not dict
                or record.get("git_blob_sha1") != expected_blob
                or record.get("matches_pinned") is not True):
            raise ValueError(f"{relative}: pinned source identity differs")

    generated = provenance.get("generated_files")
    if type(generated) is not dict or set(generated) != set(GENERATED_NAMES):
        raise ValueError("generated source fingerprints are incomplete")
    for name, digest in generated.items():
        require_digest(sha256_file(trace / name), digest, name)

    marker = provenance.get("binary_marker")
    loader_marker = provenance.get("binary_loader_marker")
    if (type(marker) is not str or type(loader_marker) is not str
            or re.fullmatch(r"VH_MAP02_TRACE_BUILD_ID:[0-9a-f]{64}", marker) is None
            or loader_marker != marker.replace("TRACE_BUILD_ID:", "TRACE_LOADER_ID:", 1)):
        raise ValueError("loader and renderer build identities do not match")
    if marker not in (trace / "graphics.trace.c").read_text(encoding="utf-8"):
        raise ValueError("renderer build marker missing from generated C source")
    if loader_marker not in (trace / "game_setup.trace.c").read_text(encoding="utf-8"):
        raise ValueError("loader build marker missing from generated C source")
    overlay = (trace / "map02_trace.mk").read_text(encoding="utf-8")
    if f"VH_MAP02_TRACE_DIR := {trace.resolve()}" not in overlay:
        raise ValueError("Make overlay does not reference this diagnostic directory")

    return {
        "integrity": "verified",
        "trace_mode": "full",
        "source_revision": PINNED_UPSTREAM_REF,
        "build_dir": build_dir,
        "warning": "Hash consistency is not a signature, nor proof of a successful build or game trace. Check source and owned game resources again before compiling.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_directory", type=Path)
    args = parser.parse_args()
    try:
        report = verify_session(args.session_directory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
