# MAP02 — distinguish guest AudioOut append from host PCM silence

**Research-only Draft**, built from all-green [PR #231](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/231)
commit `33f4ce16cde160d30a154cca453a7545ed106b26`.
No guest C source, game audio/SEQ/SPU/resampler code, libnx output,
original music assets or production runtime configuration changed.

## Verified background
The same opt-in 48-kHz guest NRO was tested at different *host-only*
PulseAudio client hints:
- Three `PULSE_LATENCY_MSEC=20` trials (one earlier A/B plus two
  repetitions): **entire 48-kHz virtual sink raw PCM was all-zero**,
  no final `VHPRE001` screenshot; guest showed normal MAP02 grid.
- Repeated default, 24, 32, 40 and 80 ms host trials: valid guest
  optical receipt with eight unchanged PCM pages, and eight unique
  complete byte-exact CRC32+FNV1a64 page matches in monitor recording.
- In all successful captures, seven inter-page intervals are **only**
  PCM16 zeros and starts are 512-frame-quantized. This indicates host
  output gaps but does not attribute them to the guest or NeXium.

Even **a successful 32-ms** trial had a transient observed PulseAudio
`Buffer Latency=10666us` (512 frames) early but recovered to 24000us.
An instantaneous host queue measurement is not its maximum capacity.

## Read-only NeXium source diagnostics

Inspection of public `nexium-emu/nexium` tree at commit
`089562567a0a8760dfdd8420e1f57c35159a9219` established:
- `nexium-kernel/src/services/audio_out/handlers.rs` already gates
  the first 128 **AudioOut append IPC** log lines under the environment
  variable `NEXIUM_AUDIO_TRACE`. Lines contain `frames`,
  `pcm_nonzero`, `pcm_peak`, `sink_present`, `started`,
  `pushed_frames`, and `queued`, alongside guest pointers.
- `nexium-gui/src/main.rs` accepts `NEXIUM_LOG_LEVEL=info`.
- `nexium-common/src/paths.rs` respects `NEXIUM_DATA_ROOT`, and
  `nexium-common/src/file_logger.rs` writes full traces to
  `NEXIUM_DATA_ROOT/logs/nexium-*.log`.
- The `AudioOutMixer` in `nexium-runner/src/audio.rs` consumes the
  submitted guest frames and returns zeros when that guest stream
  has no queued sample. `audio_out/handlers.rs` separately tracks
  per-page host acceptance and guest buffer release.

These are **source code observations**, not yet results from the
downloaded nightly emulator binary; it must be verified that the
nightly includes the same trace gates. Trace of an IPC append also
does not prove physical DAC delivery, audibility, contiguous playback
or music accuracy.

## Controlled test

The independent child branch compares `default` versus `20` ms,
two repeat NeXium jobs per host hint, using **one** same-run
SHA-256/source-verified experimental NRO. The 48-kHz PulseAudio null
sink and the separate `parec` recorder remain unchanged.

Only for the emulator subprocess:
- Set `NEXIUM_LOG_LEVEL=info`, `NEXIUM_AUDIO_TRACE=1`,
  `NEXIUM_AUDIO_RATE=1`, and set an isolated
  `NEXIUM_DATA_ROOT=$RUNNER_TEMP/vh-map02-aout-trace`.
- The raw NeXium trace log stays in the runner's temporary directory
  **outside GitHub's uploaded artifacts**: it includes virtual guest
  pointer/descriptor/header addresses. Do not upload full traces.
- Python `tools/report_nexium_aout_trace.py` parses only a strict
  allowlist of scalar counters and true/false states. It writes
  `runtime-evidence/nexium-aout-append-summary.json` without guest
  pointers, headers, tags, raw PCM or user files.
- The parser requires a recognizable NeXium startup log when
  `--require-logger` is used and rejects invalid/duplicated
  append serials or impossible counts. A valid initialized logger
  with **zero** append events is an observation of zero **logged**
  appends only: if the nightly lacks this trace gate, the absence
  cannot be interpreted as a guest IPC stall.

The normal strict `VHPRE001` optical check remains mandatory in
successful host variants, and even a trace with nonzero PCM does not
override a failed guest screen or all-zero monitor recording.

**Diagnostic questions:**
1. Did AudioOut append IPC receive page frames of 557/558 with
   `pcm_nonzero>0` in each condition?
2. Was a host sink present and active when appends occurred?
3. Did NeXium accept all frames into its host mixer?
4. Were appends absent in the failed 20ms run despite successful
   host logger initialization? If so, the blockage may precede the
   kernel's append handler; if appends exist, investigate host mixing
   and callback scheduling.

Do not infer causality from a single attempt. No changes to parent
PRs, standard game audio or main. **Draft / DO NOT MERGE.**
