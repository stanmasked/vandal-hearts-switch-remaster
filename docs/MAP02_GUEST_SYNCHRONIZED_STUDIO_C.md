# MAP02: guest-side exact-clock synthetic STUDIO_C wet tail

**Experimental Draft, DO NOT MERGE.** This is a separate child of [PR #207](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/207), whose NeXium first-page PCM analysis already passed. It addresses one unresolved limitation: **two independent guest PCM monitor recordings are not sample-aligned**. Differences between WET_TAIL=0 and WET_TAIL=1 NRO captures cannot isolate a reverb-tail effect.

## Experimental counterfactual inside one Nintendo Switch guest

The existing host-generated-only synchronized reverb test from [PR #200](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/200) is now implemented as a self-contained, single-clock DSP replay **inside the actual libnx guest binary**, using the real native SEQ, SPU, STUDIO_C and music director code:

- Initialize two independent native SPU/music-director instances, identical sample fixture, Gaussian interpolation and reverb depth. Only `keep_reverb_across_cues` differs (0 reset vs 1 retained).
- Synthesize **64 × 512** 44.1-kHz stereo blocks in exact lockstep from an identical generated SEQ. Require every pre-switch PCM block and all wet-history state to match byte-for-byte.
- Feed the same MAP02 A-confirm game input contract, producing the same new scene in both; switch at one **shared block boundary** to a validated SEQ that generates **no new notes or dry voices**.
- Synthesize **48 × 512** further stereo blocks in lockstep. Require **all 48 blocks to differ**, reset-mode output to be exactly zero, retained mode to be nonzero, equal director phases/SEQ event clocks and different wet-history PCM hashes.
- Request explicit silence; require both PCM blocks and all reverb-history work area samples to become zero; detach.
- Repeat the **entire trial a second time**, with identical hashes, nonzero counts and block outcomes. Any broken invariant records a failure-line number and fails closed.

No PS1 game image, original music bank, physical audout stream or scene timer is used to drive this synthetic test. It is deliberately a **host-style controlled DSP experiment compiled and executed on the guest's architecture**, run **only after** the real audio worker has stopped and joined. It neither changes gameplay's music timing nor tries to compare unrelated host-monitor recordings.

## Evidence transport

The standalone `VH_MAP02_AUDIO_SYNC_TAIL_WITNESS=1` opt-in Makefile adds no code to the default NRO. After the existing two post-join optical receipts (audio scene timeline, first 48-kHz PCM page metrics), a third **`VHSYNC01`** CRC32-protected optical packet is displayed for eight seconds.

`tools/decode_guest_sync_studio_c.py` validates the screenshot's recovered 924-byte packet, magenta-window calibration, CRC32, zeroed unused bytes, same-clock proof flags, replay count, scene note counts, 64/48 block counts, all-different tails, zero reset samples and divergent wet/reset hashes. The CI boots two otherwise identical diagnostic binaries with outer wet-tail setting 0/1, and requires **the same synthetic proof fingerprints in both**—a consistency check, not comparing their independent PCM monitor timing.

The identical C source is also compiled for GCC and Clang under ASan/UBSan with a generated-only regression; 12 Python packet fixtures reject manipulated proof flags, bad CRC, missing causal effect, new notes, wet/reset silence, nonrepeatability and reserved-byte violations.

## Carefully bounded claims

A passing NeXium receipt **does establish the effect of retaining STUDIO_C wet state at a common synthetic cue boundary within a guest process**. It does **not** yet establish sample-aligned effects on the **live audout music path**, PS1 soundtrack fidelity, any physically audible Switch speaker output or equal music timing between independent guest sessions. The prior real guest A/B scene acceptance and first-page measurements from [#205](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/205)/[#207](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/207) remain independent evidence.

The old frozen-source immutable audio guard is not changed. It may fail because experimental source instrumentation differs from its historical snapshot. Keep parent stack and this child Draft, no automatic merges, and do not upload copyrighted source music.
