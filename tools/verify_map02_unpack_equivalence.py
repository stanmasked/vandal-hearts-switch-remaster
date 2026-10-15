#!/usr/bin/env python3
"""Differential-test MAP02 Python PRS decoder against the pinned PC-port C function.

Extracts UnpackMapFileData from upstream src/maps/unpack.c, compiles that
function in an isolated host harness and compares exact output bytes on
deterministic synthetic streams. No game asset is read, emitted or uploaded.
"""
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.audit_map02_disc_prs import unpack_prs
from tools.compare_map02_variants import (
    EXPECTED_LENGTH, FACE_GFX_OFFSET, RECORD_SIZE, TARGET_RECORDS,
)
from tools.prepare_map02_pcport import git_blob_sha1

PINNED_UNPACK_BLOB = "f427131d295c691dd55b4ecb1f68842304366c48"
START = "s32 UnpackMapFileData(u8 *input, u8 *output, s32 len) {"
END = "\nvoid ProcessMapFileData(u8 *input) {"
REQUIRED = (
    "pCache[cacheOfs++]",
    "cacheOfs &= 0x3ff;",
    "cacheOfs = 990;",
    "cacheIdx |= ((b1 & 0x03) << 8);",
    "num = (b1 >> 2) + 2;",
    "cacheIdx = b1 & 0x0f;",
    "num = ((b1 & 0x30) >> 4) + 1;",
    "num = (b1 & 0x3f) + 7;",
    "#ifdef PC_PORT",
)

HOST_WRAPPER = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
typedef unsigned char u8;
typedef uint32_t u32;
typedef int32_t s32;
''' + "\n{upstream_function}\n" + r'''
#define COMPRESSED_CAP 24576
#define OUTPUT_CAP 2097152
static u8 compressed[COMPRESSED_CAP + 128];
static u8 expanded[OUTPUT_CAP];
int main(void) {
    size_t n = fread(compressed, 1, COMPRESSED_CAP + 1, stdin);
    if (n < 4 || n > COMPRESSED_CAP) return 2;
    u32 len = (u32)compressed[0] | ((u32)compressed[1] << 8) |
              ((u32)compressed[2] << 16) | ((u32)compressed[3] << 24);
    if (len == 0 || len + 4 > n || len > COMPRESSED_CAP - 4) return 3;
    s32 size = UnpackMapFileData(compressed + 4, expanded, (s32)len);
    if (size < 0 || size > OUTPUT_CAP) return 4;
    if (fwrite(expanded, 1, (size_t)size, stdout) != (size_t)size) return 5;
    return 0;
}
'''


def extract_upstream_decoder(source: str) -> str:
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("pinned UnpackMapFileData / ProcessMapFileData anchors changed")
    start = source.index(START)
    end = source.index(END)
    if end <= start:
        raise ValueError("decompressor function order changed")
    extracted = source[start:end]
    for token in REQUIRED:
        if token not in extracted:
            raise ValueError(f"pinned upstream decompressor anchor changed: {token}")
    return extracted


def prs_payload(tokens: bytes) -> bytes:
    return len(tokens).to_bytes(4, "little") + tokens


def make_corpus() -> list[tuple[str, bytes]]:
    rng = random.Random(20261016)
    corpus = [
        ("literal", prs_payload(b"\x00abcdefgh")),
        ("cache_absolute", prs_payload(b"\x01\x00\x64")),
        ("cache_relative", prs_payload(b"\x01\x80")),
        ("long_literals", prs_payload(b"\x01\xc0abcdefgh")),
        ("mixed_tokens", prs_payload(b"\x07\x00\x64\x80\xc0abcdefgh")),
    ]
    letters = bytes(rng.randrange(0, 256) for _ in range(2048))
    lit = bytearray()
    for at in range(0, len(letters), 8):
        lit.append(0)
        lit.extend(letters[at:at + 8])
    corpus.append(("random_literals", prs_payload(bytes(lit))))

    # 616×304 synthetic map, matching two face-zero PRS GFX indices,
    # without storing any original map bytes.
    markers = {rec * RECORD_SIZE + FACE_GFX_OFFSET: val
               for rec, val in zip(TARGET_RECORDS, (241, 243))}
    tokens = []
    position = 0
    while position < EXPECTED_LENGTH:
        if position in markers:
            tokens.append((0, bytes((markers[position],))))
            position += 1
        else:
            next_marker = min((k for k in markers if k > position), default=EXPECTED_LENGTH)
            count = min(34, next_marker - position)
            if count < 3:
                tokens.append((0, b"\x00"))
                position += 1
            else:
                tokens.append((1, bytes(((count - 3) << 2, 100))))
                position += count
    encoded = bytearray()
    for index in range(0, len(tokens), 8):
        block = tokens[index:index + 8]
        encoded.append(sum(bit << i for i, (bit, _) in enumerate(block)))
        for _, chunk in block:
            encoded.extend(chunk)
    corpus.append(("synthetic_full_map", prs_payload(bytes(encoded))))
    return corpus


def compare_with_upstream(source: str, *, compiler: str = "gcc") -> dict:
    func = extract_upstream_decoder(source)
    if not shutil.which(compiler):
        raise ValueError(f"C compiler not found: {compiler}")
    records = []
    with tempfile.TemporaryDirectory() as folder:
        c_path = Path(folder) / "unpack.c"
        executable = Path(folder) / "unpack"
        c_path.write_text(HOST_WRAPPER.replace("{upstream_function}", func),
                          encoding="utf-8")
        compiled = subprocess.run(
            [compiler, "-std=gnu89", "-O0", "-DPC_PORT", "-Dasm(x)=",
             "-fno-strict-aliasing", str(c_path), "-o", str(executable)],
            capture_output=True, text=True,
        )
        if compiled.returncode:
            raise ValueError(f"pinned C decompressor failed host compilation: {compiled.stderr[-1500:]}")
        for label, sample in make_corpus():
            expected = unpack_prs(sample)
            actual = subprocess.run([str(executable)], input=sample,
                                    capture_output=True, timeout=15)
            if actual.returncode != 0:
                raise ValueError(f"upstream C decoder failed on {label}: exit {actual.returncode}")
            if actual.stdout != expected:
                offset = next((i for i, (a, b) in
                               enumerate(zip(actual.stdout, expected)) if a != b),
                              min(len(actual.stdout), len(expected)))
                raise ValueError(
                    f"Python/upstream decoder mismatch for {label} at byte {offset}"
                    f" (C length {len(actual.stdout)}, Python length {len(expected)})"
                )
            records.append({
                "fixture": label,
                "uncompressed_bytes": len(expected),
                "decoded_sha256": hashlib.sha256(expected).hexdigest(),
                "matches_upstream": True,
            })
    return {
        "decoder_git_blob_sha1": git_blob_sha1(source.encode("utf-8")),
        "test_count": len(records),
        "cases": records,
        "evidence_scope": "host-compiled pinned C decompressor vs Python on synthetic data; not original disc bytes",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_unpack_c", type=Path)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--allow-modified-source", action="store_true")
    args = parser.parse_args()
    try:
        source = args.upstream_unpack_c.read_bytes()
        observed = git_blob_sha1(source)
        if observed != PINNED_UNPACK_BLOB and not args.allow_modified_source:
            raise ValueError("unpack.c differs from pinned US upstream")
        result = compare_with_upstream(source.decode("utf-8"), compiler=args.compiler)
        result["matches_pinned_source"] = observed == PINNED_UNPACK_BLOB
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
