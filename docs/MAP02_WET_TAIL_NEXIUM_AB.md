# MAP02 WET_TAIL=0/1 — NeXium guest input and virtual-audio A/B

**Isolated experimental child of Draft PR #200. DO NOT MERGE.** No production
game C code, original MAP02 renderer, audio engine, `source/main.c`, normal
`Makefile`, or original PS1 assets are altered by this stage.

## Why two guest runs?

The previous synchronized [PR #200](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/200)
passed GCC and Clang ASan/UBSan **host-DSP** comparison: the exact same
synthetic pre-switch PCM, a MAP02 A selection and no-note next cue produced
49,128 retained-tail samples against zero legacy samples, with identical
SEQ clocks and 48/48 differing 512-frame blocks. The independent virtual
NeXium PCM of #198 and #196 proved guest output but did not compare both
opt-in wet-tail binary modes.

The new workflow builds WET_TAIL=0 and WET_TAIL=1 from the exact same
source/run, records independent SHA-256 values and validates NRO0 headers.
For **each variant**, a fresh NeXium guest executes the same A→B sequence
against the MAP02 tactical grid. The test captures three screenshots and
a separate virtual stereo 48-kHz s16le PCM recording via PulseAudio's null
sink. Evidence includes same-run binary receipts, guest logs, screenshots,
and a machine-readable verdict.

## Fail-closed checks

`tools/audit_map02_nexium_wet_tail_ab.py` confirms:
- Every NRO SHA-256 matches the same GitHub run ID/attempt/checkout SHA.
- Both programs are valid and *different* NRO0 binaries.
- Both guest displays visibly show the blue `AUDIO ACTIVE` marker, A
  selection range highlight and its removal after B. Screenshot color and
  region thresholds reuse the proven MAP02 NeXium input checks.
- Both guest runs attach to PulseAudio and record at least 20 seconds of
  independent nonzero stereo virtual PCM.
- The verdict distinguishes *two guests running music and receiving A/B*
  from any unsupported claim of **sample-aligned wet-tail reverb**.

Nine generated-only Python fixtures reject missing sink, muted PCM, a
missing selection/cancel highlight, corrupt NRO SHA, wrong run/attempt,
incomplete stereo frames and insufficient duration. Both original MAP02
input regression and the exact-clock synthetic DSP test are re-run under
GCC and Clang with ASan/UBSan in this same workflow.

## Limitations / required future proof

**The two guest recordings are sequential, not sample-aligned, and may be
subject to different emulator startup, guest scheduling and host monitor
timing.** Their different waveforms, levels, timestamps or hashes must
NOT be interpreted as isolated STUDIO_C reverb causality. The optical
highlights establish the *game state* changed, not that the audio owner
necessarily accepted the new cue; the latter needs actual guest audio
scene POST/ACCEPT/PCM trace correlation or a deterministic guest fixture.
The host #200 experiment already isolates DSP state under controlled
conditions, but a future guest-level causal test requires identical
stimulus and synchronized, trace-verified render blocks.

Virtual PulseAudio does not establish speaker/DAC output on physical
Nintendo Switch. This stage imports no Vandal Hearts copyrighted music
or disc files.

Keep #194 → #196 → #198 → #200 and this child as separate Draft PRs.
