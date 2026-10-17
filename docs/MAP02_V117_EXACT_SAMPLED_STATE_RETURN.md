# MAP02 v117 — exact three-callback sampled VRAM returns

Stacked after [v116 Draft PR #107](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/107).

## Why consecutive pairs are insufficient

v115 and v116 already compared the exact 16-bit values at 24 selected
post-handler VRAM positions **between adjacent observed Unai callbacks**,
discriminating equal changed-point counts from equal actual values, and
classifying the number of observed VBlank callbacks between the pair.

v117 observes **three** consecutive Unai handlers (A, B, C). The exact
24-value post-handler sample from C is compared to both B and A inside
the pinned synthetic PCSX ReARMed native process. Every triplet is
classified *once*, with mutually exclusive precedence:

- **Same as previous:** C == B across all 24 selected values.
- **Exact return to two-back:** C != B and C == A at all 24 values (A–B–A).
- **Different from both:** C != B and C != A at least at one selected value.

The gap label is the number (0–4) of **recorded emulator VBlank callback
events between A and C**, not an emulated CPU duration, frame scanout, or
full VRAM lifetime.

The native observer keeps only two previous 24-value arrays in process
memory, updates them after each callback and overwrites/erases them on
reset. It exports no raw pixel values, pixel hash, address or screenshot.
The original v115 and v116 APIs and the canonical v82 private JSONL
format remain intact.

The independent v117 private-log verifier reconciles all triplet counts
and five gap bins against **the canonical, strictly validated native
VBlank/Unai event append order**. It also validates the existing v116
exact adjacent-pair report in full. It rejects duplicate/malformed
native status, overflow, missing callbacks, missing triads, and counters
reported in the wrong VBlank gap despite correct global totals.

GCC and Clang test native A–B–A recovery, A–B–B persistence of the latest
sample, A–B–C distinct outcomes, four different VBlank gap lengths,
invalid fifth VBlank, malformed samples, legacy ABI compatibility and
full erasure of *both* previous sample buffers. The full pinned PCSX
synthetic emulator executes v117 in the real software renderer, checks
strict private logs and uploads only the sanitized aggregate
`proof/public/v117-triplet-summary.json`.

## Limitations

An exact A–B–A return refers only to the selected **24 sampled values**.
It does **not** establish that the complete VRAM returned to a previous
state, that GPU commands finished at any particular emulated CPU cycle,
that pixels survived hardware scanout, or that actual retail MAP02 or
Nintendo Switch HD rendering was reproduced.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

All changes remain in a stacked Draft PR; `main` is untouched.
