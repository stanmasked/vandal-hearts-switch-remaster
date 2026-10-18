# Vandal Hearts Remake — Stage293: per-16-call slow latency occupancy

**Stage292 has now passed all CI checks**, including the independent
current-original-SD NeXium [run 39117595627](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39117595627).

The successful Stage292 analysis of its actual current run found:

| API blocking threshold | Stage292 actual phase0 switching-minus-idle /1k calls | All original calls switching-minus-idle /1k calls |
| --- | ---: | ---: |
| 40 ms ≤ duration < 50 ms | +17.857143 | +2.626840 |
| ≥50 ms | 0.000000 | +0.075166 |
| ≥40 ms | +17.857143 | +2.702006 |

The 1-in-16 pre-submit queue service observation is at attempts
1, 17, 33, etc. Only those calls have actual observed queue counts.
The slow-call journal, however, records the exact attempt index and
guest timestamp of **every** ≥40ms software API call.

## What Stage293 adds

`tools/analyze_nexium_slow_call_cycle_occupancy.py` reopens the
same original guest SD evidence for switching and idle, reruns the
Stage291 and Stage292 audits, and demands exact equality with
both previous report objects. It then partitions each uninterrupted
session into consecutive, non-overlapping groups of 16 audout attempts
(the last group may contain fewer than 16).

For each group, it reports exact counts of ≥40ms, 40–<50ms and
≥50ms calls, including whether a slow call fell on phase0 or one
of the **unqueried** phases 1–15.

The report summarizes:
- Groups containing at least one slow call vs groups with two or more;
- Slow-containing groups whose ONLY slow calls were on phases 1–15,
  so the observed phase0 call itself was not slow;
- Adjacent slow calls and pairs exactly 16 attempts apart;
- Longest run of consecutive groups containing a slow call;
- Full / final partial group count and conservation of all attempts.

All counters are based on original, timestamped software calls;
no queue state is fabricated for the unqueried phases. This is
**not** an operating system scheduler trace, a randomized inference,
proof of scene-switch causality or an actual audio-output test.

New workflow step (same original SD-backed NeXium run):

```sh
python3 tools/analyze_nexium_slow_call_cycle_occupancy.py \
 --switch-sd-root "$RUNNER_TEMP/vh-nexium-stage268-$GITHUB_RUN_ID" \
 --idle-sd-root "$RUNNER_TEMP/vh-nexium-idle276-$GITHUB_RUN_ID" \
 --switch-evidence runtime-evidence/scene-soak \
 --idle-evidence runtime-evidence/idle-control \
 --stage290-report runtime-evidence/idle-control/idle-switch-service-probe-comparison.json \
 --stage291-report runtime-evidence/idle-control/idle-switch-phase-sensitivity.json \
 --stage292-report runtime-evidence/idle-control/idle-switch-phase-selection-gap.json \
 --switch-slow-report runtime-evidence/scene-soak/soak-audout-exact-slow-verification.json \
 --idle-verdict runtime-evidence/idle-control/idle-audout-verification.json \
 --output runtime-evidence/idle-control/idle-switch-16-call-cycle-occupancy.json
```

## Verified Stage293 original-SD NeXium results — 2026-10-18

The Stage293 code was committed in
[`314510a3`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/314510a3143e84bd315ae64a08cd840df877c84c).
A syntax-only guard fix is recorded in
[`8f79ec0e`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/8f79ec0e018d06c3f8376d150d38de5f2bf7b0c9).

**All CI checks passed on the fixed code commit**, including:

- [Current-NRO independent guest-original-SD NeXium run 39118625048](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39118625048)
- [Host C/Python and Switch toolchain 39118625040](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39118625040)
- [Host SPU 39118625073](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39118625073)
- [Native PCM 39118625054](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39118625054)

The original same-NRO SD-source audout run produced the following
**consecutive 16-attempt cycle** counts:

| Guest software audout group count | Music switching | Idle control |
| --- | ---: | ---: |
| Total cycles (including last partial cycle) | 121 | 139 |
| Cycles containing ≥1 call duration ≥40ms | **27** | **30** |
| Cycles with ≥2 slow calls | 5 | 5 |
| Slow-containing cycles with no slow call at sampled phase0 | **25** | **28** |
| Individual slow calls at unqueried attempt phases 1–15 | **30** | **34** |

Thus, phase0's **slow-call duration** falls below 40ms in most
cycles that nevertheless have at least one slow call at another
attempt index (25/27 and 28/30, respectively). This describes
**call-index selection only**. It does NOT tell us that phase0's
observed **queue count** was misleading about any other phase:
**queue counts were never measured** on phases 1–15.

Both sessions used a single verified NRO. The session with scene
changes was recorded before idle, and guest-emulator host conditions
were not randomized. These group counts are correlated views of the
same source calls, not independent trials or evidence of real audio
starvation. No real Switch speaker, hardware DAC, scheduler callback,
or audible game soundtrack was tested.
