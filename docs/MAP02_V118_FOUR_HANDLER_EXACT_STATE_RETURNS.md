# MAP02 v118 — exact sampled VRAM state returns across four Unai callbacks

Stacked after v117 [Draft PR #108](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/108).

## Scope

v118 extends the private pinned synthetic PCSX ReARMed Unai observer
from three successive post-handler 24-point VRAM samples (v117) to
four: A–B–C–D. The fourth sample D is compared **in native memory**
with the previous three sets of exact 16-bit values. The classification
is mutually exclusive in descending recency:

1. D equals C (same as previous).
2. D differs from C, but equals B (return to two back).
3. D differs from C and B, but equals A (return to three back, A–B–C–A).
4. D differs from all three.

The 0–4 VBlank label counts recorded callbacks **between A and D**,
not elapsed frames, GPU CPU cycles, or a physical display scanout.
Each four-callback window contributes to exactly one bin. Windows
overlap in the expected sliding sequence; their population is
`max(0, observed_Unai_handlers - 3)`.

The existing private event JSONL and v115/v116/v117 native metrics
APIs remain unchanged. Three prior sets of 24 values are retained
inside the native process only and all three are wiped on reset.
No actual pixel value or pixel hash is sent to stdout or a public
artifact. New `vh118_get_quadruplet_metrics` validates legacy
metrics and the 20 exclusive aggregate counter bins.

An independent verifier checks the five gap populations directly
against strict canonical private VBlank/Unai append order and
revalidates the previous v117 report before publishing sanitized
`proof/public/v118-quadruplet-summary.json`.

Native GCC and Clang regressions cover A–B–C–A, A–B–C–B,
A–B–C–C, A–B–C–D, the equal-state precedence rule,
0–4 intervening VBlank callbacks, overlapping windows, all
previous-sample cache erasure, fifth-VBlank fail-closed behavior,
preservation of earlier APIs, corrupted native counters and
wrong-gap attribution. The full pinned PCSX workflow also
executes the actual patched software renderer for both compilers.

## Evidence limitations

This observes only 24 selected 16-bit locations after four successive
**observed** native Unai callbacks. It does not prove full-VRAM
persistence or restoration, PS1 GPU completion timing, retail Vandal
Hearts MAP02, physical PlayStation scanout, or Switch HD rendering
equivalence.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

Main remains untouched; this is a stacked Draft PR.
