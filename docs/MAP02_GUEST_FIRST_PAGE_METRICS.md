# MAP02 — quantitative first PCM page for A/B musical scenes

**Experimental, Draft / DO NOT MERGE.** This stage is a child of the
independently successful [PR #205](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/205).
The parent proved NeXium's real A-select and B-cancel musical scene
tickets each generated a nonzero 48-kHz PCM page before audout submission.
It did not quantify those pages.

## Exact observed numbers

The diagnostic-only flag `VH_MAP02_AUDIO_PCM_METRICS=1` adds a bounded,
fixed-allocation **one-pass** read-only measurement of the first **final,
post-resample, post-ramp stereo s16le** page for ticket 1/scene 2 and
ticket 2/scene 1. For each first page, the audio-owner thread records:

- Frame count (48-kHz stereo frames) and signed-sample count
- Count of nonzero signed 16-bit sample values
- Absolute peak amplitude (0..32768, capturing the -32768 edge)
- Exact 64-bit sum of squared signed samples; RMS is computed offline as
  `sqrt(sum_squares / (frames * 2))`
- FNV-1a 64-bit hash of the PCM samples in **little-endian 16-bit** order

It stores at most **two 28-byte value records**, keyed by ticket and scene.
No PCM arrays, sound-bank data or copyrighted material are retained in the
witness. No dynamic allocation, I/O, callback blocking, modification of
synthesis states, or additional observation of later pages occurs.
Default MAP02/audio NROs do not define this flag.

## Post-join transport and analysis

Only after the audio thread joins, the guest presents two different
black/white optical receipts with the *same* magenta frame:

1. The already verified `VHFBTRC1` CRC32 scene-event packet for
   `INPUT → POST → ACCEPT → PCM_PAGE_NONZERO → SUBMIT_CALL → RELEASE_RETURN`
   on each ticket
2. A new `VHPCM01A` CRC32 packet containing the **quantitative metrics**

The second display follows the first and is never rendered during normal
gameplay/music. Existing image calibration automatically accounts for the
NeXium viewport's scale and borders. New independent decoder
`tools/decode_map02_guest_pcm_metrics.py` checks exact packet magic, CRC32,
zeroed reserved bytes, mode, scene IDs, positive/possible frame lengths,
nonzero sample counts, peak and energy consistency, plus derives RMS.

`.github/workflows/map02-guest-scene-trace.yml` captures *both*
screenshots from each WET_TAIL=0/1 NRO in the same CI run and archives
raw PNG, parsed per-mode JSON, summary JSON and guest logs. Nine new
synthetic screenshot regression fixtures reject false metrics and corrupt
checksums; a native C11 metrics test under GCC/Clang and sanitizers checks
the exact encoder and edge-value handling.

## Interpretation limits

These measurements are **quantitatively grounded in the actual first PCM
page of each accepted scene**. However, WET_TAIL=0 and =1 run sequentially,
and their note clocks, startup times, focus and emulator scheduling may
differ. Differences in RMS, peak, sum-squares or hashes are therefore
**NOT a sample-aligned causal test of STUDIO_C reverb**. The prior exact-clock
synthetic DSP test in [PR #200](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/200)
established retained-tail causality at host level.

The first-page metrics do not prove speaker/DAC output, audible latency
or fidelity to original Vandal Hearts audio. No PS1 game resources are
uploaded. The existing frozen-source provenance guard is left untouched
and is **expected to reject this research branch**, where optional audio
instrumentation deliberately changes C source bytes.

Keep this PR and parents #205/#204/#202/#200/#198/#196/#194 Draft.
`main` and standard MAP02 renderer/build continue unchanged.
