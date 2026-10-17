# MAP02 v116 — Exact sampled VRAM value identity by intervening VBlank callbacks

Stacked after [v115 Draft PR #106](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/106).

## Goal

v115 established that comparing exact post-handler values at **24 selected
16-bit VRAM positions** detects differences invisible to simple counts of
changed positions. Its results previously divided adjacent observed Unai GP0
handlers into "same observed VBlank interval" and "one or more VBlank events
between handlers." v116 preserves the **exact number of intervening observed
VBlank callbacks**: 0, 1, 2, 3 or 4.

The pinned PCSX ReARMed synthetic renderer keeps the previous actual 24
post-handler values solely in native process memory; it already erases them
on reset. v116 extends the native sidecar with three independent counters
for **each possible VBlank gap**:

- Equal numbers of changed sample points and exactly identical 24 final values.
- Equal numbers of changed sample points but different 24 final values.
- Different numbers of changed sample points.

All bins are strict non-overlapping classifications of adjacent *observed
Unai callbacks*. A pair separated by four observed VBlank callbacks is
counted **once** in gap 4, never four times. The existing v115 C API and
private v82 JSONL event schema are preserved unchanged. The native function
`vh116_get_gap_metrics` reconciles the sum of all bins against the original
v115 totals, including cross-VBlank totals, and rejects invalid states,
overflow, more than four callbacks or missing input.

A new independent private-log verifier `summarize_map02_v116_gap_identity_runtime.py`
compares the native counters against v114's strictly validated
per-gap readback-change-count trends and v115's native exact-equality
aggregates. This prevents a forged relocation of counts from gap 4 to
gap 0 even if the overall totals remain unchanged.

The synthetic GCC and Clang suites exercise exact identical/different
24-value comparisons with zero, one, two, three and four intervening
VBlank events, invalid fifth-edge/refusal, secure reset, malformed
samples, preservation of the original v115 metrics ABI, synthetic
multi-VBlank ordering and log-tampering refusals.

The full pinned PCSX ReARMed host workflow uses the existing original
private JSONL plus its new **native aggregate-only** stdout marker,
performs strict reconciliation, and writes
`proof/public/v116-sample-gap-summary.json`. Raw pixels, pixel hashes,
GPU addresses, private trace bytes and gameplay assets are not uploaded.

## Limits

Intervening callbacks do not prove GPU completion at a PlayStation CPU
cycle, unchanged *whole* VRAM, actual physical frame contents or display
scanout. Exact equality refers ONLY to the chosen 24 locations after
two adjacent observed synthetic Unai handlers; it does not certify
retail Vandal Hearts MAP02 or the Switch HD renderer.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The changes are isolated in a stacked Draft PR; `main` stays untouched.
