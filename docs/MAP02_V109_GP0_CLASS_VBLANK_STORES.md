# MAP02 v109 — Unai GPU primitive families by VBlank event order

Stacked after v108 [PR #99](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/99).
Earlier v80-v108 pinning, private file publication and instrumented GPU
tests remain mandatory and unmodified.

## Scope

The original v83 Unai observer records an already-dispatched GP0 command
header, followed immediately by its v84 24-location VRAM readback delta,
v85 native 16-bit store-attempt count, and same-value write count.
The independent v108 audit distributes these observations by sequence
position relative to four real emulator callbacks for VBlank. No GPU
CPU-cycle or frame identity is available at the Unai callback.

New v109 groups the supported command header by **coarse family**:

- GPU VRAM fill (`02h`);
- Polygons (`20h–3Fh`);
- Lines/polylines (`40h–43h`, `48h–53h`, `58h–5Fh`);
- Rectangles/sprites (`60h–6Bh`, `70h–7Fh`);
- GPU environment state (`E1h–E6h`).

The decoder strictly refuses unsupported gaps rather than guessing
their semantics. It requires an indivisible four-event block for
each Unai handler and refuses a state-only E1–E6 command with
instrumented 16-bit pixel-store attempts.

Every interval's class histogram is independently reconciled to v108
Unai callback counts, VRAM sample changes, all native store attempts,
same-value writes and changed-value writes. The totals are also
reconciled across intervals, without duplicating or discarding events.

## Privacy and CI

The already existing private, canonical native event journal remains
the *only* source. The pinned GCC/Clang PCSX ReARMed synthetic host
workflow runs the new analyzer after the existing v108 validation.
Only aggregate per-family counters are placed in
`proof/public/v109-gp0-class-summary.json`; no raw GP0 header words,
VRAM values, addresses, synthetic binaries or private journal bytes are
uploaded. The independent v109 native/Python regression workflow
checks class boundaries, invalid opcode gaps, forged timestamps,
malformed four-event groups, VBlank separation and ordinary v83–v108
compatibility.

## What is not established

This is a **host callback append-order** correlation, not a proof
of actual PlayStation GPU raster completion, hardware VBlank latency
or original retail MAP02 draw-call behavior. The instrumented Unai
software pixel store sites do not cover every assembly renderer,
DMA or alternate GPU path. No physical PS1 or Nintendo Switch HD
rendering equivalence is inferred.

`original_retail_MAP02_verified=false`
`physical_ps1_raster_timing_verified=false`
`HD_replacement_approved=false`

Draft is stacked on v108. `main` remains untouched.
