# Optional STUDIO_C continuation across gameplay music cues

This document describes an **opt-in, host-tested** behavior stacked on the
atomic SEQ/SPU bank-switch backport in draft PR #171.

## Contract

A `VhMusicScene` initialized with `vh_music_scene_init` defaults to legacy
behavior: each switch to another music cue resets the SPU reverb delay/FIR
history. Gameplay requiring this behavior **does not change**.

Before starting a music cue, the owning audio thread can call:

```c
vh_music_scene_init(&scene, &spu);
if (vh_music_scene_set_reverb_continuity(&scene, 1) != 0) {
    /* Stop startup; don't assume continuity was enabled. */
}
```

The setting is only accepted when the scene is initialized, silent and idle,
with no pending or active cue. Invalid values and changes during a fade or
active scene fail without changing the setting. The caller must serialize
requests with its PCM producer; this API is not callback-thread safe.

### Enabled behavior

On a **non-silent cue-to-cue** transition:

**The first cue started from silence always performs the legacy full
reverb/voice reset**, even with continuity enabled. The director cannot
inherit unexplained STUDIO_C history or borrowed sample pointers from
a previous SPU owner merely because the option was configured.

1. Validate the complete replacement pQES SEQ before changing the live
   player (including queued cue validation immediately before use).
2. Stop the old SEQ and release every borrowed old-bank PCM voice pointer.
3. Retain the STUDIO_C work/delay state, wet depth and interpolation mode,
   while resetting per-scene voice ownership and counters.
4. Begin the next SEQ at frame zero. Existing fade-in/fade-out logic
   still operates at 512-frame boundaries.

This preserves only the reverb *state*, not an outgoing bank PCM pointer.
The caller must still keep SEQ/VAB/PCM resources alive until the transition
is complete and must safely drain/retire previously submitted output pages
before freeing a bank. This setting does not manage audout descriptors.

### Silence and teardown

A request for silence **always** uses the legacy reset path, even if wet-tail
continuation is enabled. `vh_music_scene_detach` also always clears voices,
borrowed source pointers and the whole STUDIO_C state. The opt-in flag is
retained across detach for the lifetime of the initialized director, and can
be changed again only in the resulting silent/idle state.

A corrupted queued SEQ fails closed: the old SEQ, live SPU/reverb state
and old-bank pointer ownership are preserved until explicit teardown.
The renderer returns an error and silences that output block; callers must
not assume that the old cue can continue automatically after such an error.

## Verification and limitations

The synthetic regression compares an opt-in director with an unmodified
legacy director through 64 warm-up blocks and a two-block fade. It also
checks the first cue discards deliberately seeded stale silent-SPU state,
and compares 48 post-transition output PCM blocks while ensuring both
directors stay synchronized in SEQ clocks and scene stages. It verifies
the original PCM matches before the transition, that only the opt-in path
retains a precharged STUDIO_C tail at the cue change, and that both silence
and detach clear reverb. A queued-cue mutation test checks fail-closed
state and byte-identical old SEQ/SPU survival. The existing 1200-block 44.1-to-48-kHz audio director
scenario remains unchanged, and the same test now also runs a separate
**512-block opt-in versus legacy 48-kHz comparison** through three
eight-block fades. Both paths must have equal SEQ/scene clocks, equal
numbers of output frames and identical resampler timing, while their
sample histories are intentionally allowed to differ. The test
requires divergent post-switch **PCM16 samples**, not merely divergent
reverb state. Previous sample values in each resampler are
channel-audio data, not timing invariants.

The existing rapid gameplay mailbox stress now runs in **both** legacy
and opt-in modes: 3,200 blocks each, including 100,000 competing desired
scene updates, deferred requests during active fades, continuous 48-kHz
resampler timing and forced detach after playback. This probes the same
music scene scheduler under both configurations without adding a new
source-asset dependency.

An additional opt-in teardown/restart regression precharges the wet
tail with the first cue, forcibly detaches it, overwrites the old bank's
PCM memory, then starts a second cue. It compares 48 complete PCM output
blocks, SEQ clocks and the entire STUDIO_C history against a **freshly
initialized** reference synthesizer. This catches session-to-session
wet-state leakage or stale pointers after a bank unload.

A separate director-level synthetic PCM FIFO regression also prepares a
full 512-frame page from the outgoing cue, makes a non-silent opt-in cue
change, and verifies the already-queued page remains byte-identical and
can be consumed exactly once. The producer's subsequent PCM must come
from the new bank, and no stale voice pointer may survive. This covers
the portable `VhAudioStream` queue only; it is not proof that libnx
audout has retired all in-flight descriptors or that a caller may free
a bank without first completing the documented drain/synchronization.

Dedicated GCC and Clang ASan/UBSan jobs and existing Host SPU / libnx builds
must pass **for the exact merge candidate**. This development does not prove
real audible output or HOME/suspend behavior on a physical Nintendo Switch.
It uses synthetic test PCM only and contains no original copyrighted assets.

**Integration order:** merge/rebase PR #171 first; then review this stacked
PR independently. Keep both drafts until all relevant checks are satisfied.
