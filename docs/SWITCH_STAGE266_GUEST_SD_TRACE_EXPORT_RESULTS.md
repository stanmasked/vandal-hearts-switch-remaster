# Stage 266 — SD-backed guest audio scene event export

**Result: NATIVE_EXPORT_TESTS_PASSED; EMULATOR_GUEST_SD_NOT_VERIFIED.**  
**Physical Switch: `HARDWARE NOT TESTED`.**

## Implementation

This stage adds `source/vh_audio_scene_trace_export.[ch]` to the native libnx tactical-music NRO and makes `source/main.c` invoke the exporter **only after joining the audio worker**. It does not allocate memory, block on SD writes, or format CSV in a gameplay or audio-render callback.

The source writes a new numbered `sdmc:/switch/vandal-hearts-remake/audio-scene-trace-0000.csv` (up to 64 slots), with the exact columns:

`index,event,serial,scene,monotonic_ns,dropped_total`

The bounded guest event witness records `INPUT`, `POST`, `ACCEPT`, `SUBMIT_CALL`, `RELEASE_RETURN` and `SUBMIT_ERROR`. Every row repeats the final dropped-event count; a nonzero value means the internal witness is incomplete.

The exporter exclusively creates a per-slot `.tmp` file, writes the canonical CSV, flushes/closes, reopens and **checks every byte plus exact EOF**, verifies that the numbered target remains absent and renames the verified staging file. It does not intentionally open, truncate or remove existing numbered CSVs. A stale `.tmp` causes a subsequent free slot to be selected. This is **not** an atomic no-replace guarantee on concurrent FAT writers, nor proof of SD durability after sudden loss of power; the game assumes exclusive ownership of the directory while exporting. A failed readback never becomes a committed CSV.

## Reproducible tests and compiled candidate

- Native integrated build: [GitHub Actions 39050183383](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39050183383), build commit `02f5f51e4225b60659ec8409dcc0ab0dc5d62d39`, **SUCCESS**.
- Native artifact ID `12106909905`, archived as `vandal-hearts-tactical-with-native-music`.
- Archive SHA-256 `125c7398299c2b10514ef76d373ea0ec0c0fd0f54263c667c3b54dfa3af24a9a`, independently checked against downloaded ZIP. The ZIP passes CRC for both members.
- Exact NRO: 270,392 bytes, SHA-256 `a5836de758498f29dacb0f2f9ffba6acf74ffb7b08f8f7e0bfd3ba91f298ca27`. The SHA receipt inside the ZIP agrees.
- `tests/test_vh_audio_scene_trace_export.c`: normal publication, multiple numbered files, no overwriting a prior result, rejection of corrupted readback, injected flush/rename errors, deliberate competing target, stale temporary file handling and saturated 64-event trace with nonzero dropped count. All tests passed in the native integrated build's primary CI log.
- `tools/audit_switch_guest_scene_trace.py --sd-csv ...` parses **strict canonical ASCII CSV**, verifies all count columns, event order, serial/scene matching and timestamp ordering, and explicitly distinguishes internal buffer-return confirmation from DAC playback.
- `tools/audit_nexium_guest_sd_handoff.py` verifies the isolated `NEXIUM_DATA_ROOT` path and requires exactly four complete `FIELD→FOCUS→FIELD→FOCUS→FIELD` transitions; no log-source fallback can silently satisfy the gate.
- Earlier synthetic auditor tests initially used a nonexistent event-row index and caused a failed CI build (`39050786240`). Fixed tests were rerun in [CI 39050977528](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39050977528), where the entire build/test job **succeeded**.

## Actual NeXium experiment — strong negative boundary

Emulator run: [GitHub Actions 39050977528](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39050977528), workflow source commit `d3cdd5289041034f5dc841bec83e465222148137`. It downloads and hash-verifies the **pinned integrated NRO** from `39050183383`, rather than substituting an arbitrary newly compiled executable.

- Build/test job: **SUCCESS**.
- NeXium graphics/input tests: **SUCCESS**.
- Independent PulseAudio PCM capture: **NONZERO_MONITOR_PCM**, duration **45.098 s**.
- Repeated musical scene capture: **REPEATED_SCENE_CORRELATED_PCM_CHANGE**, **42.723 s** of stereo PCM, relative FIELD/FOCUS zero-crossing ratio **1.7346**.
- Screen image verification: all four scene label changes have **47 altered pixels** in the expected region.
- New strict guest SD gate: **FAILED**, report `GUEST_SD_TRACE_NOT_VERIFIED`; no `audio-scene-trace-NNNN.csv` or `.tmp` was present under the isolated `NEXIUM_DATA_ROOT` mapping. The guest stderr bridge also produced a zero-byte log and remained `GUEST_TRACE_NOT_OBSERVED`.
- Original evidence artifact `12107249423` (`nexium-runtime-evidence`) was downloaded; all **37 archive entries passed CRC**. The precise failed verdict states: `expected one newly committed guest scene CSV, found 0 (incomplete temp files: 0)`.

**Do not report this run as green.** Failure is deliberately exposed rather than reporting unverified internal timing as `PASS`. NeXium audio, graphics and control results stand separately, but the new SD evidence is missing. Actual `INPUT→POST→ACCEPT→SUBMIT_CALL→RELEASE_RETURN` time intervals are **not measured**.

### Likely compatibility blocker — not yet a proved root cause

The public NeXium source maps guest `sdmc:/` through `NEXIUM_DATA_ROOT/sdmc` in `nexium-common/src/paths.rs` and `nexium-kernel/src/fs_host.rs`. However, the current public `nexium-kernel/src/services/fs.rs` `OpenSdCard` command and `services/fsp.rs` have placeholder implementations, and source searches did not find use sites for the `fs_host::get_fs_host` helper beyond its definition. This suggests that guest-side libnx filesystem calls may not yet reach the host filesystem. The exact nightly executable and absence of a published file are **not enough to prove precisely where guest export failed**; do not attribute a specific return code without guest evidence.

## Next independent path

1. On a Switch capable of running user-built homebrew, run the verified NRO, perform two A/B scene-selection cycles, exit via Plus, then inspect `sdmc:/switch/vandal-hearts-remake/audio-scene-trace-0000.csv`. Keep all captured original bytes. This hardware action is **not yet performed**.
2. Validate the user-provided CSV using `python3 tools/audit_switch_guest_scene_trace.py --sd-csv PATH`. A complete serial witnesses *internal* event timings only; physical acoustic onset and hardware buffer underruns remain independently unverified.
3. For an emulator-only continuation that does not require guest FS or stderr, implement a small read-only **framebuffer-encoded trace receipt** after audio thread join. Verify exact pixels and timestamps from NeXium screenshots, not OCR or inferred host PCM offsets; mark this alternative as a different evidence transport.
4. Do not add copyrighted retail soundbanks, console keys, firmware or game images to the repository.

**Hardware status remains exactly `HARDWARE NOT TESTED`.**
