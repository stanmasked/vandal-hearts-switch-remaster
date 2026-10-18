# Vandal Hearts Remake — Stage319: zero-clock-read running audio worker stop gate

## Why this matters

Stage317 records when the audio worker **first observes** its running
mailbox flag is false, allowing a source-bound comparison with the last
returned audout buffer and the worker cleanup entrance. A timestamp
is only useful if the diagnostic work itself does not materially alter
normal audio production.

Stage318 adds an independent replay of original worker-stop source
CSV and prior original exit/audout/optical evidence. Its real NeXium
source workflow must finish before archive replay can succeed.

## Implementation

`source/vh_audio_worker_stop_gate.h` isolates the **existing one**
`vh_game_music_mailbox_running(&mailbox)` atomic running-flag read at
the start of the audio producer loop.

On `running != 0` it:

- Returns immediately to the existing PCM producer loop.
- Never calls `scene_trace_now_ns()` (or the supplied guest clock).
- Never writes or even reads the optional stop-observed marker.
- Does not allocate, wait, lock, submit audio or perform file I/O.

Only when that same single running-flag read is **false** does it
read the guest monotonic clock and mark a one-shot witness, then
return false so the existing worker loop exits. If the mailbox, clock or witness
is unavailable, the worker exits safely without manufacturing a stop
observation or querying the guest clock. On a real non-null mailbox,
the original single atomic running-flag read remains unchanged.
Repeated invocation after a first observed stop doesn't replace
the initial timestamp or call the clock again.

The audio source uses the portable helper, but still invokes the same
atomic running-flag check **once per outer PCM loop iteration**.
It does not change SPU rendering, audout calls, buffer data, worker
teardown ordering or game rules.

## Host proof

`tests/test_vh_audio_worker_stop_gate.c` initializes the actual
portable game-music mailbox and invokes the real helper for **100,000
running iterations**, asserting zero clock-provider calls and zero
witness writes. It then stops the mailbox, requires exactly one clock
read and a first-write-wins recorded timestamp, and checks repeated
stop, unavailable clock/witness and a synthetic null-mailbox fail-closed
case.

The same test is part of both `make test`/`make test-audio-stream`
and the standalone GCC/Clang Host SPU workflow.

This is a portable regression guard, **not** a measured guest CPU
overhead benchmark or a substitute for real NeXium source capture.
The timestamp remains guest software monotonic time, not host
PulseAudio samples, DAC output or physical speaker sound.
