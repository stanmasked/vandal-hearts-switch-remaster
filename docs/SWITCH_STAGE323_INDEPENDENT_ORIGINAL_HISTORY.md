# Vandal Hearts Remake — Stage323: independent original 16-call audout history

## What is known from original guest evidence

Stage320 authentic NeXium [#39154247222](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39154247222) and independent Stage321 [#39156088373](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39156088373) both succeeded. The final successful normal `audoutPlayBuffer` service call in that guest software capture lasted 28,391,093 ns and overlapped the main-thread stop request for 27,834,739 ns. That **does not** prove it is unusually slow during ordinary playback or that any sound is audible at the speakers.

Stage322 introduced a fixed-size 16-entry original guest source history using the already existing software call begin/end clocks. Host SPU, C/Python, toolchain, native `audout` and integrated NRO CI passed on the corrected Stage322 branch. The source run is the **exact** NeXium workflow [#39159226320](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159226320), whose complete runtime artifact must be successful before independent conclusions.

## Stage323 source replay

`tools/replay_nexium_original_playbuffer_history_archive.py` runs on a **different GitHub Actions runner**, after verifying that the exact original Stage322 capture is completed successfully. It demands:

- The original guest-created `audio-playbuffer-history-000.csv`, with up to 16 consecutive actual normal audout service attempts (successful and failed), original software begin/end timestamps and sequence numbers.
- The original guest-created Stage320 `audio-last-playbuffer-000.csv`, Stage317 `audio-exit-worker-stop-000.csv`, Stage313 `audio-exit-output-000.csv` and Stage307 `audio-exit-timeline-000.csv`.
- The original CRC-protected optical framebuffer `scene-optical-trace.png`.
- The associated capture-time source receipts for Stages 307, 308, 310, 313, 314, 317, 320, 322.

It first independently replays the complete original Stage321 source chain, then decodes the Stage322 history CSV, recomputes its SHA-256 and regenerates the **exact** Stage322 receipt. Both original CSV and derived capture receipt must agree; the analysis never reconstructs original data from JSON.

Only if the authentic 16-call window contains the final successful call **and** earlier successful calls does the report include the earlier lower-median duration and the final-minus-median difference. Otherwise it explicitly reports that the prior baseline is absent.

The independently replayed report also counts strictly **shorter**, **equal**, and **longer** preceding successful calls than the final call, excluding failed service attempts and the final call itself. It reports the ascending rank of the final call inside **this one retained window**, with ties assigned the lowest rank. Counts must sum exactly to the original number of preceding successful calls. This ranking is descriptive and is not a statistical percentile or inference about all game sessions.

For the original Stage322 guest capture [#39159226320](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159226320), the independently verified Stage323 source replay [#39159251998](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159251998) reproduced the final normal call duration of **18,385,781 ns**, versus a lower median of **31,775,052 ns** among **15** earlier successful calls. The final call was **13,389,271 ns shorter** than that median. The separate [Stage323 rank verification #39160645756](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39160645756) succeeded with **16 tests** and reproduced **3 shorter, 0 tied, 12 longer** prior successful calls. Thus the final successful call ranks **4th shortest of 16** in this one genuine source window. This supports a within-capture comparison, not a universal stopping-performance claim.

Independent output:

`independent-stage323-evidence/original-playbuffer-history-stage323.json`

The new read-only workflow publishes only its newly computed JSON result, not raw PCM, original PlayStation music, firmware or console keys.

## Tests

Sixteen synthetic adversarial cases cover original-byte mutations, fake SHA receipts, mismatched final successful call, missing/duplicate/relocated/symlinked guest sources, invalid capture identifiers and unsupported physical-audio conclusions. Tests run both in Host SPU and the new standalone Stage323 runner with isolated Pillow.

## Scope

This stage **only replays and compares diagnostic original source evidence**. It changes no SPU code, audio buffer content, `audout` scheduling, Nintendo Switch gameplay behavior or musical assets. Time intervals are guest monotonic *software call brackets*, not DAC timestamps, speaker sound, host PulseAudio sample-clock synchronization, or proof of audible dropout caused by Plus.
