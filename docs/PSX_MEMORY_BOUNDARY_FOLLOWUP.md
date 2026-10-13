# PS1 memory boundary follow-up: logical buffers versus guest RAM

Scope: static review of pinned upstream PC-port revision `14552fffa0e0b47e02b57592e274fc6e7a649923`. This document records a memory-model constraint before engine integration; it does not change upstream code or claim Switch runtime compatibility.

## Why the 2 MiB translator is not a drop-in replacement for every legacy pointer

The current host-tested `psx_memory_translate` prototype models only these guest ranges:

- Main RAM: `[0x80000000, 0x80200000)`, exactly 2 MiB.
- Scratchpad: `[0x1f800000, 0x1f800400)`, exactly 1 KiB.

That is a useful guest-address contract, but the PC port also represents some historical linker/data-segment objects as host allocations with logical sizes that do not exactly fit the nominal guest region.

### `gScratch3_80180210`

The upstream data-segment notes assign `gScratch3_80180210` a nominal size of `0x80000`, based on observed accesses up to `+0x3a300` and the report that a smaller guess breaks gameplay. Its symbol base is `0x80180210`.

- The nominal range ends at `0x80200210`, which is `0x210` beyond the modeled main-RAM end.
- Known offsets `+0x3a300` and `+0x472c0` (the movie ring buffer) remain within the 2 MiB window.
- The declared logical allocation size is therefore not proof that every byte in the full allocation corresponds to valid guest main RAM.

A Switch integration must not silently turn a rejected out-of-range guest access into an unchecked host pointer. First determine whether each access is truly a guest-address access, an access to a host-only logical data object, or a legacy overrun that must be represented deliberately.

### A related warning: `additional_VRAM`

The upstream data-segment notes document a `StoreImage` write at `additional_VRAM + 0x10380`, with dimensions 60 by 144, ending at offset `0x14700`—beyond the linker segment size `0x12970`. The PC port sizes the host object to the observed write ceiling because the original segment boundary was not the last byte touched. The notes report that on original hardware the write spills into adjacent memory, while in the PC build an undersized host allocation corrupted the next global.

This is not evidence that the write is safe to emulate by widening the whole guest RAM range. It demonstrates that guest segment boundaries, actual access extents, and host allocation boundaries are three different concepts and must be audited separately.

## Integration rules

1. **Keep strict guest translation strict.** A guest address and requested span must fit completely within a modeled guest region. Do not enlarge the 2 MiB main-RAM map solely to accommodate a symbol's host-side logical size.
2. **Track logical objects separately when needed.** If a legacy symbol needs a host allocation beyond its nominal guest range, give it an explicit object/buffer adapter with a documented size and call sites; do not pretend that its entire allocation is valid PS1 RAM.
3. **Audit actual access extents.** For each candidate buffer, record the base address, nominal size, maximum observed read/write end, alignment, and whether pointers escape the current call or loading state.
4. **Treat boundary-crossing accesses as unresolved, not automatically bugs or safe behavior.** The original program may rely on adjacent-memory effects. Confirm the exact object layout and observable behavior before deciding whether to reject, emulate, or intentionally isolate an overrun.
5. **Add focused tests before integration.** Test valid in-range spans, exact-end spans, one-byte-past-end spans, and any explicit logical-object adapter separately. A passing translator test alone does not establish that every upstream caller has been adapted.

## Evidence and limits

Evidence comes from upstream `docs/pc-port/data-segment.md` (size overrides for `gScratch3_80180210` and `additional_VRAM`), `src/core/cd.c` (movie ring buffer), and the local prototype `switch-memory/psx_memory.c`. This is static source/document review. It does not establish all runtime accesses, the complete original memory layout, or the behavior of a future Switch backend.
