#!/usr/bin/env python3
"""Bind a Switch homebrew NRO to the exact checked-out Git source and SHA-256.

The receipt is deliberately deterministic and contains only public build
metadata, never retail ROM paths, keys, source-image contents or user data.
This does not authenticate the builder: it detects accidentally replaced,
stale, truncated or mismatched CI artifacts across jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys

NRO_NAME = "vandal-hearts-prototype.nro"
KIND = "map02-original-asset-free-homebrew"
SCHEMA = 1
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_FIELDS = frozenset(
    ("schema_version", "kind", "filename", "size_bytes",
     "sha256", "source_commit", "source_tree")
)


class ReceiptError(ValueError):
    pass


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("duplicate receipt field: " + key)
        result[key] = value
    return result


def require_sha(label: str, value: str):
    if not isinstance(value, str) or SHA40.fullmatch(value) is None:
        raise ReceiptError(label + " must be a 40-character lowercase SHA")
    return value


def hash_file(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ReceiptError("NRO must be a regular file, never a symlink")
    if path.name != NRO_NAME:
        raise ReceiptError("unexpected NRO filename")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            count += len(chunk)
    if count < 1:
        raise ReceiptError("zero-byte NRO cannot be accepted")
    return count, digest.hexdigest()


def make_receipt(nro: Path, source_commit: str, source_tree: str):
    require_sha("source_commit", source_commit)
    require_sha("source_tree", source_tree)
    size, digest = hash_file(nro)
    return {
        "schema_version": SCHEMA,
        "kind": KIND,
        "filename": NRO_NAME,
        "size_bytes": size,
        "sha256": digest,
        "source_commit": source_commit,
        "source_tree": source_tree,
    }


def parse_receipt(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ReceiptError("receipt must be a regular file, never a symlink")
    if path.stat().st_size > 8192:
        raise ReceiptError("receipt is unexpectedly large")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"),
                         object_pairs_hook=unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("malformed JSON receipt") from exc
    if not isinstance(obj, dict) or frozenset(obj) != EXPECTED_FIELDS:
        raise ReceiptError("unexpected or missing receipt fields")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != SCHEMA:
        raise ReceiptError("unsupported receipt schema")
    if obj["kind"] != KIND or obj["filename"] != NRO_NAME:
        raise ReceiptError("wrong game or artifact kind")
    if type(obj["size_bytes"]) is not int or obj["size_bytes"] < 1:
        raise ReceiptError("invalid artifact byte count")
    if not isinstance(obj["sha256"], str) or not SHA64.fullmatch(obj["sha256"]):
        raise ReceiptError("invalid SHA-256 format")
    require_sha("source_commit", obj["source_commit"])
    require_sha("source_tree", obj["source_tree"])
    return obj


def verify(nro: Path, receipt: Path, source_commit: str, source_tree: str):
    require_sha("expected source_commit", source_commit)
    require_sha("expected source_tree", source_tree)
    saved = parse_receipt(receipt)
    current = make_receipt(nro, source_commit, source_tree)
    if saved["source_commit"] != current["source_commit"]:
        raise ReceiptError("source commit mismatch; stale NRO")
    if saved["source_tree"] != current["source_tree"]:
        raise ReceiptError("Git source tree mismatch; stale NRO")
    if saved["size_bytes"] != current["size_bytes"]:
        raise ReceiptError("NRO byte count mismatch")
    if not hmac.compare_digest(saved["sha256"], current["sha256"]):
        raise ReceiptError("NRO SHA-256 mismatch")
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--nro", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    args = parser.parse_args()
    try:
        if args.action == "create":
            entry = make_receipt(args.nro, args.source_commit, args.source_tree)
            if args.receipt.is_symlink():
                raise ReceiptError("receipt output cannot be a symlink")
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(
                json.dumps(entry, sort_keys=True, indent=2) + "\n",
                encoding="utf-8")
        else:
            entry = verify(args.nro, args.receipt,
                           args.source_commit, args.source_tree)
        print(
            "VH_MAP02_CANDIDATE_RECEIPT_PASS "
            f"action={args.action} bytes={entry['size_bytes']} "
            f"sha256={entry['sha256']} "
            f"source_commit={entry['source_commit']} "
            f"source_tree={entry['source_tree']} retail=0",
            flush=True,
        )
    except (OSError, ReceiptError) as exc:
        print("VH_MAP02_CANDIDATE_RECEIPT_FAIL: " + str(exc),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
