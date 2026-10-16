#!/usr/bin/env python3
"""Offline SHA-256 inventory and verification of Nintendo Switch audio evidence.

The manifest is unsigned and self-reported. Verification establishes only
current byte-for-byte consistency with that manifest and CSV parseability;
it is NEVER physical playback, SD power-loss durability or audio acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

import analyze_switch_audio_log as audio

SCHEMA = "vh-switch-audio-bundle/v1"
HARDWARE_STATUS = "HARDWARE NOT TESTED"
MANIFEST_NAME = "audio-evidence-manifest.json"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")


class BundleError(ValueError):
    """Invalid manifest, missing file, altered bytes or corrupt CSV."""


def safe_member(root: Path, relative: str, suffix: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise BundleError("invalid relative bundle path")
    name = PurePosixPath(relative)
    if (name.is_absolute() or relative != name.as_posix() or
            any(bit in ("", ".", "..") for bit in relative.split("/")) or
            name.suffix.lower() != suffix):
        raise BundleError(f"unsafe or unexpected path: {relative!r}")
    part = root
    for bit in name.parts:
        part = part / bit
        if part.is_symlink():
            raise BundleError(f"symbolic links are not accepted: {relative}")
    if not part.is_file():
        raise BundleError(f"file is missing or is not regular: {relative}")
    if not part.resolve().is_relative_to(root.resolve()):
        raise BundleError(f"path escapes bundle: {relative}")
    return part


def digest_file(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return path.stat().st_size, h.hexdigest()


def record(root: Path, name: str, kind: str) -> dict:
    path = safe_member(root, name, ".nro" if kind == "nro" else ".csv")
    size, digest = digest_file(path)
    result = {"path": name, "size": size, "sha256": digest}
    if kind == "csv":
        # Explicitly verify the format using the existing strict analyzer.
        audio.load_csv(path)
    return result


def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    if path.is_symlink() or not path.is_file():
        raise BundleError("manifest missing or a symbolic link")
    if path.stat().st_size > 65536:
        raise BundleError("manifest exceeds 64 KiB")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"),
                              object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BundleError("manifest must be an object")
    if set(manifest) != {"schema", "hardware_status", "git_sha", "ci_run_url", "nro", "sessions"}:
        raise BundleError("manifest has missing/unknown keys")
    if manifest["schema"] != SCHEMA or manifest["hardware_status"] != HARDWARE_STATUS:
        raise BundleError("unsupported schema or claimed physical acceptance")
    if not isinstance(manifest["git_sha"], str) or not GIT_SHA_RE.fullmatch(manifest["git_sha"]):
        raise BundleError("invalid full git commit SHA")
    if not isinstance(manifest["ci_run_url"], str):
        raise BundleError("ci_run_url must be a string")
    if manifest["ci_run_url"] and not re.fullmatch(
            r"https://github\.com/[^/\s]+/[^/\s]+/actions/runs/[0-9]+",
            manifest["ci_run_url"]):
        raise BundleError("invalid GitHub Actions run URL")
    if not isinstance(manifest["sessions"], list) or len(manifest["sessions"]) > 64:
        raise BundleError("sessions must be a list (up to 64)")
    return manifest


def verified_entry(root: Path, item: dict, kind: str) -> Path:
    if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
        raise BundleError("invalid file record fields")
    if type(item["size"]) is not int or item["size"] < 0:
        raise BundleError("invalid recorded file size")
    if not isinstance(item["sha256"], str) or not SHA256_RE.fullmatch(item["sha256"]):
        raise BundleError("invalid SHA-256 field")
    path = safe_member(root, item["path"], ".nro" if kind == "nro" else ".csv")
    actual_size, actual_hash = digest_file(path)
    if actual_size != item["size"] or actual_hash != item["sha256"]:
        raise BundleError(f"size or SHA-256 mismatch: {item['path']}")
    return path


def inspect(root: Path) -> dict:
    manifest = read_manifest(root)
    nro = verified_entry(root, manifest["nro"], "nro")
    registered = {nro.relative_to(root).as_posix()}
    observed = []
    for item in manifest["sessions"]:
        path = verified_entry(root, item, "csv")
        relative = path.relative_to(root).as_posix()
        if relative in registered:
            raise BundleError(f"duplicate file path: {relative}")
        registered.add(relative)
        rows = audio.load_csv(path)
        summary = audio.summarize(rows)
        observed.append({
            "path": relative,
            "rows": summary["rows"],
            "observed_pcm_pages": summary["observed_counter_increments"]["output_pages"],
            "observed_home_resumes": summary["observed_counter_increments"]["home_resumes"],
            "assessment": summary["assessment"],
            "has_exit": rows[-1]["event"] == "EXIT",
            "counter_rollbacks": summary["counter_rollbacks"],
            "warnings": summary["warnings"],
        })
    # NRO/CSV files not in the inventory must not be mistaken for verified evidence.
    unexpected = sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*")
        if p.suffix.lower() in (".csv", ".nro") and p.relative_to(root).as_posix() not in registered
    )
    if unexpected:
        raise BundleError("untracked NRO/CSV: " + ", ".join(unexpected[:4]))
    hashes = [item["sha256"] for item in manifest["sessions"]]
    duplicate_payloads = len(hashes) != len(set(hashes))
    enough = (len(observed) >= 2 and not duplicate_payloads and
              all(s["observed_pcm_pages"] >= 1000 and s["has_exit"] and
                  not s["counter_rollbacks"] for s in observed))
    return {
        "integrity": "VERIFIED",
        "telemetry_readiness": "ENOUGH_DATA_FOR_MANUAL_REVIEW" if enough else "INCOMPLETE",
        "hardware_status": HARDWARE_STATUS,
        "git_sha": manifest["git_sha"],
        "session_count": len(observed),
        "sessions": observed,
        "evidence_warnings": (["Identical CSV bytes in different paths: "
                               "copies cannot count as independent sessions."]
                              if duplicate_payloads else []),
        "limitations": ("Hashes are unauthenticated; independent physical sessions, "
                        "audible fidelity, HOME/sleep and power-loss durability are not proven."),
    }


def create(root: Path, nro: str, sessions: list[str], sha: str, ci_url: str) -> dict:
    if not GIT_SHA_RE.fullmatch(sha):
        raise BundleError("--git-sha must be a full 40-digit hexadecimal commit SHA")
    if not root.is_dir():
        raise BundleError("bundle directory does not exist")
    if (root / MANIFEST_NAME).exists() or (root / MANIFEST_NAME).is_symlink():
        raise BundleError("manifest already exists; refusing to overwrite evidence")
    if len(sessions) > 64 or len(sessions) != len(set(sessions)):
        raise BundleError("too many or repeated CSV session paths")
    if len(set(sessions + [nro])) != len(sessions) + 1:
        raise BundleError("same file listed multiple times")
    if ci_url and not re.fullmatch(
            r"https://github\.com/[^/\s]+/[^/\s]+/actions/runs/[0-9]+", ci_url):
        raise BundleError("--ci-run-url must be a GitHub Actions run link")
    obj = {
        "schema": SCHEMA,
        "hardware_status": HARDWARE_STATUS,
        "git_sha": sha.lower(),
        "ci_run_url": ci_url,
        "nro": record(root, nro, "nro"),
        "sessions": [record(root, path, "csv") for path in sessions],
    }
    # Fail closed if another NRO/CSV exists outside the provided inventory.
    paths = {nro, *sessions}
    untracked = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                       if p.suffix.lower() in (".csv", ".nro")
                       and p.relative_to(root).as_posix() not in paths)
    if untracked:
        raise BundleError("untracked NRO/CSV: " + ", ".join(untracked[:4]))
    manifest = root / MANIFEST_NAME
    # Exclusive creation: the original manifest must never be silently replaced.
    with manifest.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(obj, file, sort_keys=True, ensure_ascii=False, indent=2)
        file.write("\n")
    return inspect(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("create", help="hash local NRO and CSV files into a new manifest")
    prepare.add_argument("bundle", type=Path)
    prepare.add_argument("--git-sha", required=True)
    prepare.add_argument("--ci-run-url", default="")
    prepare.add_argument("--nro", required=True, help="relative path inside bundle")
    prepare.add_argument("--session", action="append", default=[], help="relative CSV; repeat")
    check = sub.add_parser("verify", help="check all listed bytes and parse real CSV")
    check.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.bundle.resolve()
        if not root.is_dir():
            raise BundleError("bundle directory not found")
        if args.action == "create":
            report = create(root, args.nro, args.session, args.git_sha, args.ci_run_url)
        else:
            report = inspect(root)
    except (BundleError, OSError, audio.LogFormatError) as exc:
        print(json.dumps({"integrity": "FAILED", "hardware_status": HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
