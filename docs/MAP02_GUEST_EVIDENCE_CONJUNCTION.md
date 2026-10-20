# MAP02: conjoined optical / virtual PCM / guest raster observations

This is **read-only**, opt-in NeXium research. It extends [Draft PR #242](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/242) at verified parent head `720eeb489b42460be74ea5c74033ba5b2c4db0e4`. It changes **no Nintendo Switch C code**, audio renderer, PCM buffer ownership, synthetic music, graphics, NRO build recipe or original game assets. All parents and `main` stay frozen. **DO NOT MERGE**.

## Reason for a separate classifier

An actual guest optical `VHPRE001` is drawn only **after** `vh_switch_game_audio_stop()` has waited in `threadWaitForExit(&audio_thread)`. If the post-join packet is missing, neither a still frame nor a zero virtual sink identifies where the guest stopped progressing. A capture may show:

- No valid optical receipt and a zero PCM monitor. This proves **only** the two observed failures; it cannot identify whether guest audio never started, the service stopped returning or the emulator backend stalled.
- No valid optical receipt but a nonzero monitor. **No eight-page guest identity** may be inferred from these samples.
- A valid eight-page optical receipt plus a nonzero monitor. Fingerprint **identity** is established only if the independent page matcher reports eight unique CRC32+FNV1a64 page matches; even then continuous, gapless audio is separately unproven.
- A valid optical packet with a zero monitor. This is a contradictory/incomplete observation requiring investigation, not a pass.

Historical genuine NeXium [run #39386868354](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39386868354) contains:
- 21ms repeat 1 and 2: no valid optical packet, entire captured PCM16 sink zero, normal game image before the attempted exit and no further ROI changes in the additional five-second screenshot.
- 22ms repeat 1 and 2: real eight-page CRC-valid optical packet, all eight original guest pages individually matched in nonzero 48k stereo PCM output.
- The raster comparator itself proves only **changes of pixels**. A static late screenshot is neither proof of a blocked `audoutPlayBuffer` nor even proof that the correct input triggered exit.

## Added evidence conjunction

`tools/classify_map02_guest_evidence.py` reads up to five **already independently generated** evidence JSON reports from the same NeXium job:

| File | Independent observation |
| --- | --- |
| `presubmit-guest.json` | Opt-in guest eight-page optical `VHPRE001` proof |
| `presubmit-monitor-health.json` | Independent raw PCM16 stereo zero/nonzero count |
| `presubmit-guest-raster-sequence.json` | Before/final/late gameplay ROI changes and SHA-256 |
| `presubmit-sink-parity.json` | Exact independent page matches inside virtual monitor |
| `pulse-sink-input-observed.json` | Unique observed 48k stereo PulseAudio client |

It emits `presubmit-guest-evidence-conjunction.json` with one of these conservative verdicts:
- `OPTICAL_MISSING_ZERO_VIRTUAL_SINK`
- `OPTICAL_MISSING_NONZERO_VIRTUAL_SINK`
- `EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK`
- `OPTICAL_VALID_SINK_PAGE_IDENTITY_UNVERIFIED`
- `OPTICAL_RECEIPT_BUT_ZERO_MONITOR_CONTRADICTION`
- `INSUFFICIENT_VIRTUAL_MONITOR_EVIDENCE`

The report preserves the observed changed-pixel counts, any unique host 48k stereo client identification and whether the eight page matches were individually found. It explicitly outputs `audout_playbuffer_stall_proven=false`, `guest_join_deadlock_proven=false`, physical DAC/speaker proof false and original music fidelity proof false.

The additional workflow step uses `if: always()` **after** the original strict optical decoder and page matcher; it **does not change their pass/fail status**. It archives machine-readable findings even after a guest test failure. Generated-only `tests/test_classify_map02_guest_evidence.py` covers known good and all-zero failures, contradiction, malformed guest payloads, missing monitor, missing receipt with nonzero output, and raster false liveness (eight cases).

## Acceptance

Validate GCC/Clang generated-only tests and an actual same-run NeXium opt-in NRO execution before treating a new JSON artifact as real. A passing CI badge is not a claim of gapless PCM, physical DAC timing, Nintendo Switch speaker playback or fidelity to the original PS1 soundtrack. Keep all previously successful Draft parents immutable; no merge.
