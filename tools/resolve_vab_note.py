#!/usr/bin/env python3
"""Resolve a PS1 SEQ note to VAB program/tone/VAG metadata (read-only).

Matches the lookup order of VandalHearts-PcPort's SeqPickTone:
requested program's first matching range, then the first global range,
then the nearest *lower range boundary* globally. This is a lookup
diagnostic, not an audio synthesizer or a hardware-accurate pitch model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_vab_header import inspect_vab_header


def _signed_byte(raw: int) -> int:
    return raw - 256 if raw >= 128 else raw


def resolve_note(vh: Path, *, program: int, note: int,
                 vb: Path | None = None) -> dict[str, object]:
    """Select a playable VAG, retaining original sparse program IDs."""
    if type(program) is not int or not 0 <= program < 128:
        raise ValueError("program must be an integer in 0..127")
    if type(note) is not int or not 0 <= note <= 127:
        raise ValueError("MIDI note must be an integer in 0..127")
    bank = inspect_vab_header(vh, vb_path=vb)
    if not bank["tone_table_complete"] or not bank["vag_size_table_complete"]:
        raise ValueError("complete VH program, tone and VAG size tables required")

    # Each tuple retains true program number and 0-based tone slot, even
    # when preceding programs have nTone == 0 (no packed tone block).
    indexed = [(p["program"], tone)
               for p in bank["populated_programs"]
               for tone in p["active_tones"]]
    if not indexed:
        raise ValueError("VAB contains no playable tones")

    def contains(tone: dict[str, int]) -> bool:
        return tone["key_min"] <= note <= tone["key_max"]

    matches_requested = [
        (p, t) for p, t in indexed if p == program and contains(t)
    ]
    if matches_requested:
        selected_program, tone = matches_requested[0]
        lookup = "requested_program_range"
    else:
        matches_global = [(p, t) for p, t in indexed if contains(t)]
        if matches_global:
            selected_program, tone = matches_global[0]
            lookup = "global_range"
        else:
            # The PC-port fallback compares distance to *key_min*, not
            # to the nearest endpoint; ties preserve first table order.
            selected_program, tone = min(
                indexed, key=lambda item: abs(item[1]["key_min"] - note)
            )
            lookup = "global_nearest_lower_bound"

    program_attr = next(p for p in bank["populated_programs"]
                        if p["program"] == selected_program)
    vag = tone["vag"]
    sample = bank["vag_entries"][vag - 1]
    if not sample["size_bytes"]:
        raise ValueError("selected VAG contains no compressed sample bytes")
    center = _signed_byte(tone["center"])
    shift = _signed_byte(tone["fine_tune"])
    # Mirrors the PC port's *approximate* equal-tempered PitchRatio
    # (SEQ fine argument = 0). Not PS1's exact pitch-table rounding.
    semitones = (note - center) - shift / 128.0
    ratio = 2.0 ** (semitones / 12.0)
    pitch_step = int(ratio * 4096.0)

    return {
        "requested_program": program,
        "note": note,
        "lookup": lookup,
        "selected_program": selected_program,
        "bank_master_volume": bank["master_volume"],
        "program_volume": program_attr["volume"],
        "program_pan": program_attr["pan"],
        "tone": tone["tone"],
        "vag": vag,
        "key_min": tone["key_min"],
        "key_max": tone["key_max"],
        "center_signed": center,
        "shift_signed": shift,
        "volume": tone["volume"],
        "pan": tone["pan"],
        "mode": tone["mode"],
        "adsr1": tone["adsr1"],
        "adsr2": tone["adsr2"],
        "adpcm_offset_in_vb": sample["offset_bytes"],
        "adpcm_size_bytes": sample["size_bytes"],
        "vh_header_sha256": bank["header_sha256"],
        "tone_table_sha256": bank["tone_table_sha256"],
        "vag_size_table_sha256": bank["vag_size_table_sha256"],
        "vb_bounds_verified": bank["vb_bounds_verified"],
        "pitch_ratio_approx": ratio,
        "pitch_step_approx": pitch_step,
        "warning": (
            "Diagnostic lookup following PC-port SeqPickTone, not proof of "
            "original PS1 selection or timing. Approximate pitch is not "
            "a rendered note. No ADSR, loops, reverb or audio output."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vh", type=Path)
    parser.add_argument("--vb", type=Path,
                        help="optional matching local VB for size-bound checks")
    parser.add_argument("--program", type=int, required=True)
    parser.add_argument("--note", type=int, required=True)
    args = parser.parse_args()
    try:
        result = resolve_note(
            args.vh, program=args.program, note=args.note, vb=args.vb
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
