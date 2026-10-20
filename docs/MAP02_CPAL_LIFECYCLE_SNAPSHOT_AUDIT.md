# MAP02 Stage288 — strictly parse new CPAL lifecycle/error snapshots

**Research-only Draft / DO NOT MERGE.** Child of [Stage287 Draft PR #349](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/349), frozen source `0301b4def224a76905fdb2af5007d1ea73e73f92`. Only four new offline audit files; no emulator binary, game source, original ROM, artwork or soundtrack is changed.

## Why the new format requires a new auditor

The six verified old 21/22-ms trials used Stage274 `T` rows with eight numeric columns after the tag and no CPAL lifecycle state. Stage286 appends a new **lifecycle state** and **CPAL error callback count** to the existing counters and uses `L` rows; the two schemas must not be conflated. The new reporter produces 11 comma-delimited fields total:

`L,monotonic_ns,lifecycle_state,error_callbacks,cpal_entries,cpal_returns,cpal_output_frames,sink_consumed_frames,audioout_appends,audioout_accepted_frames,audioout_releases`

State codes: **1** build attempted; **2** built; **3** `stream.play()` returned successfully; **4** build failed; **5** play failed. **0** means no lifecycle state sampled. A single initial sampled 3 may be valid because creation and playback happened between earlier samples; it does **not** mean the stream is necessarily still active.

## Fail-closed validation

`tools/audit_map02_cpal_lifecycle_snapshots.py` accepts only genuine exact-format 11-field `L` rows with unsigned 64-bit values, strictly increasing host monotonic time, 8–240 samples, at least one second of coverage and no heartbeat gap above 2 seconds. It rejects decreasing atomic counters, CPAL returns greater than entries, impossible observed lifecycle transitions, and malformed rows.

An interpretable post-input report requires both actual monotonic guest input and final-observation markers, with at least 500ms of pre-input coverage and one sample from the last second before the final guest snapshot. Missing timing coverage yields **UNVERIFIED**, never a false zero.

The analyzer distinguishes **observed CPAL errors in the guest window**, failure state from stream build/play, callback entries still unmatched at the sampled observation, confirmed entries/returns and a prior successful `stream.play()` without observed new callback entries. Crucially:

- State 3 means **a prior `stream.play()` call succeeded**, not that the Pulse/ALSA stream is running at the precise time of the final snapshot.
- The CPAL error callback field is a **counter**, not an event log with a timestamp for every error.
- No pause/drop/wakeup instrumentation is included; no exact causal sequence or permanent guest AudioOut deadlock can be deduced.
- The parser by itself does not independently authenticate the NeXium ELF SHA-256 or guest NRO SHA-256; those must be checked by the eventual real experiment.

The new CI executes **18 ROM-free synthetic falsification scenarios**, followed by the actual parser CLI on generated samples. It uploads only a generated report. Passing it proves correctness only for its declared synthetic cases, **not** actual CPAL runtime activity, a 21-ms fix, the original PS1 soundtrack or sound on a physical Nintendo Switch.

## Next gate

First validate the new Stage287 compiled ELF and exact SHA, then launch a new guest control with opt-in `VH_MAP02_CPAL_TRACE_PATH`, inspect raw L rows and compare to real guest optical/PCM data. New instrumentation may perturb scheduling and must be independently re-tested at 21 and 22 ms. Preserve the original six archived Stage283/284 guest trials unchanged.

**Do not merge to main.**
