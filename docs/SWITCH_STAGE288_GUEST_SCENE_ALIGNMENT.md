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
