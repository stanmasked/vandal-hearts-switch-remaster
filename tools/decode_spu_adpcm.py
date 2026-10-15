#!/usr/bin/env python3
"""Decode raw PlayStation SPU-ADPCM blocks into mono signed 16-bit PCM.

Input is *raw* ADPCM (no standalone VAGp header, no VH/VB auto-detection).
The sample rate is NOT stored in raw blocks: the CLI requires an explicit rate.
No resampling, ADSR, voice mixing, or loop playback is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

BLOCK_BYTES = 16
SAMPLES_PER_BLOCK = 28
COEFF_POS = (0, 60, 115, 98, 122)
COEFF_NEG = (0, 0, -52, -55, -60)


@dataclass(frozen=True)
class DecodedSpu:
    pcm: bytes
    block_count: int
    loop_start_frame: int | None
    loop_end_frame: int | None
    first_end_block: int | None

    @property
    def frames(self) -> int:
        return len(self.pcm) // 2


def decode_spu_blocks(raw: bytes) -> DecodedSpu:
    """Strict block decoder; reconstruct all blocks, including trailing ones.

    The decoded PCM samples are clipped *before* updating predictor history,
    as in the original PC-port DecodeVag(). Flags record sample/loop metadata
    but do not change the decoded block count.
    """
    if not raw or len(raw) % BLOCK_BYTES:
        raise ValueError("SPU ADPCM requires nonempty 16-byte-aligned data")

    pcm = bytearray()
    old = older = 0
    loop_mark = None
    loop_start = loop_end = None
    first_end = None
    for index in range(len(raw) // BLOCK_BYTES):
        block = raw[index * BLOCK_BYTES:(index + 1) * BLOCK_BYTES]
        shift = block[0] & 15
        predictor = block[0] >> 4
        flags = block[1]
        if predictor >= len(COEFF_POS):
            raise ValueError(f"block {index}: invalid predictor {predictor}")
        if shift > 12:
            raise ValueError(f"block {index}: invalid shift {shift}")
        if flags & ~7:
            raise ValueError(f"block {index}: unknown loop/end flag bits 0x{flags:02x}")
        if flags & 4:
            loop_mark = index * SAMPLES_PER_BLOCK
        if flags & 1 and first_end is None:
            first_end = index

        f0, f1 = COEFF_POS[predictor], COEFF_NEG[predictor]
        for byte in block[2:]:
            for nibble in (byte & 15, byte >> 4):
                signed16 = ((nibble - 16) if nibble & 8 else nibble) << 12
                sample = (signed16 >> shift) + ((old * f0 + older * f1 + 32) >> 6)
                sample = max(-32768, min(32767, sample))
                pcm += struct.pack("<h", sample)
                older, old = old, sample
        if flags & 3 == 3:
            # The reference implementation defaults to the start of the
            # sample when an end+repeat block has no explicit loop marker.
            loop_start = 0 if loop_mark is None else loop_mark
            loop_end = (index + 1) * SAMPLES_PER_BLOCK

    return DecodedSpu(bytes(pcm), len(raw) // BLOCK_BYTES,
                      loop_start, loop_end, first_end)


def wav_bytes(decoded: DecodedSpu, sample_rate: int) -> bytes:
    if type(sample_rate) is not int or not 1 <= sample_rate <= 192000:
        raise ValueError("explicit sample rate must be an integer in 1..192000")
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(decoded.pcm)
    return stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="headerless 16-byte SPU ADPCM blocks")
    parser.add_argument("output", type=Path, help="new mono 16-bit WAV path")
    parser.add_argument("--sample-rate", type=int, required=True,
                        help="explicit playback Hz; cannot be inferred from raw SPU blocks")
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("output cannot overwrite input")
        decoded = decode_spu_blocks(args.input.read_bytes())
        wav = wav_bytes(decoded, args.sample_rate)
        with args.output.open("xb") as destination:
            destination.write(wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "blocks": decoded.block_count,
        "frames": decoded.frames,
        "sample_rate": args.sample_rate,
        "pcm_sha256": hashlib.sha256(decoded.pcm).hexdigest(),
        "loop_start_frame": decoded.loop_start_frame,
        "loop_end_frame": decoded.loop_end_frame,
        "first_end_block": decoded.first_end_block,
        "warning": ("PCM reconstruction only: this does not establish the "
                    "correct game playback pitch, ADSR, loops, or audio fidelity."),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
