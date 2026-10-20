# Stage265 — one NeXium host executable, six MAP02 guest trials

**DRAFT / DO NOT MERGE.** Research-only child of Stage263 [Draft #258](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/258) at `896ba7746b73665dd8e8616a614860eddb00e9e0`. Parent [Draft #248](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/248) retains frozen source at `64a3e81b53d375fae3cfc93b4384ec8e18e68703`. No ROM, licensed music, original game audio, production Switch audio transport, or base integration branch changed.

## Changed experimental variable

The former workflow downloaded the mutable `nightly` NeXium release independently from each guest. Stage265 creates a **single** `nexiom-host` job which resolves that release once, records the GitHub release/asset IDs, downloads one Linux x86-64 archive, validates its tar contents and hashes:

- Full downloaded host archive: SHA-256
- Extracted `nexium`/`nexium-gui` executable: SHA-256
- Same-run provenance: GitHub run ID, attempt, exact PR source SHA, event SHA, release/asset ID

A single GitHub Actions `map02-nexium-once-binary` artifact is distributed to every guest job. All six jobs verify the archive and extracted executable hashes **before starting** NeXium. A failed match prevents the guest from running.

The guest workload itself is copied from the previous fixed 21/22-ms × three-repeat research workflow. It keeps the same opt-in NRO, 48-kHz stereo null sink, ALSA→PulseAudio routing, optional `PULSE_LATENCY_MSEC` hint **only on the host NeXium process**, original gameplay inputs, eight-page PCM witness, CRC8 prejoin stage, and strict postjoin CRC/virtual PCM checks. Requested milliseconds are never treated as observed CPAL callback periods.

### Jobs

1. `nexiom-host`: acquire, hash and artifact one host binary.
2. `host-witness`: unchanged generated-only GCC/Clang PCM and retry sanitizer checks.
3. `research-nro`: independently compile unchanged opt-in native Switch NRO and save its digest.
4. `nexiom-presubmit`: six guest trials. Each additionally records `nexium-host-build.json` in its always-uploaded evidence directory; expected 21-ms failures remain **failures**.
5. `compare-all-six-exact-host-binaries`: even if guest checks fail, independently validates the original NRO SHA and raw PCM, actual optical PNG CRC8/XOR snapshots, all six original guest identities and the shared host archive/executable SHA; emits an explicit machine-readable verification status.

The verifier also rejects host manifests from another run or source commit, forged trial hashes, missing 21-ms failure evidence, mismatching asset provenance, and assertions that an unverified upstream commit was authenticated.

The Stage266 hardening adds a **cross-attempt check**: the host, research NRO and six guest manifests must all carry the identical `GITHUB_RUN_ATTEMPT`. Merely matching `GITHUB_RUN_ID` or the NRO digest is insufficient when GitHub retries individual jobs. Three new generated tests cover matching provenance, a stale guest archive and a stale NRO archive; an invalid or missing manifest fails closed.

## Scientific limits

- One downloaded archive distributed to six jobs **proves the same host bytes within that run**, provided all six verifications and uploaded proofs pass. It does not pin the moving GitHub release to a fixed revision *across separate workflow runs*.
- The source commit used to build the published NeXium release is **not** authenticated by the archive SHA alone. The manifest explicitly marks `upstream_source_commit_verified=false` and `cross_run_release_immutability_proven=false`.
- On Linux NeXium, public source identifies a CPAL audio layer with ALSA transport. The actual distribution package and dynamically loaded backend still require observation on the test host; the new common binary does not itself show CPAL callback duration or driver initialization.
- PulseAudio `Buffer Latency` is sampled after guest inputs and may change. It is **not** the SDL or CPAL callback quantum, nor necessarily the buffer size of the guest's first `audoutPlayBuffer`.
- All six runs use the deliberately prolonged 1+8-second prejoin panel. Do **not** pool their timing with earlier non-instrumented tests as identical workloads.
- The 21-ms trials can legitimately fail final audio assertions; converting them to green would hide the phenomenon being examined. The host-identity auditor is a separate job with a separate verdict.
- A snapshot of zero returns does not prove permanent deadlock; monitoring a virtual PulseAudio sink never proves sound at the Nintendo Switch DAC or speakers.

## Gate to a real root cause

Only after the *same-run exact host binary* control succeeds should a separate host instrumented A/B experiment log the **CPAL stream configuration, actual callback period, consumed samples, ALSA period/buffer values, and time-aligned guest entry/return points** before/after the first `audoutPlayBuffer`. Instrumentation must be disclosed because it can change thread timing. At least three runs per condition and an independent Nintendo hardware test will be required before any production mitigation is considered.

**No auto-merge; no game code change.**
