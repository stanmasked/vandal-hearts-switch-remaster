#!/usr/bin/env python3
"""Audit PC-port VAB tone aliases absent from the validated active-tone model.

The pinned PC-port SsVabOpenHeadSticky constructs a 16-tone view for
every program up to the highest populated program. Empty program IDs
borrow the *next* packed tone block; inactive slots of populated programs
are also parsed. SeqPickTone scans all 16 slots and accepts vag > 0.
This tool is diagnostic/read-only and does not bundle game music.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from tools.inspect_vab_header import inspect_vab_header

TONE_BASE = 32 + 128 * 16
BLOCK_BYTES = 16 * 32


def audit_aliases(vh: Path, vb: Path | None = None) -> dict[str, object]:
    bank = inspect_vab_header(vh, vb_path=vb)
    if not bank.get("tone_table_complete") or not bank.get("vag_size_table_complete"):
        raise ValueError("complete VH tone and VAG-size tables required")
    populated = bank["populated_programs"]
    if not populated:
        raise ValueError("at least one populated program is required")

    # The source loader has a distinct header-declared count and computes
    # highestProg from that count; do not claim a faithful alias view when
    # the two disagree. The standard synthetic fixture has matching counts.
    if bank["programs"] != len(populated):
        raise ValueError(
            "header program count differs from populated program count; "
            "PC-port alias layout cannot be inferred safely"
        )
    highest = populated[-1]["program"]
    with vh.open("rb") as stream:
        stream.seek(TONE_BASE)
        raw = stream.read(len(populated) * BLOCK_BYTES)
    if len(raw) != len(populated) * BLOCK_BYTES:
        raise ValueError("packed tone data truncated")

    active_counts = {entry["program"]: entry["tones"] for entry in populated}
    aliases: list[dict[str, object]] = []
    packed_index = 0
    for program in range(highest + 1):
        active = active_counts.get(program, 0)
        # Matches the upstream block[p] assignment before nBlocks++
        source_program = populated[packed_index]["program"]
        for tone in range(active, 16):
            offset = packed_index * BLOCK_BYTES + tone * 32
            vag = struct.unpack_from("<h", raw, offset + 22)[0]
            if vag <= 0:
                continue
            low, high = raw[offset + 6], raw[offset + 7]
            playable = (vag <= bank["vags"] and low <= high and high <= 127)
            aliases.append({
                "kind": "empty_program" if not active else "inactive_slot",
                "program": program,
                "tone": tone,
                "source_program": source_program,
                "vag": vag,
                "key_min": low,
                "key_max": high,
                "valid_vag_and_range": playable,
            })
        if active:
            packed_index += 1

    gaps = sum(item["kind"] == "empty_program" for item in aliases)
    inactive = len(aliases) - gaps
    return {
        "schema": 1,
        "reference": "VandalHearts-PcPort SsVabOpenHeadSticky/SeqPickTone",
        "header_sha256": bank["header_sha256"],
        "tone_table_sha256": bank["tone_table_sha256"],
        "highest_populated_program": highest,
        "gap_alias_tones": gaps,
        "inactive_slot_tones": inactive,
        "aliases": aliases,
        "requires_pcport_compatibility_review": bool(aliases),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vh", type=Path, help="locally owned VAB VH")
    parser.add_argument("--vb", type=Path, help="optional VB for size verification")
    parser.add_argument(
        "--strict", action="store_true",
        help="exit 4 if any potentially selectable alias exists",
    )
    args = parser.parse_args()
    try:
        report = audit_aliases(args.vh, args.vb)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 4 if args.strict and report["requires_pcport_compatibility_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
