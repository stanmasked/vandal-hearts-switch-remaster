#!/usr/bin/env python3
"""Decode one selected VAG from a local VH+VB bank into mono WAV.

The VH/VB metadata must pass structural and size-bound validation. Raw VAG
sample bytes stay local and are never written to an intermediate file.
No ADSR, pitch synthesis, sequencer timing or audio loops are rendered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.decode_spu_adpcm import decode_spu_blocks, wav_bytes
from tools.inspect_vab_header import inspect_vab_header


def decode_vab_sample(vh: Path, vb: Path, *, vag: int,
                      sample_rate: int) -> tuple[bytes, dict[str, object]]:
    """Return a mono WAV and audit metadata; leave input files untouched."""
    if type(vag) is not int or vag < 1:
        raise ValueError("VAG number must be a positive integer (one-based)")
    if type(sample_rate) is not int or not 1 <= sample_rate <= 192000:
        raise ValueError("explicit sample rate must be an integer in 1..192000")

    bank = inspect_vab_header(vh, vb_path=vb)
    if not bank["vag_size_table_complete"] or not bank["vb_bounds_verified"]:
        raise ValueError("complete VH and VB bounds verification required")
    if vag > bank["vags"]:
        raise ValueError(f"VAG {vag} exceeds bank VAG count {bank['vags']}")
    entry = bank["vag_entries"][vag - 1]
    size = entry["size_bytes"]
    if size <= 0:
        raise ValueError(f"VAG {vag} has no sample data")

    with vb.open("rb") as source:
        source.seek(entry["offset_bytes"])
        raw = source.read(size)
    if len(raw) != size:
        raise ValueError(f"VAG {vag} truncated while reading VB")
    decoded = decode_spu_blocks(raw)
    wav = wav_bytes(decoded, sample_rate)
    references = [
        {"program": program["program"], "tone": tone["tone"],
         "key_min": tone["key_min"], "key_max": tone["key_max"],
         "adsr1": tone["adsr1"], "adsr2": tone["adsr2"]}
        for program in bank["populated_programs"]
        for tone in program["active_tones"]
        if tone["vag"] == vag
    ]
    return wav, {
        "vag": vag,
        "sample_rate_hz": sample_rate,
        "adpcm_offset_in_vb": entry["offset_bytes"],
        "adpcm_size_bytes": size,
        "adpcm_sha256": hashlib.sha256(raw).hexdigest(),
        "header_sha256": bank["header_sha256"],
        "tone_table_sha256": bank["tone_table_sha256"],
        "vag_size_table_sha256": bank["vag_size_table_sha256"],
        "vb_bounds_verified": bank["vb_bounds_verified"],
        "pcm_frames": decoded.frames,
        "pcm_sha256": hashlib.sha256(decoded.pcm).hexdigest(),
        "loop_start_frame": decoded.loop_start_frame,
        "loop_end_frame": decoded.loop_end_frame,
        "first_end_block": decoded.first_end_block,
        "referencing_tones": references,
        "warning": (
            "Decoded WAV is an offline diagnostic only. Explicit sample-rate "
            "does not establish original pitch; no ADSR, loop playback, "
            "SEQ timing, reverb, or console audio has been reproduced."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vh", type=Path, help="local standalone VAB header file")
    parser.add_argument("vb", type=Path, help="local matching VAB body file")
    parser.add_argument("output", type=Path, help="new WAV file; never overwritten")
    parser.add_argument("--vag", type=int, required=True,
                        help="one-based VAG entry from the size table")
    parser.add_argument("--sample-rate", type=int, required=True,
                        help="explicit diagnostic playback Hz; not inferred")
    args = parser.parse_args()
    try:
        # Exclusive creation also rejects an existing file/symlink; require
        # a fresh destination even if the old WAV was produced by this tool.
        if args.output.resolve() in (args.vh.resolve(), args.vb.resolve()):
            raise ValueError("output cannot alias a source VH or VB")
        wav, report = decode_vab_sample(
            args.vh, args.vb, vag=args.vag, sample_rate=args.sample_rate
        )
        with args.output.open("xb") as destination:
            destination.write(wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
