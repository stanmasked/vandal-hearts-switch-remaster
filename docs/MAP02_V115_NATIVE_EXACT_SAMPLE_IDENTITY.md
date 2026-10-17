# MAP02 v115 — exact Unai 24-point VRAM sample identity in native memory

Stacked after [v114 Draft PR #105](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/105).

## Why counts are insufficient

The previous v84/v114 readback provides only an integer count of sampled
VRAM values that differ before versus after each observed Unai GP0 handler.
Two consecutive handlers may each change **one** of the same 24 sampled
locations but leave **different exact final 16-bit values**. The old
private v82 canonical JSONL cannot establish equality of those final
values: it never records the pixels.

## New native-only exact comparison

A distinct v115 sidecar is enabled only for the pinned synthetic PCSX
ReARMed v104 smoke. Its actual Unai callback reads the same 24 selected
post-handler VRAM 16-bit values into a transient native array. An in-process
C observer compares all 24 values individually against the previous
observed Unai callback; no probabilistic hash or fingerprint is used.

The native observer counts:

- Consecutive handlers with **equal changed-sample counts and identical**
  exact 24-value final snapshots.
- Consecutive handlers with **equal changed-sample counts but different**
  exact 24-value final snapshots.
- Consecutive handlers with different changed-sample counts.
- The same three categories when one or more emulator VBlank callbacks
  separate adjacent *observed* Unai handlers.

Each previous native 24-value snapshot is overwritten on the next handler,
and the cache is scrubbed with volatile byte writes on observer reset.
The current stack array is wiped immediately after the comparison.
No original pixel values, hashes, addresses, frame captures or raw game
materials are printed or exported.

**The canonical v82 private JSONL event schema and its existing v84
four-record Unai groups remain unchanged.** The observer hooks the
native v80 reset and successful VBlank append in the temporary pinned
emulator checkout, so it can classify the interval without inventing
unavailable GPU CPU-cycle timestamps.

The separate strict v115 report reader checks the native host stdout
aggregate against the original private v82/v114 event journal. It proves
that the sum of actual-value identical/different classifications exactly
equals the number of consecutive handler pairs with equal observed
**changed-sample counts**; it independently checks the count of pairs
crossing at least one observed VBlank callback.

GCC and Clang exercise the isolated native C sidecar, distinct exact values
with equal delta count, cross-VBlank equality, multi-VBlank gaps, disabled
observer, malformed input, failure-closed re-enable and secure cache reset.
The pinned PCSX synthetic-host pipeline compiles the sidecar into the
actual Unai renderer, requires its runtime pass marker, rechecks native
aggregate invariants, and exports only
`proof/public/v115-sample-identity-summary.json`.

## Limits

These comparisons cover exactly **24 selected 16-bit locations**, and
compare values from adjacent *observed Unai callbacks*, not complete
frame snapshots. Equal sampled values do not establish full VRAM
persistence, exact physical PS1 timing, native GPU completion or Switch
HD parity. No authentic retail MAP02 content was evaluated.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

This is a stacked Draft PR; `main` stays untouched.
