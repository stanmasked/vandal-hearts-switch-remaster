#!/usr/bin/env python3
"""Split and reassemble an owner-local disc image without publishing its bytes.

The manifest contains private SHA-256 digests. Keep it beside the split parts
in the owner's private storage; do not commit it or attach it to a public issue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

SCHEMA = "vh.map02.private-disc-parts.v1"
DEFAULT_CHUNK_SIZE = 220 * 1024 * 1024
MAX_CHUNK_SIZE = 240 * 1024 * 1024
MAX_PARTS = 100
IO_BLOCK_SIZE = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _regular_file(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{description} must be a regular, non-symlink file")


def _safe_basename(name: Any) -> bool:
    return (isinstance(name, str) and bool(name) and name not in {".", ".."}
            and Path(name).name == name and "/" not in name and "\\" not in name)


def _sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def split_image(source: Path, output_dir: Path,
                chunk_size: int = DEFAULT_CHUNK_SIZE) -> tuple[Path, dict[str, Any]]:
    source = Path(source)
    output_dir = Path(output_dir)
    _regular_file(source, "source image")
    if output_dir.is_symlink():
        raise ValueError("output directory must not be a symlink")
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("chunk size must be between 1 byte and 240 MiB")

    total_bytes = source.stat().st_size
    if total_bytes <= 0:
        raise ValueError("source image must not be empty")
    part_count = (total_bytes + chunk_size - 1) // chunk_size
    if part_count > MAX_PARTS:
        raise ValueError("source would require too many parts")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{source.name}.parts.json"
    part_paths = [output_dir / f"{source.name}.part{i:02d}" for i in range(part_count)]
    for path in [*part_paths, manifest_path]:
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"refusing to overwrite existing split output: {path.name}")

    before = source.stat()
    created: list[Path] = []
    whole_hash = hashlib.sha256()
    parts: list[dict[str, Any]] = []
    remaining_total = total_bytes
    try:
        with source.open("rb") as source_stream:
            for part_path in part_paths:
                wanted = min(chunk_size, remaining_total)
                part_hash = hashlib.sha256()
                part_bytes = 0
                with part_path.open("xb") as part_stream:
                    created.append(part_path)
                    while part_bytes < wanted:
                        block = source_stream.read(min(IO_BLOCK_SIZE, wanted - part_bytes))
                        if not block:
                            raise ValueError("source ended before its recorded size")
                        part_stream.write(block)
                        whole_hash.update(block)
                        part_hash.update(block)
                        part_bytes += len(block)
                parts.append({
                    "filename": part_path.name,
                    "size_bytes": part_bytes,
                    "sha256": part_hash.hexdigest(),
                })
                remaining_total -= part_bytes
            if source_stream.read(1):
                raise ValueError("source grew while it was being split")
        after = source.stat()
        if (after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns
                or remaining_total != 0):
            raise ValueError("source changed while it was being split")

        manifest: dict[str, Any] = {
            "schema": SCHEMA,
            "original_filename": source.name,
            "total_bytes": total_bytes,
            "total_sha256": whole_hash.hexdigest(),
            "chunk_size_bytes": chunk_size,
            "part_count": part_count,
            "parts": parts,
        }
        with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            created.append(manifest_path)
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
        return manifest_path, manifest
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def _load_manifest(path: Path) -> dict[str, Any]:
    _regular_file(path, "manifest")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("unsupported manifest schema")
    original = data.get("original_filename")
    total = data.get("total_bytes")
    chunk_size = data.get("chunk_size_bytes")
    count = data.get("part_count")
    parts = data.get("parts")
    if not _safe_basename(original):
        raise ValueError("manifest original filename is unsafe")
    if type(total) is not int or total <= 0:
        raise ValueError("manifest total size is invalid")
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("manifest chunk size is invalid")
    if type(count) is not int or not 1 <= count <= MAX_PARTS:
        raise ValueError("manifest part count is invalid")
    if count != (total + chunk_size - 1) // chunk_size:
        raise ValueError("manifest part count does not match its sizes")
    if not _sha256_hex(data.get("total_sha256")):
        raise ValueError("manifest total SHA-256 is invalid")
    if not isinstance(parts, list) or len(parts) != count:
        raise ValueError("manifest parts list is invalid")

    size_sum = 0
    for index, item in enumerate(parts):
        if not isinstance(item, dict):
            raise ValueError("manifest part entry is invalid")
        expected_name = f"{original}.part{index:02d}"
        expected_size = min(chunk_size, total - index * chunk_size)
        if item.get("filename") != expected_name:
            raise ValueError("manifest part order or filename is invalid")
        if type(item.get("size_bytes")) is not int or item["size_bytes"] != expected_size:
            raise ValueError("manifest part size is invalid")
        if not _sha256_hex(item.get("sha256")):
            raise ValueError("manifest part SHA-256 is invalid")
        size_sum += item["size_bytes"]
    if size_sum != total:
        raise ValueError("manifest part sizes do not sum to the total")
    return data


def join_parts(manifest_path: Path, parts_dir: Path, output_path: Path) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    parts_dir = Path(parts_dir)
    output_path = Path(output_path)
    manifest = _load_manifest(manifest_path)
    if parts_dir.is_symlink() or not parts_dir.is_dir():
        raise ValueError("parts directory must be a real directory")
    if output_path.name != manifest["original_filename"]:
        raise ValueError("output filename must match the original filename in the manifest")
    if not output_path.parent.is_dir() or output_path.parent.is_symlink():
        raise ValueError("output parent must be an existing, non-symlink directory")
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError("refusing to overwrite existing reconstructed image")

    whole_hash = hashlib.sha256()
    written = 0
    try:
        with output_path.open("xb") as output:
            for item in manifest["parts"]:
                part_path = parts_dir / item["filename"]
                _regular_file(part_path, "split part")
                part_hash = hashlib.sha256()
                part_bytes = 0
                with part_path.open("rb") as part:
                    while True:
                        block = part.read(IO_BLOCK_SIZE)
                        if not block:
                            break
                        output.write(block)
                        whole_hash.update(block)
                        part_hash.update(block)
                        part_bytes += len(block)
                        written += len(block)
                    if part_bytes != item["size_bytes"] or part_hash.hexdigest() != item["sha256":
                        raise ValueError("split part size or SHA-256 mismatch")
            output.flush()
            os.fsync(output.fileno())
        if written != manifest["total_bytes"] or whole_hash.hexdigest() != manifest["total_sha256"]:
            raise ValueError("reconstructed image size or SHA-256 mismatch")
    except Exception:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return {"total_bytes": written, "part_count": manifest["part_count"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    split_parser = commands.add_parser("split", help="split a private image into upload-sized parts")
    split_parser.add_argument("source", type=Path)
    split_parser.add_argument("output_dir", type=Path)
    split_parser.add_argument("--chunk-size-mib", type=int, default=220)
    join_parser = commands.add_parser(join", help="verify and reconstruct private split parts")
    join_parser.add_argument("manifest", type=Path)
    join_parser.add_argument("parts_dir", type=Path)
    join_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "split":
            manifest_path, manifest = split_image(
                args.source, args.output_dir, args.chunk_size_mib * 1024 * 1024)
            print(f"VH_MAP02_PRIVATE_DISC_SPLIT_PASS parts={manifest['part_count']} "
                  f"total_bytes={manifest['total_bytes']} hashes_in_private_manifest=1 "
                  "original_media_uploaded=0")
        else:
            result = join_parts(args.manifest, args.parts_dir, args.output)
            print(f"VH_MAP02_PRIVATE_DISC_REASSEMBLY_PASS parts={result['part_count']} "
                  f"total_bytes={result['total_bytes']} hashes_verified=1")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
