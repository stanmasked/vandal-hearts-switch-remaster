#!/usr/bin/env python3
"""Deterministic host-only PS1 SPU ADSR and sample-position state machines.

This models pc_spu.c's per-44100-Hz envelope changes and its 20.12 fixed
point sample cursor. It does not render/mix PCM, interpolate samples, or
emulate the complete PlayStation SPU. No copyrighted assets are required.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RATE = 44100
ADSR_MAX = 0x7FFF
COUNTER_BIT = 0x8000
UNITY_STEP = 0x1000
MAX_STEP = 0x4000
PHASES = ("off", "attack", "decay", "sustain", "release")


def _trunc_zero(n: int, divisor: int) -> int:
    """Integer division with C99 truncation toward zero (unlike Python //)."""
    return n // divisor if n >= 0 else -((-n) // divisor)


@dataclass
class SpuEnvelope:
    """Envelope fields follow pc_spu.c SpuDecodeAdsr and SpuAdsrAdvance."""

    adsr1: int
    adsr2: int
    level: int = field(default=0, init=False)
    counter: int = field(default=0, init=False)
    phase: str = field(default="attack", init=False)

    def __post_init__(self) -> None:
        if type(self.adsr1) is not int or not 0 <= self.adsr1 <= 0xFFFF:
            raise ValueError("ADSR1 must be a 16-bit unsigned integer")
        if type(self.adsr2) is not int or not 0 <= self.adsr2 <= 0xFFFF:
            raise ValueError("ADSR2 must be a 16-bit unsigned integer")
        ar = (self.adsr1 >> 8) & 0x7F
        sr = (self.adsr2 >> 6) & 0x7F
        sl = self.adsr1 & 15
        self.ar_shift, self.ar_step = ar >> 2, ar & 3
        self.attack_exp = bool(self.adsr1 & 0x8000)
        self.dr_shift = (self.adsr1 >> 4) & 15
        self.sl_target = min(ADSR_MAX, (sl + 1) << 11)
        self.sr_shift, self.sr_step = sr >> 2, sr & 3
        self.sustain_exp = bool(self.adsr2 & 0x8000)
        self.sustain_decrease = bool(self.adsr2 & 0x4000)
        self.rr_shift = self.adsr2 & 31
        self.release_exp = bool(self.adsr2 & 0x20)

    def key_off(self) -> None:
        if self.phase != "off":
            self.phase = "release"

    def _rate_step(self, shift: int, step: int, exponential: bool,
                   decreasing: bool, rate_all_ones: bool) -> None:
        if rate_all_ones:
            return
        delta = 7 - step
        if decreasing:
            delta = ~delta
        if shift < 11:
            delta <<= 11 - shift
        increment = COUNTER_BIT
        if shift > 11:
            increment >>= shift - 11
        if exponential and not decreasing and self.level > 0x6000:
            if shift < 10:
                delta >>= 2
            elif shift >= 11:
                increment >>= 2
            else:
                delta >>= 1
                increment >>= 1
        elif exponential and decreasing:
            delta = _trunc_zero(delta * self.level, 0x8000)
            if self.phase == "release" and delta == 0 and self.level > 0:
                delta = -1
        increment = max(1, increment)
        counter = self.counter + increment
        self.counter = counter & (COUNTER_BIT - 1)
        if not counter & COUNTER_BIT:
            return
        self.level += delta
        if not decreasing:
            self.level = max(0, min(ADSR_MAX, self.level))
        elif self.level < 0:
            self.level = 0

    def advance(self) -> bool:
        """Run one output-sample envelope tick; False means voice finished."""
        if self.phase == "attack":
            self._rate_step(self.ar_shift, self.ar_step, self.attack_exp,
                            False, (self.ar_shift << 2 | self.ar_step) == 0x7F)
            if self.level >= ADSR_MAX:
                self.level = ADSR_MAX
                self.phase = "decay"
        elif self.phase == "decay":
            if self.level <= self.sl_target:
                self.level = self.sl_target
                self.phase = "sustain"
            else:
                self._rate_step(self.dr_shift, 0, True, True, False)
                if self.level <= self.sl_target:
                    self.level = self.sl_target
                    self.phase = "sustain"
        elif self.phase == "sustain":
            self._rate_step(self.sr_shift, self.sr_step, self.sustain_exp,
                            self.sustain_decrease,
                            (self.sr_shift << 2 | self.sr_step) == 0x7F)
            if self.sustain_decrease and self.level <= 0:
                self.phase = "off"
                return False
        elif self.phase == "release":
            if self.level <= 0:
                self.phase = "off"
                return False
            self._rate_step(self.rr_shift, 0, self.release_exp, True,
                            self.rr_shift == 31)
            if self.level <= 0:
                self.phase = "off"
                return False
        else:
            return False
        return True


@dataclass
class SpuSampleCursor:
    """PS1 sample position update with unity pitch = 0x1000.

    The cursor tracks the position AFTER each output sample was consumed;
    the caller should read the current position BEFORE advancing it.
    """
    length: int
    loop_start: int
    loop_end: int
    pitch_step: int
    phase: int = field(default=0, init=False)
    looped: bool = field(default=False, init=False)
    active: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if type(self.length) is not int or self.length <= 0:
            raise ValueError("sample length must be a positive integer")
        if type(self.pitch_step) is not int:
            raise ValueError("pitch step must be an integer")
        if type(self.loop_start) is not int or type(self.loop_end) is not int:
            raise ValueError("loop boundaries must be integers")
        if self.loop_end > self.loop_start and not (
            0 <= self.loop_start < self.loop_end <= self.length
        ):
            raise ValueError("loop boundaries outside the sample")
        self.pitch_step = max(1, min(MAX_STEP, self.pitch_step))

    @property
    def index(self) -> int:
        return self.phase >> 12

    @property
    def fraction(self) -> int:
        return self.phase & (UNITY_STEP - 1)

    def advance(self) -> bool:
        if not self.active:
            return False
        self.phase += self.pitch_step
        if self.loop_end > self.loop_start and self.loop_start >= 0:
            loop_end_phase = self.loop_end << 12
            loop_len_phase = (self.loop_end - self.loop_start) << 12
            if self.phase >= loop_end_phase:
                # Equivalent to pc_spu.c's repeated subtraction, including
                # overshoots at fast pitch (> one sample per output frame).
                wraps = (self.phase - loop_end_phase) // loop_len_phase + 1
                self.phase -= wraps * loop_len_phase
                self.looped = True
        elif self.index >= self.length:
            self.active = False
        return self.active
