# MAP02 v113 — Native Unai readback/store outcome transitions across VBlank

Stacked after [v112 Draft PR #103](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/103).

## Why this stage exists

v111 distinguishes four observed cases per dispatched Unai GP0 command:
24-point sampled VRAM unchanged/changed × instrumented native 16-bit
pixel-store attempts absent/present. v112 finds consecutive runs of
unchanged samples with actual store attempts and counts crossings of
observed emulator VBlank callbacks. Neither retains **all transitions
between outcome classes**, including transitions to and from sampled
changes or handlers without instrumented stores.

v113 independently reads the same **private, pinned PCSX ReARMed
synthetic** event journal and classifies adjacent observed Unai callback
pairs by the four v111 outcomes. It separates adjacent pairs that stay
within one ordinal VBlank interval from those that cross one, two, three
or four VBlank callback markers. A pair spanning two markers is counted
once as an adjacent handler pair and twice as an edge witness.

The auditor requires a complete, immediately adjacent Unai
handler/readback/store/same-value-store quartet; a VBlank cannot split
the quartet. It reconciles:

- Per-interval observed handler counts to v111's original sample/store
  partitions.
- All same-interval pairs and coarse GPU class transitions to v110.
- All cross-VBlank observed-handler pairs to v110's total pair count.
- Each VBlank boundary's closest observed GP0 classes to independent
  v110 witnesses, including gaps with **multiple VBlank callbacks
  between the same adjacent GPU handlers**.
- Exact counts of adjacent qualifying zero-sample-delta/native-write
  pairs per VBlank edge to v112.
- Total pair counts to `max(native_observed_handlers - 1, 0)`,
  without double-counting multi-VBlank pairs.

GCC/Clang regression tests include changed/unchanged sample
transitions, native stores of unchanged values, one and two VBlank
edges between consecutive observed callbacks, absent pre-first or
post-last witnesses, and cases where v110 class totals remain
unchanged but outcome transitions differ. Unsupported opcodes,
impossible readback counts, forged native CPU cycles and split
four-event groups are refused.

The pinned GCC/Clang full emulator pipeline runs v113 on its **already
private** V104_RENDERER_EVENTS.jsonl and uploads only the aggregate
`proof/public/v113-vblank-outcome-transitions.json`; raw GPU opcode
headers, VRAM pixels, ROM assets, original game code and private
journal records remain inaccessible as public artifacts.

## Strict evidence limits

'Previous' and 'next' describe recorded callback append order, NOT
GPU completion timestamps. An intervening native emulator VBlank
observation does **not** prove that all VRAM pixels persisted, or that
any specific command was rendered on physical hardware. Only 24
sample locations and instrumented software Unai write sites are
observed; hardware/assembly/DMA and other renderer paths remain
out of scope.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

The changes remain in a stacked Draft PR. `main` is untouched.
