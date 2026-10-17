# Vandal Hearts Remake — Stage 276: No-Switch NeXium Audio Control

**Implementation committed; full NeXium idle-control CI acceptance pending.**
**HARDWARE NOT TESTED; no speaker output, DAC or causal claims.**

## Experimental rationale

The preceding [Stage 275](SWITCH_STAGE275_NEXIUM_SAME_NRO_SLOW_RUNS.md)
reverified four original-SD-audited, same-NRO runs with **ten deliberate
A/B scene transitions** each. Across 7,815 `audoutPlayBuffer` calls,
86 lasted ≥40 ms and ten lasted ≥50 ms. The association between
individual scene serials and slow calls was not reproducible.

Stage 276 adds a **within-workflow negative control**: run the
**identical NRO** again, in a new isolated guest data root with the
initial music playing, for at least 50 guest audio seconds but send
**zero A/B scene-changing keys**.

The existing `tools/capture_nexium_scene_soak.sh` retains its
original ten-switch default. Only `SOAK_MODE=idle` selects the new
control: 11 framebuffer snapshots with the music scene unchanged,
a longer steady-state observation interval, and one final Plus key
for clean shutdown and post-join SD export. This is not a second,
recompiled or silent NRO, and no zero-input control is inferred
from a previously changing scene trace.

Two distinct original NeXium guest SD folders are required:

- A/B transitions:
  `$RUNNER_TEMP/vh-nexium-stage268-$GITHUB_RUN_ID`
- No-switch control:
  `$RUNNER_TEMP/vh-nexium-idle276-$GITHUB_RUN_ID`

Each captures **its own** original SD scene, queue, latency, absolute
clock origin, and exact ≥40 ms calls. Already published evidence
is never silently overwritten. Independent copies and status
receipts are retained for later review.

## Fail-closed requirements

`tools/audit_nexium_audout_idle_control.py` runs against the **live
original isolated guest SD** before GitHub deletes the runner. It
checks:

1. Same-workflow NRO provenance (commit, Actions run, attempt and SHA-256).
2. Original/copy byte identity and independently successful post-join
   writer receipts for queue, per-call duration histogram, clock
   and bounded exact slow-call CSVs.
3. The scene CSV contains **exactly three** startup events:
   `ACCEPT(0, scene=1)`, `SUBMIT_CALL(0, scene=1)`,
   `RELEASE_RETURN(0, scene=1)`. **Zero** INPUT, POST,
   unexpected scene changes, dropped trace entries, or retries.
4. The first `audoutPlayBuffer` timestamp lies **within** the
   independent startup submit/return interval of the guest monotonic
   clock — not a host-aligned time estimate.
5. At least 50 second-window buckets, no missing or reordered
   original-SD observations, zero audout errors, and all original
   per-second counts/bounds consistent with full-session totals.
6. Every ≥40 ms individual begin/end timestamp matches its
   per-second bucket, exact call number and ≥50 ms classification.
   The 128-slot recorder must **not** overflow.
7. Eleven host screenshot checkpoints, with the ten later ones
   explicitly designated `idle_1` through `idle_10` — a
   deliberate no-A/B input schedule, not a replay of switch
   snapshots.

The NeXium Actions workflow compares the original-SD-verification
report with the earlier **ten-switch audit of the same NRO**.
It stores both counts, each number of audout attempts, and a
same-NRO negative-control report in
`runtime-evidence/idle-control/idle-vs-switch.json`.

Synthetic regressions reject inserted scene INPUTs, altered
SD originals, changed file-location manifests, missing or invalid
status receipts, altered slow-call summaries, missing audio
windows, wrong NRO/run identity, and scene-changing host schedules.

## Evidence interpretation

Compare durations normalized by attempted audout calls, not just
raw counts, because the virtual service can submit a different
number of buffers during each approximately 50–60 s capture.
No-switch vs switching is an **observational control**,
not a randomized blinded causal experiment: CPU load, emulator
scheduling, initial startup, audio device state, PulseAudio server,
and wall-clock timing may vary between captures.

A difference in 40/50 ms slow-call rates in virtual NeXium
does **not** prove scene transitions cause stalls or that game
music can be heard without skips on Nintendo Switch hardware.
No retail Vandal Hearts soundtrack is bundled or authenticated.

## Acceptance

Real **idle original SD** and normal-switch original SD must both pass
in one live Actions run, using the exact same current-run NRO SHA-256.
Before that result, the tool and synthetic tests are implemented
but **the controlled baseline itself is not yet verified**.
