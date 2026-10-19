# MAP02: synchronized guest 44.1-kHz → 48-kHz audout format bridge

**Research-only Draft / DO NOT MERGE.** Child of verified [PR #210](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/210), which reproduced identical generated-only STUDIO_C wet-tail PCM under GCC, Clang and both NeXium guest binaries.

## A specific missing layer

PR #210's same-clock DSP comparison used the native PS1 SPU output at **44,100 Hz**. The real Switch audout thread converts that to **48,000 Hz stereo s16le** with a stateful integer resampler and a **192-output-frame ramp** on device startup.

The new isolated `source/vh_guest_native_48k.c` receives the very same two **synchronized 512-frame** 44.1-kHz SPU blocks from the #210 synthetic test. It applies two independent instances of the **unchanged production** `vh_audio_resample_process()` and `vh_audio_output_ramp_apply()` on every generated block, without submitting either output buffer to the live audout device.

The experiment demands:
- Identical 48-kHz PCM pages before the common scene transition (64 blocks)
- Exactly equal 48-kHz stereo output **frame counts** on the two synthetic paths
- All **48 post-switch pages** must differ, with retained-history output nonzero
- A special distinction between the **first reset-mode page** and later pages: the stateful resampler may interpolate **one stereo output frame from the previous scene**, so its first reset page is allowed up to **2 nonzero sample values**, but *all later reset pages must contain zero*
- Different retained-history and reset post-process hashes
- Two complete synthetic trials must have identical 48-kHz lengths, nonzero counts, output hashes and boundary-residue values

The paired DSP test does **not** assume that interpolation necessarily produces a nonzero value: it measures the actual first-page count and rejects more than one stereo frame of residue.

### Independent exact-boundary and compiler/guest comparison

A separate asset-free `tests/test_vh_guest_native_48k_boundary.c` exercises the **production resampler and output ramp directly**, without SEQ/SPU or optical parsing. It includes both a high-amplitude generated stereo tone (+10000/−10000, which produces exactly 2 nonzero transition values) and a low-amplitude generated tone (+1/−1, whose fractional first-page residue truncates to **0 signed PCM values** at the same 64-block boundary). Hence the correct first-reset-page requirement is **0 through 2 signed nonzero values**, rather than exactly 2 for every source amplitude. After exactly 64 × 512 source frames of a generated `+10000/-10000` stereo tone, a zero block has **one interpolated stereo output frame** at the particular transition phase; the expected first signed samples are `+7812/-7812`, with two nonzero sample values total, and **47 subsequent silence blocks must be exactly zero**. The C fixture repeats the entire transition twice and is compiled under both GCC and Clang with ASan/UBSan. A second phase-sweep regression initializes an independent production resampler/ramp for each of **17 different prefix lengths**: 1, 2, 3, 7, 8, 15, 16, 31, 32, 63, 64, 65, 127, 128, 147, 176 and 294 source blocks (including source-block boundaries exactly divisible by the resampler's 147-frame ratio). For a generated nonzero stereo tone followed by silence, each selected phase is required to produce exactly two signed PCM values in the first reset output page and no signal in the following five pages. This independently covers varied 44.1→48-kHz fractions but is **not an exhaustive mathematical proof for all possible transitions**. The quantitative numbers +7812/−7812 are specific to the 32768-source-frame boundary.

The guest source test also prints an exact `native48 ...` stdout receipt under GCC and Clang: 48-kHz pre/wet/reset FNV hashes, total prefix and tail frames, number of differing pages, retained nonzero values and reset-first/reset-later residue counts. A second fail-closed auditor `tools/audit_guest_native48_cross_arch.py` requires **all nine values** to agree exactly with **both** CRC-verified NeXium `VH48K001` receipts. Twelve generated-only tests reject forged compiler logs, guest values and unsafe claims. Any real compiler or architecture mismatch causes a failure rather than being rounded away or described as equivalent.

## Guest evidence and strict boundaries

Only the extra opt-in `Makefile.map02-guest-sync-tail` binary builds this observer. It adds a **fourth diagnostic optical screen** after guest audout has joined, with the same calibrated magenta border, a new `VH48K001` packet and CRC32. No copyrighted PS1 music data, raw PCM arrays, file I/O or extra work in the live audio thread.

`tools/decode_guest_native_48k.py` verifies first/remaining reset residue, complete block counts, physical bounds, hashes, immutable ticket context and packet integrity. Twelve generated positive/negative cases prevent false green results. GCC/Clang ASan+UBSan execute the same C DSP+output-stage fixture, while NeXium checks both outer NRO modes independently and requires identical synthetic 48-kHz metrics from both.

**Evidence limits:** This isolates retained STUDIO_C state *after the native 48-kHz conversion and device-start ramp*, but is still a generated-only in-guest counterfactual. It does not prove the live audout stream's content is sample-aligned across independent guest boots, physical speaker output, original PS1 music fidelity or a real gameplay cue's acoustic reverb.

Historical frozen-source identity checking is intentionally unchanged and may reject this research instrumentation. Parent PR #210, #207 and all earlier drafts remain unmerged. `main` is untouched.
