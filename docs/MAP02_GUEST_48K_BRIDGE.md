# MAP02: synchronized guest 44.1-kHz → 48-kHz audout format bridge

**Research-only Draft / DO NOT MERGE.** Child of verified [PR #210](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/210), which reproduced identical generated-only STUDIO_C wet-tail PCM under GCC, Clang and both NeXium guest binaries.

## A specific missing layer

PR #210's same-clock DSP comparison used the native PS1 SPU output at **44,100 Hz**. The real Switch audout thread converts that to **48,000 Hz stereo s16le** with a stateful integer resampler and a **192-output-frame ramp** on device startup.

The new isolated `source/vh_guest_native_48k.c` receives the very same two **synchronized 512-frame** 44.1-kHz SPU blocks from the #210 synthetic test. It applies two independent instances of the **unchanged production** `vh_audio_resample_process()` and `vh_audio_output_ramp_apply()` on every generated block, without submitting either output buffer to the live audout device.

The experiment demands:
- Identical 48-kHz PCM pages before the common scene transition (64 blocks)
- **Exactly 35,665** 48-kHz stereo output frames over the 64 synchronized source blocks and **exactly 26,750** over the following 48 blocks: these counts are derived from the original integer output-tick arithmetic of 512-frame 44.1-kHz input blocks and fail on even a one-frame deviation
- Exactly equal 48-kHz stereo output **frame counts** on the two synthetic paths
- All **48 post-switch pages** must differ, with retained-history output nonzero
- A special distinction between the **first reset-mode page** and later pages: the stateful resampler may interpolate **one stereo output frame from the previous scene**, so its first reset page is allowed up to **2 nonzero sample values**, but *all later reset pages must contain zero*
- Different retained-history and reset post-process hashes
- Two complete synthetic trials must have identical 48-kHz lengths, nonzero counts, output hashes and boundary-residue values

The paired DSP test does **not** assume that interpolation necessarily produces a nonzero value: it measures the actual first-page count and rejects more than one stereo frame of residue.

### Stage 213: full recorder walk with injected clock faults (2026-10-19)

The actual `tests/test_guest_sync_studio_c.c` host fixture now directly walks the diagnostic **observer** over all **64 prefix plus 48 post-switch pages**, in addition to replaying the real synthetic DSP scenario and exercising the production resampler in the separate independent boundary fixture. Input to this extra observer walk is generated silence, intentionally isolating page ordering/tick invariants from wet-tail sample values. For every page, an independently derived literal **44,100→48,000-Hz** clock is compared with the recorder's running prefix/tail frame count.

Negative cases deliberately submit a skipped first prefix page, an early tail, invalid boundary indices, a repeated page at both the beginning and end, and both prefix and post-switch **+1 frame counter corruption** midway through the sequence. The intended result is immediate refusal without consuming converter state, then success when the corrupted counter is restored. End totals are exactly **35,665 / 26,750**, with all-zero nonzero-sample counters for this added silence-only fixture. Existing same-clock STUDIO_C reverb test and all legacy source preservation checks remain unchanged.

A separate *local arithmetic-only* C oracle was compiled and executed successfully with **GCC and Clang under UBSan**: among 112 page lengths, **81 are 557 frames and 31 are 558 frames**. This verifies the independent integer-clock arithmetic only; it is **not** a claim that repository host fixtures, Switch NRO or NeXium have passed. New head run validation must be performed on its exact SHA and artifacts before reporting GCC/Clang/NeXium parity.

### Independent checks on every output page (continuation of stage 212)

The guest diagnostic recorder now checks the **exact output-frame length of every one of the 112 generated 512-frame input pages**, not only the final 35,665/26,750 frame totals. An integer-clock oracle independent of the resampler state derives the total completed output frames after `n` input blocks as

```
frames(n) = 0                                      if n == 0
frames(n) = floor(((n * 512 - 1) * 48000) / 44100) + 1  otherwise
```

For each page, the observer checks `frames(n+1)-frames(n)` against the resampler output length, in both wet and reset paths. Before consuming the next input page, it also checks the cumulative emitted frame count, both converters' consumed-source-frame counters, and their next output ticks against this independent clock. Consequently, a missing, repeated or out-of-order prefix or tail block fails immediately; a one-page +1/−1 drift cannot be hidden by a correct sum. A separate direct production-resampler C regression now asserts **all 112 exact per-page lengths** for both complete replays, as well as the pre/post totals and the earlier 17-phase first-transition oracle. Added C negative fixtures reject skipped, duplicated, early-tail and out-of-range synthetic page indices without using game assets.

This is a **source-level guest-side gate**; the optical `VH48K001` packet still carries aggregate lengths and PCM hashes rather than individual page lengths. A passing decoder alone must not be taken as proof that a particular guest run executed the added source gate: the NRO SHA and exact workflow run must be independently verified. The new revision remains unverified in NeXium until its queued workflow executes successfully.

### Independent exact-boundary and compiler/guest comparison

A separate asset-free `tests/test_vh_guest_native_48k_boundary.c` exercises the **production resampler and output ramp directly**, without SEQ/SPU or optical parsing. It includes both a high-amplitude generated stereo tone (+10000/−10000, which produces exactly 2 nonzero transition values) and a low-amplitude generated tone (+1/−1, whose fractional first-page residue truncates to **0 signed PCM values** at the same 64-block boundary). Hence the correct first-reset-page requirement is **0 through 2 signed nonzero values**, rather than exactly 2 for every source amplitude. After exactly 64 × 512 source frames of a generated `+10000/-10000` stereo tone, a zero block has **one interpolated stereo output frame** at the particular transition phase; the expected first signed samples are `+7812/-7812`, with two nonzero sample values total, and **47 subsequent silence blocks must be exactly zero**. The C fixture repeats the entire transition twice and is compiled under both GCC and Clang with ASan/UBSan. A second phase-sweep regression initializes an independent production resampler/ramp for each of **17 different prefix lengths**: 1, 2, 3, 7, 8, 15, 16, 31, 32, 63, 64, 65, 127, 128, 147, 176 and 294 source blocks (including source-block boundaries exactly divisible by the resampler's 147-frame ratio). For a generated nonzero stereo tone followed by silence, each selected phase is required to produce exactly two signed PCM values in the first reset output page and no signal in the following five pages. This independently covers varied 44.1→48-kHz fractions but is **not an exhaustive mathematical proof for all possible transitions**. The regression now asserts the **independently derived exact first signed output sample and output frame count for each of the 17 phases**, rather than checking only an upper bound or the nonzero count. In particular, at 147 and 294 source blocks, even though the total source-frame count is divisible by 147, the converter **holds the last fractional interpolation of the preceding block**; the first sample of the next page is `+9187/−9187` (558 frames), **not zero**. At 64 blocks, the corresponding values are `+7812/−7812` (558 frames). A generated low-amplitude `+1/−1` fixture at 64 blocks separately proves that fractional interpolation can quantize to all-zero output.

The exact 17-phase reference values were independently checked against a source-equivalent reconstruction of the production integer resampler and 192-frame ramp, compiled with **GCC 14.2 and Clang 17**, `-Wall -Wextra -Werror -fsanitize=address,undefined`: both passed all 17 amplitude/frame-count assertions and the low-amplitude silent case. This preflight is **not** a claim that the still-queued GitHub Actions or NeXium jobs have run.

The guest source test also prints an exact `native48 ...` stdout receipt under GCC and Clang: 48-kHz pre/wet/reset FNV hashes, total prefix and tail frames, number of differing pages, retained nonzero values and reset-first/reset-later residue counts. A second fail-closed auditor `tools/audit_guest_native48_cross_arch.py` requires **all nine values** to agree exactly with **both** CRC-verified NeXium `VH48K001` receipts. Fourteen generated-only tests reject forged compiler logs, guest values and unsafe claims, including intentional one-frame output-clock drift. Any real compiler or architecture mismatch causes a failure rather than being rounded away or described as equivalent.

## Guest evidence and strict boundaries

Only the extra opt-in `Makefile.map02-guest-sync-tail` binary builds this observer. It adds a **fourth diagnostic optical screen** after guest audout has joined, with the same calibrated magenta border, a new `VH48K001` packet and CRC32. No copyrighted PS1 music data, raw PCM arrays, file I/O or extra work in the live audio thread.

`tools/decode_guest_native_48k.py` verifies first/remaining reset residue, complete block counts, physical bounds, hashes, immutable ticket context and packet integrity. Fourteen generated positive/negative cases prevent false green results, including both +1 and −1 48-kHz frame drift. GCC/Clang ASan+UBSan execute the same C DSP+output-stage fixture, while NeXium checks both outer NRO modes independently and requires identical synthetic 48-kHz metrics from both.

**Evidence limits:** This isolates retained STUDIO_C state *after the native 48-kHz conversion and device-start ramp*, but is still a generated-only in-guest counterfactual. It does not prove the live audout stream's content is sample-aligned across independent guest boots, physical speaker output, original PS1 music fidelity or a real gameplay cue's acoustic reverb.

Historical frozen-source identity checking is intentionally unchanged and may reject this research instrumentation. Parent PR #210, #207 and all earlier drafts remain unmerged. `main` is untouched.
