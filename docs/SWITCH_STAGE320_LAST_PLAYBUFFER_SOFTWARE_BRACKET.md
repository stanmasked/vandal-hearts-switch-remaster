# Vandal Hearts Remake — Stage320: last successful audoutPlayBuffer software-call bracket

## Why another measurement is useful

The authentic NeXium Stage317 trace and independently reaudited
Stage318 sources report these **guest software clock** intervals:

- Main thread requested music stop → last ordinary PCM page released to
  its audio owner: **11,942,917 ns**.
- Last page release → audio worker saw `running == 0`: **126,666 ns**.
- Worker saw stop → entered cleanup: **106,459 ns**.

This suggests stop detection itself was fast **after buffer return**.
But it is incorrect to call the entire 11.943ms wait a single
`audoutPlayBuffer` syscall without observing that syscall's own
begin and return.

## Exact existing call timestamps, no new clock queries

`source/vh_switch_game_audio.c` already called
`scene_trace_now_ns()` **before** `audoutPlayBuffer` and
**after** the descriptor was returned/checked, for its long-standing
queue/latency telemetry. Stage320 keeps the second reading in a local
variable and forwards exactly that **same begin/end clock pair** to
a fixed-size witness (`vh_audio_last_playbuffer_call.h`).

The witness records the last **successful** original normal PCM
`audoutPlayBuffer` call, its matching begin/end times, the number
of attempted/successful/failed calls and rejected invalid software
clock pairs. The bounded cleanup taper uses a distinct API and is
not reported as the final normal `audoutPlayBuffer` call.

There are **no extra clocks**, additional libnx calls, sleeps,
allocations, locks or I/O inside playback. Errors in optional
telemetry cannot alter the existing service call return.

The original witness is exported only after audio join, to a
separate exclusively created file
`sdmc:/switch/vandal-hearts-remake/audio-last-playbuffer-000.csv`.
Stage307, Stage313 and Stage317 originals are unchanged.

## NeXium proof and source preservation

`tools/audit_nexium_guest_last_playbuffer.py` reads original guest SD,
revalidates original Stage307 exit, Stage313 last normal PCM page return
and Stage317 worker-stop observation, and validates the new file's
seven canonical event rows. It fails closed on duplicate/altered
fields, symlinks, missing sources, non-monotonic timestamps and
incoherent success counters.

It requires:

`last successful call begin <= call return <= page-release witness <= worker observes stop <= worker cleanup`

It classifies the **last successful call** as:

- completed before the main stop request;
- straddled the request while the service call was outstanding; or
- began after the main stop request, before the worker observed stop.

The report separately computes:

- Time spent **inside the last successful service-call bracket**.
- The intersection of that bracket with the period **after the main
  thread requested stop**.
- The gap from the last call's return to the last successful original
  PCM page witness.

The analyzer saves byte-exact
`runtime-evidence/audio-last-playbuffer-000.csv`, verifies SHA-256
and writes
`runtime-evidence/guest-last-playbuffer-stage320.json`.

## Tests and limitations

- C11 GCC/Clang negative and positive service-call chronology tests:
  `tests/test_vh_audio_last_playbuffer_call.c`.
- 13 Python source/chronology and adversarial controls:
  `tests/test_audit_nexium_guest_last_playbuffer.py`.
- Host SPU CI, Makefile host suites and the actual NeXium source
  smoke workflow.

An `audoutPlayBuffer` return means a descriptor was returned by
the service, **not** that the final audible sample reached speakers.
Neither this service bracket nor the earlier 11.943ms software wait
proves a fault, DAC queue status, the PS1 retail soundtrack, or
causal responsibility for digital-zero PCM in a separate host clock.
No guest/host PCM sample-clock synchronization is assumed.
