# MAP02 Stage284 — audit six completed Stage283 guest archives without rerunning emulator

**Research-only Draft / DO NOT MERGE.** Child of [Stage283 Draft PR #319](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/319), exact frozen parent SHA `5653a70f1c8ea1fda8f08c962abdc9a143c62c1e`. No production Vandal Hearts Remake files, NeXium source/binary, ROM or original licensed audio are changed.

## What has already happened

The [six-job Stage283 run #39479885398](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39479885398) completed **all six separately hosted opt-in NRO guest jobs successfully** (three requested 21ms and three requested 22ms). Each job downloaded and hash-checked the identical source-pinned NeXium ELF and identical generated research NRO, used Rustarmic and virtual PulseAudio, and saved its actual PNG optical screens, cumulative CPAL/AudioOut timeline, 48-kHz/stereo PCM and provenance metadata. The original run's separate archive auditor failed closed at its **matrix identity check**, with `Matrix identity/runner or original executable mismatch`. Thus **the six captures exist but their cross-run repeatability is NOT yet independently verified**. No broad scientific conclusion is assigned to that failed archive audit.

## New offline-only audit

This child changes the existing fail-closed auditor only to separate the four formerly combined identity conditions (compiled host SHA, generated NRO SHA, Linux runner OS and job label) into individual error messages. Checks are not relaxed. Its separate `map02-cpal-six-archived-audit.yml` workflow downloads all six *unchanged archived job outputs from exact run ID 39479885398*, logs their actual manifest metadata, runs sixteen ROM-free adversarial tests, then independently:

- Validates the exact source-pinned executable SHA and NRO SHA, original source/run/attempt, six distinct labels and exact recorded hint.
- Re-decodes original guest prejoin and final PNG pixels using opt-in optical checksums.
- Re-parses real Rust CPAL and kernel AudioOut cumulative counters with guest input/final monotonic timestamps.
- Rehashes actual raw virtual PCM files and recounts their nonzero PCM16 samples.
- Reports both stable 21/22 behavior **and** unexpectedly mixed outcomes without hiding them, or reports `UNVERIFIED` if original data or identities cannot be established.

No guest processes are restarted; this is a small diagnostic audit on real existing archives, minimizing resource use. A previous failed auditor output is preserved; the new audit must establish its own green CI and source manifest provenance before a repeatability claim is made.

**Limits:** a repeatable requested Pulse latency hint does not identify the measured CPAL device callback period, prove an infinite `audoutPlayBuffer` deadlock, demonstrate a fix, validate copyrighted original music, or establish physical Nintendo Switch DAC output. Keep this and ancestor PRs Draft, without merging.
