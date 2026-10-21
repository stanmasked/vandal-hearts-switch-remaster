#!/usr/bin/env python3
"""Offline verification of a self-contained, asset-free MAP02 NeXium evidence set.

The evidence ZIP now includes the exact tested NRO, build receipt, 24 PNGs,
source metadata and logs. The canonical root digest detects accidental
truncation, changes or mismatched files after download, but is NOT a digital
signature and does not authenticate GitHub or the emulator operator.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from run_map02_nexium_cold_restart import (  # noqa: E402
    STAGES, audit_manifest, verify as verify_frames,
)
from map02_candidate_receipt import (  # noqa: E402
    NRO_NAME, ReceiptError, require_sha, unique_keys,
    verify as verify_nro,
)

RECEIPT = "bundle-receipt.json"
SCHEMA = 1
PASS_GAME = (
    "VH_MAP02_NEXIUM_COLD_RESTART_PASS emulator_processes=2 "
    "different_pids=1 first_exited_before_second=1 guard_both=1 "
    "medic_both=1 bow_both=1 two_resets_each=1 "
    "board_determinism=1 hud_determinism=1 legacy_preserved=1 retail=0"
)
PASS_OFFLINE = (
    "VH_MAP02_COLD_RESTART_OFFLINE_AUDIT_PASS frames=24 png_sha256=1 "
    "board_rgb_sha256=1 guard_hud_rgb_sha256=1"
)
OTHER = (
    "build-receipt.json", "capture-sha256-manifest.json",
    "processes.json", "result.log", "offline-audit.log",
    "nexium-release.json", "nexium-archive.sha256",
    "nexium-executable.sha256", "boot1_nexium.log", "boot2_nexium.log",
    NRO_NAME,
)
PNG = tuple(
    f"boot{boot}_{stage}.png"
    for boot in (1, 2) for stage in STAGES
)
EXPECTED = frozenset((*OTHER, *PNG))
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    pass


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def read_evidence_files(folder: Path) -> list[dict]:
    if not folder.is_dir() or folder.is_symlink():
        raise EvidenceError("evidence directory must be a real directory")
    actual = {p.name for p in folder.iterdir()}
    if actual not in (EXPECTED, EXPECTED | {RECEIPT}):
        missing = sorted(EXPECTED - actual)
        extra = sorted(actual - EXPECTED - {RECEIPT})
        raise EvidenceError(f"incomplete or unexpected evidence: "
                            f"missing={missing[:5]} extra={extra[:5]}")
    entries = []
    for name in sorted(EXPECTED):
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise EvidenceError(f"evidence file not regular: {name}")
        size = path.stat().st_size
        if not 0 < size <= (24 * 1024 * 1024 if name == NRO_NAME
                           else 10 * 1024 * 1024):
            raise EvidenceError(f"empty or oversized evidence file: {name}")
        entries.append({
            "name": name, "size_bytes": size,
            "sha256": sha256(path.read_bytes()),
        })
    return entries


def _contains_exact(path: Path, value: str) -> bool:
    return value in path.read_text(encoding="utf-8").splitlines()


def make_bundle(folder: Path, source_commit: str,
                source_tree: str) -> dict:
    require_sha("source_commit", source_commit)
    require_sha("source_tree", source_tree)
    entries = read_evidence_files(folder)
    build = verify_nro(folder / NRO_NAME, folder / "build-receipt.json",
                       source_commit, source_tree)
    # Re-validate gameplay and RGB content without ever starting NeXium.
    verify_frames(folder)
    audit_manifest(folder)
    if not _contains_exact(folder / "result.log", PASS_GAME):
        raise EvidenceError("real two-process NeXium pass line missing")
    if not _contains_exact(folder / "offline-audit.log", PASS_OFFLINE):
        raise EvidenceError("offline RGB check pass line missing")
    # Retain the exact NRO SHA, source tree and screenshot manifest identity.
    basis = {
        "schema_version": SCHEMA,
        "kind": "map02-nexium-self-contained-evidence",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "nro_sha256": build["sha256"],
        "nro_size_bytes": build["size_bytes"],
        "png_count": len(PNG),
        "file_count": len(entries),
        "files": entries,
    }
    return {**basis, "root_sha256": sha256(canonical(basis))}


def create(folder: Path, source_commit: str,
           source_tree: str) -> dict:
    if (folder / RECEIPT).exists() or (folder / RECEIPT).is_symlink():
        raise EvidenceError("refusing to replace existing bundle receipt")
    entry = make_bundle(folder, source_commit, source_tree)
    (folder / RECEIPT).write_text(json.dumps(entry, sort_keys=True,
                                              indent=2) + "\n",
                                  encoding="utf-8")
    return entry


def verify(folder: Path, source_commit: str, source_tree: str) -> dict:
    path = folder / RECEIPT
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise EvidenceError("bundle receipt absent, symlinked or oversized")
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"),
                              object_pairs_hook=unique_keys)
    except (UnicodeError, ValueError, ReceiptError) as exc:
        raise EvidenceError("invalid or duplicate-field bundle receipt") from exc
    rebuilt = make_bundle(folder, source_commit, source_tree)
    if not isinstance(recorded, dict) or frozenset(recorded) != frozenset(rebuilt):
        raise EvidenceError("bundle receipt schema mismatch")
    if (not isinstance(recorded["root_sha256"], str)
            or SHA256.fullmatch(recorded["root_sha256"]) is None
            or not hmac.compare_digest(recorded["root_sha256"],
                                       rebuilt["root_sha256"])
            or recorded != rebuilt):
        raise EvidenceError("bundle receipt SHA-256 / file provenance mismatch")
    return rebuilt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    args = parser.parse_args()
    try:
        if args.action == "create":
            entry = create(args.evidence_dir, args.source_commit,
                           args.source_tree)
        else:
            entry = verify(args.evidence_dir, args.source_commit,
                           args.source_tree)
        print(
            "VH_MAP02_EVIDENCE_BUNDLE_PASS "
            f"action={args.action} files={entry['file_count']} "
            f"png={entry['png_count']} nro_sha256={entry['nro_sha256']} "
            f"root_sha256={entry['root_sha256']} retail=0", flush=True)
        return 0
    except (OSError, ReceiptError, EvidenceError, ValueError) as exc:
        print("VH_MAP02_EVIDENCE_BUNDLE_FAIL: " + str(exc),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
