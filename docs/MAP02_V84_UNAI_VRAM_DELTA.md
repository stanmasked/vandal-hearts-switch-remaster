# MAP02 v84 — Unai handler-local 24-point source VRAM delta observations

v84 extends the successful pinned v83 Unai post-handler sequence with **read-only
before/after comparisons**, while preserving the real v78 emulator VBlank
callback and independent 2,380-sample GPU VRAM oracle.

The observation is restricted to the deliberately synthetic MAP02-like fixture.
In `--vh84-unai-vram-sample-smoke`, a successful signed `VH78SYN!` EXE
preflight enables the probe. The pinned Unai renderer reads precisely 24
16-bit VRAM values before and after each recognized GP0 handler: x positions
40, 56, 72, 88, 104, 120 and y=160..163. The probe **never writes VRAM**.

For every `gp0_unai_handled`, the bounded v80 event ring receives one
immediately adjacent `unai_sample_delta` record. Its `value` is the
integer number of sampled values which **differ** from the pre-handler
readback, in the closed range 0..24. It carries unknown cycle and frame
placeholders (zero). The v84 independent validator refuses unpaired events,
excessive delta counts, forged frame/cycle claims, missing genuine VBlank
edges, overflow, or contradictory v78 pixel-acceptance evidence.

The private report path is published only through the v82 exclusive,
fsync/readback byte-identical writer. The CI matrix builds the complete pinned
PCSX emulator under GCC and Clang and runs the signed synthetic fixture.
Raw per-command GPU headers and VRAM traces must remain **private**;
only aggregate counts and statuses are eligible as workflow artifacts.

## Interpretation / intentionally unresolved ambiguity

- **delta above zero:** at least one of the *sampled VRAM values* was
  different immediately after the Unai handler. This is evidence of changed
  memory state, not a direct instrumented count of PutPixel calls.
- **delta zero:** sampled values did not differ, but this does **not** prove
  that there were no writes. The handler could write an identical value, draw
  outside the 24 probes, be fully clipped, or perform a write later.
- A sample does not provide exact write timing, renderer bypass provenance,
  hardware pixel mask equivalence, blending correctness, or the complete
  VRAM history. Direct PutPixel entry and value-write detection is a later
  stage, not something inferred here.

The v84 aggregator counts changed and unchanged handlers within
consecutive **emulator** VBlank boundaries and before/after those edges.
No GPU CPU cycles are invented. A real hardware frame, original retail
MAP02 gameplay, or Switch rendering equivalence is not established.

`actual_PutPixel_calls_observed=false`
`same_color_write_distinguished=false`
`physical_ps1_vblank_verified=false`
`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

The production renderer on `main` is untouched and HD remains disabled.
