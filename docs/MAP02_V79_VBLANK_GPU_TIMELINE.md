# MAP02 v79 — VBlank-relative GPU command timeline (initial analysis gate)

## Verified starting point
v78's read-only hook observes the original PCSX ReARMed `psxRcntUpdate()` VBlank-start callback after `GPU_vBlank(1,0)`. Four distinct observed starts and 2,380 native VRAM sample comparisons are a **synthetic emulated** scene, not retail MAP02.

## New v79 analysis contract
A standalone, strict JSONL checker is developed for **ordered recorded events**, with:
- `vblank`: strictly increasing observer sequence number `seq`, `frame` and emulator `cycle`.
- `gp0` or `gp1`: 32-bit `word` and `seq`; means **command observed/submitted**, not completed.
- `vram_write`: `seq, x, y, value`; only an *instrumented actual write* qualifies, never a predicted write inferred from a GP0 command.
- `snapshot`: `seq, edge_seq, x, y, value`; explicit association with a previously observed VBlank edge.

VBlank intervals are half-open in observer ordering: `edge[i].seq < event.seq < edge[i+1].seq`. A command between events is attributed to that interval, without implying raster completion inside the interval. Snapshot values can be compared with the last **explicitly recorded** write to the same address; they cannot establish command causality or frame ownership by themselves.

Fail closed on out-of-order events, invalid frame or cycle continuity, invalid 16-bit BGR555 values, out-of-range VRAM coordinates, missing edge boundaries, malformed GP words, or invalid snapshot edge references. Report unmatched readbacks separately, not as retained pixels.

## Critical remaining integration work
**No claim that this initial JSONL analysis is a live emulator trace.** Before native v79 confirmation:
1. Attach nonmutating GP0/GP1 submission observers to pinned emulator source, retaining a global sequence shared with the VBlank hook.
2. Instrument actual native VRAM write paths (not postulated GP0 effects), with a bounded and opt-in trace; distinguish uploads from drawing writes.
3. Capture native GPU_freeze snapshots at the observed VBlank edges and relate them to logged writes.
4. Test ordering perturbations and dropped events in the pinned GCC/Clang PCSX job, and document the exact trace provenance.
5. Replay legally supplied original MAP02 privately; compare against original frames before considering HD replacement.

## Non-negotiable scope
`physical_ps1_vblank_verified=false`,
`retail_video_frame_correspondence_proven=false`,
`original_retail_MAP02_verified=false`,
`HD_replacement_approved=false`.

This branch is stacked on `feat/map02-v78-observed-vblank-vram-snapshots`; no production rendering switch is enabled.
