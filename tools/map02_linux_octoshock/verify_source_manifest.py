#!/usr/bin/env python3
"""Verify the native Octoshock probe matches BizHawk 2.11's exact upstream manifest."""
from __future__ import annotations

import argparse
import posixpath
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

UPSTREAM_COMMIT = "427556b5ef3ac437eba754d90c5e7e9096c9a8df"
UPSTREAM_TREE = "24f43550ff70776a86a2d7b64d09993dd09021d9"
EXPECTED_SOURCE_COUNT = 41


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source), *args], text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).with_name("source-manifest.txt"))
    args = parser.parse_args()
    source = args.source_root.resolve()

    commit = git(source, "rev-parse", "HEAD")
    tree = git(source, "rev-parse", "HEAD:psx/octoshock")
    if commit != UPSTREAM_COMMIT:
        raise SystemExit(f"unexpected upstream commit: {commit}")
    if tree != UPSTREAM_TREE:
        raise SystemExit(f"unexpected upstream Octoshock tree: {tree}")

    expected = [
        line.strip() for line in args.manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(expected) != EXPECTED_SOURCE_COUNT or len(set(expected)) != len(expected):
        raise SystemExit("manifest must contain 41 unique source paths")

    project = source / "psx/octoshock/bizhawk/octoshock.vcxproj"
    xml = ET.parse(project).getroot()
    includes = []
    for element in xml.iter():
        if element.tag.rsplit("}", 1)[-1] != "ClCompile":
            continue
        include = element.attrib.get("Include")
        if include:
            normalized = posixpath.normpath(
                posixpath.join("bizhawk", include.replace("\\\\", "/").replace("\\", "/"))
            )
            if normalized.startswith("../") or normalized == "..":
                raise SystemExit(f"project source escapes source root: {include}")
            includes.append(normalized)

    if len(includes) != EXPECTED_SOURCE_COUNT or len(set(includes)) != len(includes):
        raise SystemExit(f"upstream VS project source count changed: {len(includes)}")
    if set(includes) != set(expected):
        missing = sorted(set(includes) - set(expected))
        extra = sorted(set(expected) - set(includes))
        raise SystemExit(f"manifest/project mismatch; missing={missing}; extra={extra}")

    absent = [relative for relative in expected if not (source / "psx/octoshock" / relative).is_file()]
    if absent:
        raise SystemExit(f"source files absent from pinned upstream tree: {absent}")

    print(
        f"VH_MAP02_OCTOSHOCK_SOURCE_MANIFEST_PASS commit={commit} "
        f"tree={tree} source_files={len(expected)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"git source verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
