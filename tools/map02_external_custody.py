#!/usr/bin/env python3
"""Prepare and verify an out-of-band MAP02 Ed25519 custody signature.

GitHub Actions may produce an UNSIGNED request. A separate custodian must
inspect it, trust the identity independently, and sign its exact bytes with
a private key NEVER made available to this repository or Actions runner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from tools import verify_map02_published_receipt as published

SCHEMA = "vh.map02.external-custody-request.v1"
REPOSITORY = "stanmasked/vandal-hearts-switch-remaster"
WORKFLOW = ".github/workflows/map02-upstream-trace.yml"
LIMIT = 1024 * 1024


def _read(path, limit=LIMIT):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("MAP02 custody input symlink forbidden")
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("MAP02 custody input not bounded regular file")
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size,
                              s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != before.st_size or identity(before) != identity(after):
            raise ValueError("MAP02 custody input changed while reading")
        return raw
    finally:
        os.close(fd)


def _pairs(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ValueError("MAP02 custody JSON duplicate key")
        obj[key] = value
    return obj


def _constant(value):
    raise ValueError("MAP02 custody JSON nonfinite value")


def _canonical(item):
    try:
        raw = json.dumps(item, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("MAP02 custody JSON not canonicalizable") from exc
    if len(raw) > LIMIT:
        raise ValueError("MAP02 custody request too large")
    return raw


def _request(raw):
    try:
        item = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("MAP02 custody request malformed JSON") from exc
    if not isinstance(item, dict) or _canonical(item) != raw:
        raise ValueError("MAP02 custody request noncanonical encoding")
    if set(item) != {"schema", "subject", "independent_custodian_signed",
                     "real_map02_gameplay_authenticated",
                     "hd_replacement_authorized"}:
        raise ValueError("MAP02 custody request unexpected fields")
    if item["schema"] != SCHEMA or any(item[name] is not False for name in (
            "independent_custodian_signed",
            "real_map02_gameplay_authenticated", "hd_replacement_authorized")):
        raise ValueError("MAP02 custody request falsely claims verification")
    subj = item["subject"]
    if not isinstance(subj, dict) or set(subj) != {
            "repository", "workflow", "source_commit", "run_id",
            "run_attempt", "receipt_sha256", "linked_elf_sha256"}:
        raise ValueError("MAP02 custody request subject fields invalid")
    if subj["repository"] != REPOSITORY or subj["workflow"] != WORKFLOW:
        raise ValueError("MAP02 custody workflow identity invalid")
    if any(not isinstance(subj[name], str) or not re.fullmatch(
            r"[0-9a-f]{64}", subj[name]) for name in
            ("receipt_sha256", "linked_elf_sha256")):
        raise ValueError("MAP02 custody subject hash invalid")
    if not isinstance(subj["source_commit"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", subj["source_commit"]):
        raise ValueError("MAP02 custody source commit invalid")
    for name in ("run_id", "run_attempt"):
        if type(subj[name]) is not int or not 0 < subj[name] < 2**63:
            raise ValueError("MAP02 custody workflow run identity invalid")
    return item


def prepare(receipt, expected_sha256, *, commit, run_id, run_attempt):
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("MAP02 custody source commit invalid")
    if any(type(x) is not int or not 0 < x < 2**63 for x in
           (run_id, run_attempt)):
        raise ValueError("MAP02 custody workflow run identity invalid")
    checked = published.verify_published(receipt, expected_sha256)
    item = json.loads(_read(receipt).decode("utf-8"), object_pairs_hook=_pairs,
                      parse_constant=_constant)
    request = {
        "schema": SCHEMA,
        "subject": {
            "repository": REPOSITORY,
            "workflow": WORKFLOW,
            "source_commit": commit,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "receipt_sha256": checked["published_report_sha256"],
            "linked_elf_sha256": item["linked"]["linked_object_sha256"],
        },
        "independent_custodian_signed": False,
        "real_map02_gameplay_authenticated": False,
        "hd_replacement_authorized": False,
    }
    raw = _canonical(request)
    _request(raw)
    return raw


def _run_openssl(argv):
    try:
        return subprocess.run(["openssl", *argv], check=True,
                              capture_output=True, timeout=15).stdout
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise ValueError("MAP02 independent custodian signature invalid") from exc


def verify(request_path, signature_path, public_key_path, *,
           trusted_public_key_sha256, receipt_path, expected_receipt_sha256,
           expected_commit, expected_run_id, expected_run_attempt):
    if not isinstance(trusted_public_key_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", trusted_public_key_sha256):
        raise ValueError("MAP02 trusted custodian key fingerprint missing")
    raw = _read(request_path, 8192)
    item = _request(raw)
    subject = item["subject"]
    if (subject["source_commit"] != expected_commit or
            subject["run_id"] != expected_run_id or
            subject["run_attempt"] != expected_run_attempt or
            subject["receipt_sha256"] != expected_receipt_sha256):
        raise ValueError("MAP02 custody request differs from trusted launch identity")
    verified = published.verify_published(receipt_path, expected_receipt_sha256)
    if verified["published_report_sha256"] != subject["receipt_sha256"]:
        raise ValueError("MAP02 custodian receipt hash mismatch")
    report = json.loads(_read(receipt_path).decode("utf-8"),
                        object_pairs_hook=_pairs, parse_constant=_constant)
    if report["linked"]["linked_object_sha256"] != subject["linked_elf_sha256"]:
        raise ValueError("MAP02 custody linked ELF hash mismatch")
    signature = _read(signature_path, 128)
    if len(signature) != 64:
        raise ValueError("MAP02 Ed25519 signature must be 64 bytes")
    pem = _read(public_key_path, 8192)
    with tempfile.TemporaryDirectory(prefix="vh-map02-custodian-") as root:
        key = Path(root) / "public.pem"
        msg = Path(root) / "request.json"
        sig = Path(root) / "signature.bin"
        for path, payload in ((key, pem), (msg, raw), (sig, signature)):
            with open(path, "xb") as stream:
                stream.write(payload)
        spki = _run_openssl(["pkey", "-pubin", "-in", str(key),
                             "-pubout", "-outform", "DER"])
        if hashlib.sha256(spki).hexdigest() != trusted_public_key_sha256:
            raise ValueError("MAP02 custodian public key fingerprint mismatch")
        # Ed25519 is intentionally supported only with OpenSSL 3's -rawin.
        if len(spki) != 44 or not spki.startswith(bytes.fromhex(
                "302a300506032b6570032100")):
            raise ValueError("MAP02 custody key is not Ed25519")
        _run_openssl(["pkeyutl", "-verify", "-pubin", "-inkey",
                      str(key), "-rawin", "-in", str(msg),
                      "-sigfile", str(sig)])
    return {
        "schema": "vh.map02.external-custody-check.v1",
        "receipt_sha256": expected_receipt_sha256,
        "source_commit": expected_commit,
        "workflow_run_id": expected_run_id,
        "trusted_custodian_public_key_sha256": trusted_public_key_sha256,
        "independent_custodian_signature_verified": True,
        "real_map02_gameplay_authenticated": False,
        "hd_replacement_authorized": False,
    }


def _exclusive_output(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("--receipt", required=True)
    make.add_argument("--expected-sha256", required=True)
    make.add_argument("--source-commit", required=True)
    make.add_argument("--run-id", type=int, required=True)
    make.add_argument("--run-attempt", type=int, required=True)
    make.add_argument("--output", required=True)
    check = commands.add_parser("verify")
    check.add_argument("--request", required=True)
    check.add_argument("--signature", required=True)
    check.add_argument("--public-key", required=True)
    check.add_argument("--trusted-public-key-sha256", required=True)
    check.add_argument("--receipt", required=True)
    check.add_argument("--expected-receipt-sha256", required=True)
    check.add_argument("--expected-source-commit", required=True)
    check.add_argument("--expected-run-id", type=int, required=True)
    check.add_argument("--expected-run-attempt", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            raw = prepare(args.receipt, args.expected_sha256,
                          commit=args.source_commit, run_id=args.run_id,
                          run_attempt=args.run_attempt)
            _exclusive_output(args.output, raw)
            print("Created unsigned MAP02 custody request:", args.output)
        else:
            verified = verify(
                args.request, args.signature, args.public_key,
                trusted_public_key_sha256=args.trusted_public_key_sha256,
                receipt_path=args.receipt,
                expected_receipt_sha256=args.expected_receipt_sha256,
                expected_commit=args.expected_source_commit,
                expected_run_id=args.expected_run_id,
                expected_run_attempt=args.expected_run_attempt)
            print(json.dumps(verified, sort_keys=True))
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
