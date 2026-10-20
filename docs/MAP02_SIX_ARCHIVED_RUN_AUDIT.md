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

## Root cause of the first audit-only failure

The original six **matrix-identity.json receipts all contained the same complete 64-hex NeXium ELF SHA-256**. The first [Stage284 offline audit run #39480918142](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39480918142) confirmed the six original manifest fields and pinpointed the actual discrepancy: the independent Python auditor had inadvertently hard-coded a **46-character truncated host SHA-256 literal**. It therefore rejected legitimate full SHA-256 values. The fail-closed refusal was correct; the source test constant was wrong.

The auditor now carries the **full 64-character ELF SHA** `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`, plus an import-time requirement that both host and NRO source digests contain exactly 64 lowercase hexadecimal characters. The underlying game code, emulator binary, NRO, controller scripts, guest results and six immutable evidence archives are completely unchanged. Only a new successful independent replay of those six raw archives may establish repeatability.
