#!/usr/bin/env python3
"""Verify that an AV build bundle contains exactly seven expected NRO images.

Digest matching is only an artifact consistency check. Neither the
manifest nor the source marker is a signature or proof of playback.
"""
import argparse
import hashlib
import re
import struct
from pathlib import Path

NRO_NAMES = (
    "libnx-ps1-music-av.nro",
    "libnx-ps1-music-av-zr.nro",
    "libnx-ps1-music-av-zl.nro",
    "libnx-ps1-music-av-resume.nro",
    "libnx-ps1-music-av-resume-retry.nro",
    "libnx-ps1-music-av-focus.nro",
    "libnx-ps1-music-av-focus-manual.nro",
)
MANIFEST = "native-ps1-av-nro-sha256.txt"
COMMIT_FILE = "native-ps1-av-source-commit.txt"


def regular_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing, non-regular or symlinked AV artifact: " + str(path))
    return path


def check_nro_header(header, size, filename):
    if size < 0x80 or len(header) < 0x38 or header[0x10:0x14] != b"NRO0":
        raise ValueError("invalid NRO0 header: " + filename)
    declared = struct.unpack_from("<I", header, 0x18)[0]
    if declared < 0x80 or declared > size:
        raise ValueError("invalid declared NRO size: " + filename)
    previous_end = 0
    for offset in (0x20, 0x28, 0x30):
        start, length = struct.unpack_from("<II", header, offset)
        if length == 0 or start >= declared or start + length > declared:
            raise ValueError("invalid NRO segment bounds: " + filename)
        # A valid NRO has text, rodata and data in their specified
        # order without overlapping file ranges. A recomputed digest
        # cannot legitimize contradictory segment directory entries.
        if start < previous_end:
            raise ValueError("overlapping or out-of-order NRO segments: " + filename)
        previous_end = start + length


def verify_bundle(root, expected_commit=None, *, exact_inventory=False):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("expected a non-symlink AV artifact directory")
    # CI's working build directory can contain other products, but the
    # downloaded, published AV bundle must contain ONLY these nine files.
    if exact_inventory:
        expected = set(NRO_NAMES) | {MANIFEST, COMMIT_FILE}
        actual = {entry.name for entry in root.iterdir()}
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError("AV artifact directory inventory mismatch; " +
                             "missing=" + repr(missing) + ", extra=" + repr(extra))
    if (expected_commit is not None and
            re.fullmatch(r"[a-fA-F0-9]{40}", expected_commit) is None):
        raise ValueError("expected source commit must contain 40 hexadecimal characters")
    source = regular_file(root / COMMIT_FILE).read_bytes()
    if re.fullmatch(rb"[a-f0-9]{40}\n", source) is None:
        raise ValueError("source commit marker must be a lowercase SHA-1 plus newline")
    commit = source[:-1].decode("ascii")
    if expected_commit is not None and commit != expected_commit.lower():
        raise ValueError("source commit marker differs from the independently expected commit")
    data = regular_file(root / MANIFEST).read_bytes()
    try:
        manifest = data.decode("ascii")
    except UnicodeError as exc:
        raise ValueError("NRO digest manifest must contain only ASCII") from exc
    lines = manifest.splitlines(keepends=True)
    if len(lines) != len(NRO_NAMES):
        raise ValueError("NRO manifest must list exactly seven images")
    checksums = {}
    for line, expected_name in zip(lines, NRO_NAMES):
        parsed = re.fullmatch(r"([a-f0-9]{64})  ([a-z0-9_.-]+\.nro)\n", line)
        if parsed is None or parsed.group(2) != expected_name:
            raise ValueError("unexpected, duplicated or missing NRO manifest entry")
        expected_hash = parsed.group(1)
        binary_path = regular_file(root / expected_name)
        with binary_path.open("rb") as source_file:
            header = source_file.read(0x38)
            size = binary_path.stat().st_size
            check_nro_header(header, size, expected_name)
            source_file.seek(0)
            sha = hashlib.sha256()
            for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                sha.update(chunk)
        if sha.hexdigest() != expected_hash:
            raise ValueError("NRO SHA-256 mismatch: " + expected_name)
        checksums[expected_name] = expected_hash
    # Every variant has an independent build target, diagnostic macro
    # and NACP title. A repeated entire NRO image is a mislabeled or
    # substituted variant even when somebody rewrites its digest entry.
    if len(set(checksums.values())) != len(NRO_NAMES):
        raise ValueError("duplicate NRO payload across distinct diagnostic variants")
    return {"source_commit": commit, "nro_count": len(checksums),
            "nro_sha256": checksums,
            "physical_hardware_verified": False,
            "audible_audio_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--expected-commit",
                        help="source SHA read independently from the GitHub Actions run")
    parser.add_argument("--exact-inventory", action="store_true",
                        help="require exactly the seven NROs and two metadata files (published bundle only)")
    args = parser.parse_args()
    try:
        result = verify_bundle(args.artifact_directory, args.expected_commit,
                               exact_inventory=args.exact_inventory)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("PASS: verified " + str(result["nro_count"]) +
          " NROs with exact manifest entries, SHA-256 and source marker; " +
          "no hardware/audio attestation")


if __name__ == "__main__":
    main()
