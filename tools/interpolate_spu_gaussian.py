#!/usr/bin/env python3
"""Exact integer coefficient/sample-selection path of PC-port SPU Gaussian fetch.

This deliberately matches the *software PC port*'s per-product arithmetic
shift and clipping. It does not claim cycle-accurate original PS1 hardware
floating point, reverb, timing or mixing behaviour.
"""
from __future__ import annotations

from typing import Sequence
from tools.spu_gaussian_table import GAUSS
from tools.simulate_spu_voice import SpuSampleCursor


def gaussian_voice_sample(pcm: Sequence[int], cursor: SpuSampleCursor) -> int:
    """Read one four-tap sample at current phase without advancing the cursor.

    A wrapped voice uses its current loop tail as history on subsequent
    readings; startup history before sample zero is zero.
    """
    idx = cursor.index
    gi = (cursor.phase >> 4) & 0xFF

    def sample(position: int) -> int:
        if cursor.looped and cursor.loop_end > cursor.loop_start:
            if position < cursor.loop_start:
                position = cursor.loop_end - (cursor.loop_start - position)
        return pcm[position] if 0 <= position < len(pcm) else 0

    # The PC port performs each Q15 multiplication and right-shift
    # separately, then sums. A combined sum followed by one shift
    # changes rounding by 1-3 PCM units for many inputs.
    result = (GAUSS[0xFF - gi] * sample(idx - 3)) >> 15
    result += (GAUSS[0x1FF - gi] * sample(idx - 2)) >> 15
    result += (GAUSS[0x100 + gi] * sample(idx - 1)) >> 15
    result += (GAUSS[gi] * sample(idx)) >> 15
    return max(-32768, min(32767, result))
