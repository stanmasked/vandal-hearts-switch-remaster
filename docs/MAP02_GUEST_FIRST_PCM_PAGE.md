# MAP02 — first rendered 48-kHz PCM page per accepted scene

**Experimental only. Draft / DO NOT MERGE.** This is a child of the fully verified guest
scene-trace [PR #204](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/204).
That parent established, for each real A/B game press in both WET_TAIL modes, the same
guest ticket traverses `INPUT → POST → ACCEPT → SUBMIT_CALL → RELEASE_RETURN`.
Its witness alone did not prove **sample content** for the first page after the
new scene was accepted.

## New narrow observation

A dedicated `Makefile.map02-guest-trace` enables
`VH_MAP02_AUDIO_PCM_WITNESS=1` *alongside* the already approved post-join
optical receipt. Default Switch and default MAP02 audio builds leave this
compile-time flag at zero and do not execute the added page scan.

Immediately after the owned SEQ/SPU stream renders a new scene's first
44.1-kHz block, converts it to stereo **48-kHz s16le**, and applies the
actual output ramp — but **before** handing the native page to audout — the
audio owner performs one bounded read-only scan of those same final
samples (count × 2 signed 16-bit values). Only the result is recorded:

- `PCM_PAGE_NONZERO`: at least one signed PCM sample differs from zero.
- `PCM_PAGE_SILENT`: every sample of that page is digital zero.

This is a **single first-page classification**, not a per-block realtime
logger. It allocates no memory, writes no file, copies no PCM, and does
not mutate DSP state or alter the PCM bytes submitted to audout.
The existing lock-free 64-slot witness retains the event's original
ticket serial, scene and guest monotonic timestamp. Both witness kinds
are serialized through the existing 924-byte CRC32 optical packet only
after the audio worker has joined.

## Fail-closed external verification

`tools/decode_map02_guest_scene_trace.py` requires, separately for
actual guest serial 1 (A, scene 2) and serial 2 (B, scene 1):

`INPUT → POST → ACCEPT → PCM_PAGE_NONZERO → SUBMIT_CALL → RELEASE_RETURN`

Every event must match the same serial and scene, with ordered indices
and nondecreasing guest timestamps. Any explicit `PCM_PAGE_SILENT` on
these tickets or absence/misrouting of `PCM_PAGE_NONZERO` fails.
Unrelated PCM activity, a wrong-ticket event, an optical checksum error,
or a missing audout release **must not** pass. There are 13 independent
Python negative/positive screenshot fixtures, a C11 event/optical
serialization regression under GCC+Clang with ASan/UBSan, and actual
paired WET_TAIL 0/1 libnx → NeXium smoke execution.

## What this does and does not prove

On a passing guest run, these observations establish that **the first
48-kHz PCM page generated for each accepted A/B musical scene was
nonzero immediately before its audout submit**, and its first native
submit/recovery call later returned successfully. They do **not**
measure the actual DAC/speaker waveform, show sound was audible,
confirm original copyrighted Vandal Hearts tracks, measure PCM energy
or original VAB fidelity, or isolate WET_TAIL effect in aligned guest
recordings. A successful page transfer is a buffer-ownership fact and
not a sound onset timestamp.

The parent [PR #202](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/202)
already established separate nonzero *virtual monitor* PCM in both
modes; the host synthetic reverb causal proof resides in
[PR #200](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/200).
This stage only closes **the ticket-to-first-page-content** evidence gap.
Keep all stacked PRs Draft; do not merge to `main`.
