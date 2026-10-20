# MAP02 Stage285 — determine whether CPAL goes quiet before guest input

**Research-only Draft / DO NOT MERGE.** Child of [Draft PR #321](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/321), frozen at `3786510115a4d0be76e7e1fc2bc004178839f23d`. No game program, public emulator source, compiled NeXium ELF, generated-only research NRO, or original sound data changes.

## What the independently confirmed real experiments establish

[Stage284 offline re-audit #39481359555](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39481359555) passed **16 synthetic falsification tests**, then re-decoded all **six original guest PNGs**, time-stamped CPAL and kernel AudioOut counters, and raw 48k/stereo virtual PCM audio from [Stage283 six real jobs #39479885398](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39479885398). Three requested 21ms runs had one guest `audoutPlayBuffer` call not yet returned at prejoin, no new host CPAL callback or kernel AudioOut appends **after first game input**, and zero nonzero virtual PCM. Three requested 22ms runs had 8/8 guest CRC optical completion, host callback and kernel AudioOut progress, and 500k+ nonzero PCM16 samples.

**Still not known:** whether the 21ms CPAL stream went quiet *before* the first game input or was stopped *by* some post-input event. The earlier outcome CSV is sampled approximately every 200ms and validates the guest's first input timestamp, but prior comparisons did not quantify the first-to-last CPAL callback relative to that timestamp.

## Precise Stage285 measurement, using the unchanged real archives

The new strictly offline `tools/audit_map02_cpal_preinput_onset.py` requires the **same six immutable host/NRO archive identities** and calls the already verified full optical PNG, raw PCM and CPAL cross-check for **each original trial** before reporting any new timing conclusion.

For each actual host CPAL timeline:

- Read all cumulative callback-enter/return samples, compare their timestamps to the independently recorded actual guest first-input and final-observation monotonic markers.
- The *first* reporter sample may already contain a callback. In that case its callback time is **left-censored**: only an upper bound at the sample timestamp is justified. If a later reporter sample shows an increased callback-entry counter, the callback occurred somewhere in that **previous-sample-to-current-sample interval**, not at an invented instant.
- Report the last callback-increase **upper bound before input**, then a conservative lower bound in milliseconds for how long the counter was unchanged **prior** to the first game input. Classify `CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT` only if that verified lower bound is at least 1000ms and no callbacks advance after input.
- Use the real host console log solely to count existing `cpal stream error` and `Audio output disabled:` messages and hash the log. **Absence of logged errors is not proof the backend had no errors.** No licensed raw audio, original soundtrack or game RAM is inspected.
- Report every one of the six actual cases individually, retaining surprising/mixed timing as observed. An explicit `UNVERIFIED` result is produced for invalid source identities, malformed time series, missing logs or incomplete capture, without manufacturing a timing conclusion.

The new GitHub Actions workflow downloads the six *already captured* artifacts from immutable run #39479885398 and executes **15 synthetic falsification tests** followed by this real independent replay, not six new expensive emulator sessions.

## Interpretation

If the CPAL callback was provably quiet **at least a second before the first game input** in every 21ms run, this moves the observed onset of the host-side problem earlier than guest command `audoutPlayBuffer`. That would make a host-side Pulse/ALSA/CPAL startup or callback-scheduling hypothesis more plausible, but **does not by itself establish a root cause, rule out all earlier guest interactions, or prove a deadlock**. A 22ms continued callback result remains only a requested Pulse latency hint contrast — not a measured CPAL period.

Any actual repair requires a separate controlled source-code intervention and new repeated 21/22ms verification. Physical Nintendo Switch DAC output and the original PS1 soundtrack have not been tested. Keep this and all parent PRs in Draft.
