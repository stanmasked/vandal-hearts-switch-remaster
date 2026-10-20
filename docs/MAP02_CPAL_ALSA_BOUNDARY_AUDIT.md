# MAP02 Stage263 — independently re-audit CPAL/ALSA/Pulse buffer boundary

**DRAFT / DO NOT MERGE.** Historical host-side audit only. Child of [Draft #248](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/248) at `64a3e81b53d375fae3cfc93b4384ec8e18e68703`. Does not edit gameplay, audio transport, Makefiles, licensed PS1 ROM/music, parent integration, or `main`.

## Why this is not an SDL audio-fix experiment

The NeXium source documents **CPAL** as the audio output layer; SDL3 is used for controller support. In `nexium-runner/src/audio.rs`, Linux CPAL requests its default buffer size (`DESIRED_BUFFER_FRAMES=None` outside Android), builds the 48-kHz host stream and maintains a separate ring and mixer with consumed-frame accounting. CPAL on Linux uses ALSA by default. Our host CI routes ALSA's default PCM to a PulseAudio null sink.

NeXium public code (reviewed 2026-10-20):
- https://git.mythrax-rs.org/nexium-emu/nexium/src/branch/main/nexium-runner/src/audio.rs
- https://git.mythrax-rs.org/nexium-emu/nexium/src/branch/main/README.md

These source facts **do not prove** the exact host runtime version, which must be resolved using the pinned nightly build hash for a true causal backend audit.

## Input evidence and fail-closed integrity

The workflow downloads **exactly seven** archives from original run [39398087760](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39398087760): one opt-in research NRO plus `21/22 ms × three repetitions` of guest evidence. The workflow never starts a guest, replays original PCM, or changes historical NRO bytes.

`tools/audit_map02_cpal_alsa_boundary.py` rejects a report unless:

1. The original NRO's `NRO0` header, actual SHA-256 and saved manifest agree.
2. All six distinct trial IDs exist, with one immutable original source SHA, run ID, NRO digest and invocation attempt.
3. Each original *real PNG* decodes under the existing prejoin optical CRC-8 **and** XOR checks, and matches its stored stage JSON exactly.
4. Every raw 48-kHz stereo PCM recording independently hashes and recounts to its monitor JSON; no all-zero vs nonzero assertion is trusted without raw bytes.
5. Each report uniquely identifies the stereo 48-kHz NeXium ALSA input both during and after guest input, with valid **observed** (not requested) buffer delays.
6. Re-running the evidence classifier against independent JSON inputs reproduces the stored guest classification; it may be a valid failed 21-ms trial, not a pass disguised as success.

Synthetic ROM-free tests intentionally forge a source SHA, PCM bytes, stage JSON, missing trial, ambiguous Pulse input and a false successful optical classification. Failures are required.

## Six previously observed samples (pending independent archived rerun of audit)

| Requested host hint | Repeat | Stage at prejoin snapshot | audout entries / returns | Virtual PCM16 nonzero | Pulse buffer µs (during) |
|---|---:|---|---:|---:|---:|
| 21 ms | 1 | ENTERED_PLAYBUFFER | 1 / 0 | 0 | 10,666 |
| 21 ms | 2 | ENTERED_PLAYBUFFER | 1 / 0 | 0 | 10,666 |
| 21 ms | 3 | ENTERED_PLAYBUFFER | 1 / 0 | 0 | 10,666 |
| 22 ms | 1 | CLEANUP_COMPLETED | 464 / 464 | 515,162 | 16,999 |
| 22 ms | 2 | CLEANUP_COMPLETED | 453 / 453 | 503,681 | 14,499 |
| 22 ms | 3 | CLEANUP_COMPLETED | 499 / 499 | 555,446 | 19,479 |

The audit reports exact observed values, **not** a threshold attributed to 21/22 ms. The pulse-buffer figure is a sampled server-reported delay, *not* a CPAL callback quantum, guest buffer size, or evidence of causality. While the guest is apparently in the first real `audoutPlayBuffer` call during the 21-ms single snapshot, the service might later return. The deliberate 1+8-second optical witness also altered guest shutdown timing.

## Exact host-build caveat discovered during Stage264

The original guest workflow labels its download step **"Download pinned NeXium nightly asset"**, but the actual code retrieves the release **by mutable tag** `nightly` via GitHub API and downloads `nexium-linux-x86_64.tar.gz` separately in every job. It does **not** save the downloaded archive's SHA-256, executable SHA-256, or immutable upstream NeXium commit ID alongside each trial.

See [the frozen workflow at original source SHA](https://github.com/stanmasked/vandal-hearts-switch-remaster/blob/64a3e81b53d375fae3cfc93b4384ec8e18e68703/.github/workflows/map02-audout-presubmit.yml#L212-L232).

**Consequences:** this independent archive audit verifies the exact same guest NRO across all six runs, but cannot truthfully certify the same host NeXium executable (even though all six came from one GitHub workflow run). `PULSE_LATENCY_MSEC` is also only a request, never proof the target honored it. The audit therefore includes explicit `same_nexium_host_binary_all_six_verified=false` and `nexium_host_binary_sha256_available_in_original_artifacts=false` fields; they are not inferred from the NRO digest.

Any new causal A/B experiment must acquire one pinned NeXium executable **once**, save its SHA-256 and immutable upstream revision, distribute the identical binary to all six guest jobs, and verify its digest inside each job. Preserve the original failing cases separately: a change to emulator build identity is a new experimental condition, not a correction retroactively applied to prior evidence.

## Next experimental gate

To claim a root cause, perform a **separate** A/B run measuring CPAL callback activity and host ALSA parameters around the first real guest submission while holding the NRO and game-side PCM constant. Compare requested hint, actual buffer period/size, callback execution and real guest enter/return timestamps. Reproduce at least three times per setting and preserve all failure evidence. Changes to NeXium or host instrumentation must be explicitly reported as a changed workload. An eventual physical Switch test is still required.

**No automatic merge.** Stage263 audits the original data only and cannot repair or prove audible output on Nintendo hardware.
