#!/usr/bin/env python3
"""Sample-by-sample SPU voice liveness oracle for offline SEQ allocation.

This is a *state* simulation, not a second audio renderer. It advances the
same SpuEnvelope and SpuSampleCursor as the dry stereo mixer, recording
the first frame at which a note can no longer occupy a voice slot.
The caller must supply tone ADSR, decoded PCM frame count, pitch and loop
bounds from its local VH/VB bank. No original assets are bundled.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.simulate_spu_voice import SpuEnvelope, SpuSampleCursor
from tools.mix_spu_stereo import MAX_FRAMES


@dataclass(frozen=True)
class SpuVoiceSpec:
    adsr1: int
    adsr2: int
    pcm_frames: int
    pitch_step: int
    loop_start: int | None
    loop_end: int | None


@dataclass
class SpuVoiceClock:
    spec: SpuVoiceSpec
    start_frame: int
    frame: int = field(init=False)
    envelope: SpuEnvelope = field(init=False)
    cursor: SpuSampleCursor = field(init=False)
    terminal_frame: int | None = field(default=None, init=False)
    key_off_frame: int | None = field(default=None, init=False)

    def __post_init__(self):
        if type(self.start_frame) is not int or not 0 <= self.start_frame < MAX_FRAMES:
            raise ValueError("voice clock start out of range")
        self.frame = self.start_frame
        self.envelope = SpuEnvelope(self.spec.adsr1, self.spec.adsr2)
        self.cursor = SpuSampleCursor(
            self.spec.pcm_frames,
            -1 if self.spec.loop_start is None else self.spec.loop_start,
            -1 if self.spec.loop_end is None else self.spec.loop_end,
            self.spec.pitch_step,
        )

    def advance_to(self, frame: int) -> int | None:
        """Advance through frames [last_frame, frame), return exclusive end.

        ADSR termination at frame n produces no sound at n, hence
        terminal_frame=n. Cursor exhaustion after frame n still renders
        that frame; terminal_frame=n+1. Matches mix_spu_stereo.
        """
        if type(frame) is not int or not self.start_frame <= frame <= MAX_FRAMES:
            raise ValueError("voice clock target out of range")
        if frame < self.frame:
            raise ValueError("voice clock cannot run backwards")
        while self.frame < frame and self.terminal_frame is None:
            if not self.cursor.active or self.envelope.phase == "off":
                self.terminal_frame = self.frame
                break
            if not self.envelope.advance():
                self.terminal_frame = self.frame
                break
            active = self.cursor.advance()
            self.frame += 1
            if not active:
                self.terminal_frame = self.frame
        return self.terminal_frame

    def key_off(self, frame: int) -> int | None:
        """Key off before rendering frame, as in the offline stereo mixer."""
        end = self.advance_to(frame)
        if end is not None:
            return end
        self.envelope.key_off()
        self.key_off_frame = frame
        return None
