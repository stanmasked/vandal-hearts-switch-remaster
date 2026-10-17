# MAP02 v108 — strict Unai store observations relative to VBlank callbacks

v108 is stacked after [v107](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/98). All v82-v107 private publication and rollback protections remain unchanged.

## Why this is useful

The pinned PCSX ReARMed synthetic fixture already logs four emulator VBlank callbacks, GP1 MMIO and DMA2 start inputs, dispatched Unai GP0 handlers, the immediately adjacent 24-point VRAM readback result, and two native 16-bit-store counters (all assignments and writes retaining the previous value). Previous independent validators checked these measurements, but did not publish **one conserved, per-VBlank ordinal summary** of all four different observation classes.

`summarize_map02_v108_vblank_store_buckets.py` now:

- Validates the entire private JSONL stream through existing v82/v83/v84/v85 auditors and requires all four original VBlank edges.
- Requires every Unai handler to retain an uninterrupted four-record native observation group.
- Assigns groups to one of five event **append-order** buckets: before first VBlank; between each consecutive pair; after the last VBlank.
- Separately counts changed vs unchanged sampled readbacks, total native store assignments, same-value assignments, changed-value assignments, GP1 MMIO input events, and DMA2 start events.
- Independently reconciles the resulting totals against the prior v82-v85 strict validators, with no invented GPU frame number or cycle for plugin calls.

The v104 full pinned GCC/Clang emulator workflow runs the new audit against the **already generated private** V104_RENDERER_EVENTS.jsonl, checks totals against its previously verified native run, and only writes a sanitized aggregate JSON summary into the public artifact directory. Source opcode words, addresses, VRAM pixel colors, synthetic EXE and private event journals are never uploaded.

## Regression coverage and boundaries

The new GCC/Clang suite covers every bucket including pre-first/post-last, DMA2 inputs that are not confused with Unai stores, malformed store groups, forged GPU timestamps/readback values, and per-interval conservation. Older Unai v83/v84/v85 tests remain mandatory.

The bucket assignment describes only **order of native callbacks in one host process**; it does *not* identify exactly when commands finished in emulated CPU cycles or physical GPU raster scanlines. No real Vandal Hearts retail MAP02 image has been exercised here, no physical PlayStation VBlank validation is claimed, and Nintendo Switch HD graphics equivalence is unverified.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The changes are isolated in a Draft PR; `main` remains unchanged.
