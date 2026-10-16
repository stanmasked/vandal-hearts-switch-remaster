#!/usr/bin/env python3
"""Audit *owned* M_MAP02.PRS geometry across wide, PC OP0 and PS1 input models.

Read-only: no original map bytes are stored, uploaded or printed. Caller
supplies either compressed M_MAP02.PRS or its decoded 187264-byte buffer.
Compile small local C scanner against the separately regression-tested
portable GTE reference; report aggregate counters and two bridge-face
lighting indices only. PS1 hardware accuracy remains unverified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from tools.audit_map02_disc_prs import (
    MAX_INPUT_SIZE, PRIOR_PRS_DECOMPRESSED_SHA256, unpack_prs,
)
from tools.compare_map02_variants import EXPECTED_LENGTH

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "tools/map02_op0_geometry_scan.c"


def read_owned_input(path: Path, compressed: bool) -> tuple[bytes, str]:
    size = path.stat().st_size
    limit = MAX_INPUT_SIZE if compressed else EXPECTED_LENGTH
    if size > limit or size < (4 if compressed else EXPECTED_LENGTH):
        raise ValueError(f"input size {size} outside supported MAP02 bounds")
    payload = path.read_bytes()
    decoded = unpack_prs(payload) if compressed else payload
    if len(decoded) != EXPECTED_LENGTH:
        raise ValueError(f"MAP02 decompressed length must be {EXPECTED_LENGTH}")
    return decoded, hashlib.sha256(payload).hexdigest()


def scan_decoded(decoded: bytes, compiler: str = "gcc",
                 *, require_prior_provenance: bool = False) -> dict:
    if len(decoded) != EXPECTED_LENGTH:
        raise ValueError(f"MAP02 decompressed length must be {EXPECTED_LENGTH}")
    digest = hashlib.sha256(decoded).hexdigest()
    matches_prior = digest == PRIOR_PRS_DECOMPRESSED_SHA256
    if require_prior_provenance and not matches_prior:
        raise ValueError("decoded MAP02 SHA256 does not match prior PRS provenance")
    with tempfile.TemporaryDirectory(prefix="vh-map02-op0-geometry-") as tmp:
        executable = Path(tmp) / "op0-map02-audit"
        compile_run = subprocess.run([
            compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            str(SCANNER), "-o", str(executable),
        ], text=True, capture_output=True, timeout=40)
        if compile_run.returncode:
            raise ValueError(f"OP0 geometry scanner compile failed: {compile_run.stderr[-1500:]}")
        analyzed = subprocess.run(
            [str(executable)], input=decoded, capture_output=True, timeout=40)
        if analyzed.returncode:
            raise ValueError(f"OP0 geometry audit rejected input: "
                             f"{analyzed.stderr.decode('utf-8','replace')[-1500:]}")
        result = json.loads(analyzed.stdout)
    if (result["active_tiles"] != 288 or
        result["raw_game_bytes_emitted"] is not False or
        result["ps1_hardware_gte_verified"] is not False):
        raise ValueError("OP0 geometry report contract changed")
    result["decoded_map_sha256"] = digest
    result["matches_prior_prs_sha256"] = matches_prior
    result["evidence_scope"] = ("decoded source-local MAP02 vertices; "
        "PC OP0 model / PS1 register input model only; "
        "no hardware GTE execution, camera projection or visible-pixel proof")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prs", type=Path, help="owned compressed M_MAP02.PRS")
    source.add_argument("--decoded", type=Path, help="owned decoded 187264-byte M_MAP02.PRS")
    parser.add_argument("--require-prior-provenance", action="store_true")
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        path = args.prs if args.prs is not None else args.decoded
        decoded, source_digest = read_owned_input(path, compressed=args.prs is not None)
        report = scan_decoded(
            decoded, compiler=args.compiler,
            require_prior_provenance=args.require_prior_provenance)
        report["input_sha256"] = source_digest
        report["input_type"] = "compressed_prs" if args.prs is not None else "decoded_prs"
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
