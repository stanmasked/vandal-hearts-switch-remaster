# MAP02 — opt-in pre-submit audout PCM identity probe

This is a **research-only child of Draft PR #212**. Its parent commit
`6b323283322e5e866ef4cf19336daf9934ab3554` is an existing **five-of-five
GitHub Actions green checkpoint** and must not be rewritten or merged.

## Scope

The unmodified default `MAP02_AUDIO_PRESUBMIT_WITNESS=0` uses the existing
audout pipeline with no new PCM hashing. A separate explicit build enables
the observer:

```sh
make -f Makefile -f Makefile.map02-audio \
  MAP02_AUDIO_BUILD=build/map02-presubmit \
  MAP02_AUDIO_PRESUBMIT_WITNESS=1 map02-audio-nro
```

No PlayBuffer replacement, injected music assets, resampler reset or additional
libnx call is introduced. All research output is generated, not sourced from
the original game. The additional hash work is bounded to the first **eight
normal pages** after a fresh owner-thread session. The final cooperative-stop
taper is excluded.

For each monitored page the worker:

1. **Seals** the exact post-resampler, post-start-ramp signed PCM16 stereo
   bytes once, immediately before the existing output recovery dispatcher.
   Stores only number of frames and two fingerprints (FNV-1a64 and CRC32),
   **never** a retained PCM pointer or audio sample copy.
2. Immediately before the **actual `audoutPlayBuffer` call**, compares the
   descriptor's `buffer` + `data_size` PCM bytes against the sealed page.
   If bytes or frame count differ, the opt-in observer fails closed; it does
   not resynthesize a replacement page or advance the music clock.
3. Records a descriptor-release-confirmed successful return, or retains the
   exact sealed identity for an audout error/retry. An unsuccessful or ambiguous
   lease result must not be miscounted as successfully played audio.
4. Only **after the audio worker joins**, optionally prints one bounded CSV:
   `index,frames,fnv1a64,crc32,attempts,successful_returns` and the count of
   rejected mismatches. No worker-thread printing or filesystem writes.

Host regression `tests/test_vh_audout_presubmit_witness.c` tests single-bit
PCM corruption, a changed page length, a failed first audout attempt followed
by an identical retry, second arm while pending, and eight-page capacity.
The independent workflow `.github/workflows/map02-audout-presubmit.yml`
compiles GCC and Clang C11/ASan/UBSan tests and **builds** the special libnx
NRO; no default Makefile target or existing PR #212 CI is changed.

## Evidence and what it does *not* prove

A matching pre-submit digest means only that the generated PCM page was
unchanged immediately before the caller entered `audoutPlayBuffer`. Successful
lease release proves only the API returned this descriptor. It does **not**
prove the service consumed each individual PCM value, actual DAC scheduling,
audible playback, speaker output, or sample alignment between music cues.
Comparing the virtual PulseAudio recording to this witness requires a later
explicitly clocked matching experiment: virtual sink audio can be resampled,
delayed, or contain unrelated sounds.

The observer is not cryptographically authenticating data; the two independent
fingerprints are bounded diagnostics. It is not permitted to read buffers while
owned by audout, nor to block, allocate, or write files inside the callback.

**Keep child PR Draft / DO NOT MERGE** until host regressions, opt-in NRO
construction, and audout-ownership semantics have been reviewed.
