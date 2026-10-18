# Vandal Hearts Remake — Stage325: host dual-clock Plus-control witness

## Why this stage exists

The original failed Stage304 archive from NeXium workflow
[39157976877](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39157976877)
contains a backward **host wall-clock** change of **−347 ms** between
`before_plus_down` and `after_plus_up`. Both file sizes increased.
The independently completed [source replay 39164847668](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39164847668)
proved the exact archived CSV deltas, but it did not establish whether
a wall clock correction (NTP, VM host adjustments or another cause)
occurred during the original live run. No claim about SPU malfunction,
music dropout or physical playback follows from that archive.

## New future-capture evidence only

`tools/capture_nexium_scene_audio.sh` preserves the exact legacy
`scene-exit-controls.csv` header:

```text
event,pcm_bytes,host_epoch_ms
```

For **new** NeXium captures only, a single Python process now records
each Plus-control event in both the legacy file and a companion file:

```text
scene-exit-controls-monotonic.csv
event,pcm_bytes,host_epoch_ms,host_monotonic_ns
```

The same file size and wall epoch are written to both files.
`host_monotonic_ns` comes from Python's `time.monotonic_ns()`.
These are host process observations, **not** guest clock ticks,
PCM frame timestamps, DAC output times or a host-to-guest fitted clock.
The legacy clock remains **subject to all original Stage304 strict
ordering and source-provenance checks**; positive monotonic deltas
cannot make a failed legacy Stage304 source pass.

A new isolated audit,
`tools/audit_nexium_host_clock_pairs.py audit`,
requires three canonical matching events, exact legacy/companion
value identity, and strictly advancing monotonic samples. It emits
only original CSV SHA-256 digests, event labels, file-size deltas,
wall-millisecond deltas and monotonic-nanosecond deltas in
`runtime-evidence/host-dual-clock-stage325.json`, without absolute
timestamps or PCM contents. It refuses overwrites and malformed,
missing, duplicate, truncated or altered CSV evidence.

## Test and CI integration

`tests/test_audit_nexium_host_clock_pairs.py` contains 11 synthetic
negative/positive tests. One test reproduces the historic −347 ms
wall-clock pattern while monotonic host time increases, and still
requires the unchanged Stage304 legacy verifier to reject that
nonmonotone wall-clock source.

The tests are included in `.github/workflows/host-audio-tests.yml`.
The NeXium smoke workflow performs the independent paired-source
audit immediately after new scene capture; a failed pair audit stops
the workflow. The existing Stage304 audit remains a separate strict
step and cannot be bypassed by Stage325.

## Evidentiary limits

- Historical runs do not contain this supplemental monotonic CSV:
  **no monotonic evidence can be retroactively created**.
- A monotonically increasing host clock does not establish the cause
  of backward wall-clock jumps or prove guest input/audio timing.
- A successful NeXium capture is not an acoustic measurement on a
  physical Nintendo Switch.
- This stage changes no game logic, SPU synthesis, audout buffering,
  audible sound, original game sources or soundtrack.
