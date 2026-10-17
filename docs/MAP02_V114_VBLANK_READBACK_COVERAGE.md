# MAP02 v114 — VRAM sample-readback observation coverage around VBlank

Stacked after [v113 Draft PR #104](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/104).

## The observation boundary

The pinned synthetic PCSX ReARMed Unai observer records one readback
**count** of changed locations among 24 selected VRAM points after each
observed Unai GP0 handler; the stream also records instrumented software
16-bit-store attempts (including same-value writes) and four genuine
*emulated* VBlank callbacks. The sampled points are NOT a full VRAM
snapshot, and two equal counts do not imply identical pixel contents.

The prior v111–v113 reports conserve outcome classes and native store
counts, but still allow a frame interval with **no Unai readback at all**
to be confused with one whose observed readbacks happened to be zero.
v114 makes that distinction testable and permanent.

## New read-only audit

`summarize_map02_v114_vblank_readback_coverage.py` runs on the same
**private** pinned native JSONL trace and:

- Separately classifies five event-append-order buckets around four VBlank
  callbacks as **no readback**, **only zero deltas**, **only nonzero deltas**,
  or **mixed zero and nonzero deltas**.
- Counts observed readback callbacks, changed/unchanged sample readbacks,
  changed points among the 24 sampled positions, all instrumented native
  16-bit assignment attempts and same-value assignments per bucket.
- Identifies the three VBlank-to-VBlank windows with no observed native
  Unai readbacks and the longest consecutive run of such blind windows.
- Compares the *number* of changed sampled positions between adjacent
  observed Unai callbacks (increasing/equal/decreasing), both inside
  VBlank windows and across one or more VBlank markers.
- Records only the nearest observed changed-location counts on either
  side of each VBlank and how many VBlank callbacks lie between them.
  An absent predecessor/successor stays explicitly unknown.
- Reconciles all bucket sample/write totals to v111; all adjacent
  callback pairs and VBlank crossings to v113; total changed sample
  points and Unai handlers to the original strict v82 trace verifier.

The GCC/Clang regression suite includes three consecutive blind
between-VBlank windows, a two-VBlank gap between adjacent sampled
callbacks, forged sample counts and broken native quartets. It also
constructs two traces with exactly identical v111 and v113 reports
but reversed per-handler sample-delta intensity, which only v114 can
distinguish. A zero-delta readback remains an observation, not the
absence of an observation.

The full pinned emulator GCC/Clang workflow audits the **private** original
`V104_RENDERER_EVENTS.jsonl` and exports only sanitized aggregate
`proof/public/v114-vblank-readback-coverage.json`. Raw GPU headers,
pixel values, addresses, original game media, private traces and
synthetic EXEs are not exported.

## Hard limitations

A window with no readbacks provides **no evidence** of VRAM stability;
similarly an observed zero 24-point delta does **not** establish no
native stores or unchanged whole VRAM. A repeated sample-change **count**
cannot establish that the same pixels were changed. Callback append
order relative to emulator VBlank does not prove CPU-cycle accurate
GPU completion, physical PlayStation scanout, or Switch HD equivalence.

`original_retail_MAP02_verified=false`
`physical_PS1_vblank_verified=false`
`HD_replacement_approved=false`

Draft is stacked after v113; `main` is untouched.
