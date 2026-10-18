# Vandal Hearts Remake — Stage307: guest software exit event timeline

## Why

Stage306's independent source replay confirmed that in three separate
NeXium virtual PCM recordings, the terminal digital-zero run begins
between host file-size snapshots around actual Plus keydown and keyup.
That alignment still cannot prove when the **guest game loop**, **audio
worker**, or **audout** acted: the host `stat` snapshots share neither
the libnx guest monotonic clock nor the DAC playback clock.

Stage307 introduces an **independent, opt-in diagnostic-only** timeline
of five real guest software events without changing audio behavior.

## Guest event sites

These events use the same `armGetSystemTick() -> armTicksToNs()`
clock, each in a first-write-wins C11 atomic slot:

1. `plus_observed`: game loop sees the Plus button in `padGetButtonsDown`,
   before processing the quit action.
2. `stop_requested`: main requests the audio mailbox stop.
3. `worker_cleanup_entered`: the audio worker enters cleanup, potentially
   from natural failure as well as a cooperative quit.
4. `audout_closed`: worker completed the existing `output_stop` and
   `output_close` sequence, even if the service previously failed.
5. `worker_joined`: main completed `threadWaitForExit` and
   `threadClose`.

The worker and gameplay hot paths allocate no memory, acquire no mutex,
produce no CSV and perform no file operations for these events.
The atomic values are copied/exported **only after** the worker joins.
Existing audio production, taper, service-stop, and page ownership logic
remain unchanged.

## SD evidence

After audio join, the main thread attempts an **exclusively created**
numbered guest file:
`sdmc:/switch/vandal-hearts-remake/audio-exit-timeline-000.csv`
(or the next unoccupied number up to 031, never truncating an earlier
user session). The CSV uses the fixed schema:

```csv
event,guest_monotonic_ns
plus_observed,123456
stop_requested,123500
worker_cleanup_entered,123700
audout_closed,123900
worker_joined,124000
```

Those integers are examples, not measurements.

`tools/audit_nexium_guest_exit_timeline.py` reads the actual
isolated NeXium SD root, validates a single canonical guest CSV,
and checks the event order, nonzero timestamps, monotonicity and
distinctness for a complete cooperative quit. Missing events remain
explicitly *incomplete* evidence. If NeXium does not provide the guest
file through its SD mirror, the report states
`NOT_OBSERVED_GUEST_SD_TRANSPORT`: it does **not** invent timestamps.

Runtime evidence:
`runtime-evidence/guest-audio-exit-timeline-stage307.json`.

## Tests and limitations

- C11 host GCC/Clang: `tests/test_vh_audio_exit_timeline.c`.
- Python parser and missing guest SD source:
  `tests/test_audit_nexium_guest_exit_timeline.py`.
- Host C/Python and libnx NRO build; NeXium NRO smoke.

These events timestamp the **guest software operations** only.
There is still no verified conversion between host file-size snapshots
and guest monotonic timestamps. `audout_closed` does not prove when the
physical DAC or speaker stopped, and no original retail soundtrack or
audible dropout is confirmed. The project still needs a hardware audio
test to establish audible behavior.
