# Direct guest-pointer migration audit

This note narrows the broader memory call-site matrix to code that forms pointers directly from PS1 numeric addresses. It is based on the pinned upstream revision `14552fffa0e0b47e02b57592e274fc6e7a649923` and is static analysis only.

## Confirmed direct-address cases

| Upstream site | Direct pointer behavior | Safe migration direction | What must not be assumed |
|---|---|---|---|
| `src/core/cd.c` — `SOUND_WORK_PTR` outside `PC_PORT` | Sound-set entries cast guest addresses such as `0x80140878`, `0x80141878`, and `0x80144878` to pointers. | Translate each guest span against one shared main-RAM backing store, or refactor to an explicit RAM offset abstraction. | A separate host allocation per sound set would break guest-address aliasing; set 2 variants deliberately share an address. |
| `src/maps/unpack.c` — `pCache` | The US tree's non-PC branch casts `0x1f800000` to a pointer and uses the full 1 KiB scratchpad ring. The US `PC_PORT` branch uses a static 1 KiB host buffer. | Route through a dedicated 1 KiB scratchpad owned by the platform/memory context, or retain a narrowly scoped buffer seam. | The PC static buffer does not establish that graphics may share the same scratchpad; their PC branch has a separate static buffer. |
| `src/core/graphics.c` — `pCache` | The non-PC branch also casts `0x1f800000`; the PC branch uses a different static 1 KiB buffer. | Keep this storage distinct until call nesting, reentrancy, and lifetime are proven. | Equal guest addresses in the original executable do not automatically mean the current PC backend's two host arrays are aliased. |
| `src/core/cd.c` — movie ring buffer | The non-PC path uses guest address `0x801c74d0`; PC uses `gScratch3_80180210 + 0x472c0`. | Translate the guest span or use an explicit offset into shared RAM; validate the requested length, not just the first byte. | The starting address fitting in RAM does not prove every future frame/ring access is bounded. |
| `platform/pc/src/pc_bootstrap.c` | Desktop bootstrap reserves fixed virtual address ranges with OS APIs. | Exclude the desktop bootstrap from the Horizon target; allocate buffers normally and translate guest addresses. | Fixed mappings and OS virtual-memory calls are not a portable Switch memory model. |

The upstream project's own [memory-safety notes](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/docs/memory-safety.md) explicitly identify hard-coded RAM pointers as a host-port hazard. The upstream [bootstrap notes](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/docs/pc-port/bootstrap.md) distinguish the 2 MiB RAM mapping from the 1 KiB scratchpad and note the US unpacker host-buffer seam.

## Migration rules

1. **Never cast a guest address to a native pointer on Horizon.** A numeric PS1 address is data to translate, not a valid Switch address.
2. **Translate full spans.** Callers must supply the access length where known; a successful one-byte translation does not authorize a larger read/write.
3. **Preserve aliasing deliberately.** Guest addresses in the same PS1 RAM region must resolve into the same backing allocation, so overlapping spans see each other's writes.
4. **Keep RAM and scratchpad separate.** They are distinct guest regions. A future abstraction should make the region choice explicit and reject MMIO/unsupported aliases until they are intentionally implemented.
5. **Do not silently clamp legacy logical buffers.** `gScratch3_80180210` has a documented nominal size that extends `0x210` past the modeled RAM window. The strict translator correctly rejects out-of-window spans; each actual call site must be audited before deciding whether a host-side logical buffer is separate from guest RAM.
6. **Keep platform seams narrow.** The existing prototype is intentionally a translator and not yet wired into the game. Integrate one call-site family at a time, with tests for boundaries, aliasing, and lifetime.

## Suggested order

1. **Prototype added:** `psx_sound_work_translate()` bounds a requested span to the legacy `[0x80140000, 0x80200000)` sound-work window, then resolves it through the shared main-RAM translator. Host tests cover the window start/end, rejected out-of-window spans, and pointer identity/aliasing. This is not wired into upstream game code yet.
2. Introduce a scratchpad provider for unpacking, with a separate provider for graphics until non-overlap is demonstrated.
3. Audit the movie ring buffer's maximum access span and lifetime.
4. Only then consider a common guest-memory context passed through engine subsystems.

No Switch engine integration or on-device game test is claimed by this document.
