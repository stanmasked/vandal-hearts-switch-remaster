# Scratchpad separation audit

This note records the scratchpad-specific findings from the pinned upstream PC-port revision `14552fffa0e0b47e02b57592e274fc6e7a649923`. It is a source audit and host-test note, not a claim that the game engine is integrated with the Switch backend.

## Confirmed uses

| Upstream site | PC-port storage | Access pattern observed | Porting constraint |
|---|---|---|---|
| `src/maps/unpack.c`, `UnpackMapFileData` | Function-local static `sPcScratchpad[0x400]` selected under `PC_PORT` (around lines 47–49) | Clears 990 bytes; ring writes increment `cacheOfs` and mask with `0x3ff`; cache reads also mask indexes with `0x3ff`. | Must provide at least 1 KiB and preserve the 10-bit ring behavior. Static storage means reentrancy/thread-safety is not established. |
| `src/core/graphics.c`, `Objf050_UnitSpritesDecoder` | A separate static `sPcScratchpad[0x400]` selected under `PC_PORT` (around lines 65–69) | Clears 958 bytes; incremental decoder state retains its cache offset across calls; reads and writes wrap with `0x3ff`. | Must provide at least 1 KiB for the decoder's lifetime. Its state persists across ticks, so replacing the buffer with short-lived storage would be incorrect. |

In the non-PC branches both routines cast the same numeric PS1 address, `0x1f800000`, to a pointer. In the PC-port branch they use distinct host arrays. These are two different implementation facts: the original target address indicates a shared physical scratchpad, while the current PC-port adaptation gives the routines independent storage. This audit does not prove that the two routines can overlap in time, nor that merging their PC-port arrays is behavior-preserving.

## Prototype implications

- `psx_memory_translate()` models scratchpad as a distinct 1 KiB region at `[0x1f800000, 0x1f800400)`, separate from the 2 MiB main RAM backing store.
- Host tests now explicitly verify that writes to the modeled main-RAM base and scratchpad base reach different backing arrays, while repeated translations of each address remain stable.
- Do not add separate “graphics” and “unpack” providers or merge the PC-port arrays into one buffer until the call graph and scheduler prove the necessary non-overlap/lifetime assumptions.
- If the Switch port intentionally follows original guest-memory semantics, both call sites should eventually resolve through one scratchpad backing region. If preserving current PC-port behavior is a requirement, the independent buffers need an explicit compatibility rationale. That decision is not made by this prototype.

## Evidence and limits

The observations above come from the two functions in the pinned upstream files `src/maps/unpack.c` and `src/core/graphics.c`. The source shows the ring-buffer index masks and decoder state retention, but this static inspection alone does not establish concurrent execution, nested calls, or all pointer lifetimes. The CI smoke-test NRO is diagnostic only and does not contain or run the game engine.
