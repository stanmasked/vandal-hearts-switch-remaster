# Vandal Hearts Remake — Stage288: bound guest scene INPUT and slow audout times

Stage273 and Stage274 **already instrumented** the Nintendo Switch
guest's monotonic clock:

- Absolute audio-service `origin_ns` is the same guest clock source
  as recorded scene `INPUT` timestamps.
- `soak-audout-slow-unverified.csv` contains begin/end nanoseconds of
  every blocking `audoutPlayBuffer` invocation lasting ≥40 ms,
  with an independent original guest-SD archive verdict.
- Stage276's idle control contains zero A/B scene-changing guest INPUTs.
- Stage287 provides independently reverified, per-run 51-second
  counters and exact pooled per-second slow-call rates.

**This is not an independent Switch OS audio scheduler trace.**
The guest clock identifies ordering of software INPUT and API calls,
not buffer delivery to the DAC or host PCM timestamps. Therefore
adding an invented scheduler/event label to old data would be invalid.

## Stage288 exact archival reconciliation

`tools/analyze_nexium_steady_scene_alignment.py` requires eight
original-SD-bound source ZIP archives **and** all freshly regenerated
Stage279–287 reports in the same CI run. It performs the complete
Stage277 ZIP-archive recheck and again checks each Stage274 original
guest-SD hash/receipt witness, NRO, clock, scene INPUT CSV and exact
slow-call CSV via their original strict parsers and auditors.

For each of ten genuine scene INPUTs in each switching run, it reports
the relative guest-audio second, event serial and exact nanosecond
timestamp, all actual ≥40 ms blocking calls starting within ±500 ms
of the scene INPUT, the disjoint 40–<50 ms and ≥50 ms counts and how
many finished before, began after or overlapped the INPUT.

For a strict **same-relative-second** descriptive control, it divides
the 51 per-run audio-service seconds into:

- Ten seconds containing a guest scene INPUT in the switching mode;
- The remaining 41 seconds without one.

Idle-mode `audout` counters are compared at the **same relative guest
audio second index**. In idle mode the independent original guest
SD traces have *zero* scene-changing INPUTs. Switching/idle evidence
uses the same NRO, but because source capture order is always
switching before idle, the data remain **nonrandomized** and
confounded by time and guest/host scheduling.

Every original 51-second count is conserved when splitting those
two groups. Each timestamped call is reconciled with the precise
per-run slow-call bins of Stage287. ±500 ms observations are
**call-start-time vicinity**, not hardware underruns.

Reproduce from the same eight original archives and the fresh
verified-pairs reports:

```sh
python3 tools/analyze_nexium_steady_scene_alignment.py \
  --archive /path/to/run1.zip --archive /path/to/run2.zip \
  ... six additional original archived runs ... \
  --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
  --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
  --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
  --verified-temporal-contrasts verified-pairs/steady-state-temporal-contrasts.json \
  --verified-boundary-shifts verified-pairs/steady-state-fixed-left-boundary-shifts.json \
  --verified-boundary-pair-grid verified-pairs/steady-state-boundary-pair-grid.json \
  --verified-disjoint-bands verified-pairs/steady-state-disjoint-slow-call-bands.json \
  --verified-rate-exposure verified-pairs/steady-state-rate-exposure-decomposition.json \
  --verified-second-profile verified-pairs/steady-state-second-profile.json \
  --output verified-pairs/steady-state-guest-scene-alignment.json
```

The original transient NeXium guest SD devices no longer exist after
their historical workflow runners finish. The offline archive
check independently verifies their previously stored live-original
SD audit receipts and copies but does not reopen the original SD now.
Do not claim hardware, audible output, independent scheduler events,
host/guest PCM time synchronization, or scene-switch causality from
this stage.

## Accepted Stage288 archived-source observations (2026-10-18)

The independent [eight-pair NeXium verification workflow
39086324572](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39086324572)
completed successfully at [commit
`f45bc74e`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/f45bc74e0462c519a11eddb67a638aa8a20fc241).
It revalidated the live-original-SD-bound historical ZIP evidence,
all eight original clock/scene/slow-call CSV sets, all source run IDs,
all 51-second per-run windows, and every earlier Stage279–287
source report.

**80 actual scene INPUT events** (10 per switching session) had
**37** blocking audout calls ≥40 ms whose **call begin** time
was within ±500 ms of the INPUT (34 of duration 40–<50 ms,
3 of duration ≥50 ms).

Within the switching mode, after partitioning 408 complete
run-seconds into 80 scene-INPUT seconds and 328 other seconds:

| Relative guest-audio second category | Blocking calls 40–<50 ms /1,000 audout attempts |
| --- | ---: |
| Guest scene INPUT occurred in the second | 11.816340 |
| No guest scene INPUT occurred in the second | 13.617869 |

Thus, the verified archival software API trace does **not**
show a higher **pooled 40–<50ms rate** on the 80 scene-INPUT
seconds than on the other 328 relative run-seconds. These
categories are descriptive, unevenly located in elapsed time
and not order-randomized. They are **not** a statistical
test of whether the scene inputs affect audio.

The **±500 ms vicinity counts** and the separate
**same-second rates** are distinct definitions: a call starting
in the prior or following second can fall within 500 ms of
an INPUT, and a slow call in the same second need not start
within ±500 ms of the INPUT. Neither definition measures
physical audio playback.

The [native PCM workflow 39086324594](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39086324594)
also succeeded at this commit. Host and toolchain runs are
tracked in the corresponding commit checks. No second-by-second
guest-to-host PCM clock synchronization or operating-system
audio scheduler event timeline was captured. The next step
toward stronger attribution would be a **new same-guest-clock
scheduler-state witness recorded by the next NeXium NRO run**,
not retroactively labeling old slow-call events as scheduler stalls.
