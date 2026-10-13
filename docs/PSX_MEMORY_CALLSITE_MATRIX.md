# PS1 memory call-site matrix

This matrix follows the fixed-address and scratch-buffer paths found in the pinned upstream PC-port revision `14552fffa0e0b47e02b57592e274fc6e7a649923`. It is a source audit only: no upstream code is copied here, and no engine integration or Switch runtime test is claimed.

## Call-site inventory

| Path in upstream | Observed use | Existing PC-port seam | Switch direction | Risk / open question |
|---|---|---|---|---|
| `src/core/cd.c` — `SOUND_WORK_PTR` and `gSoundSets` | Sound work buffers use guest addresses in the `0x8014xxxx` range. | Under `PC_PORT`, addresses are converted to offsets in `sPcSoundWorkRam`; the non-PC branch casts numeric addresses to pointers. | Preserve the logical guest offsets but give them explicit owned storage, ideally through one shared memory/backend interface. Keep audio backend replacement separate from storage translation. | Need establish the full sound-work span, all pointer consumers, alignment assumptions, and whether any code expects aliases or persistent contents. |
| `src/core/cd.c` — movie ring buffer near line 1279 | Non-PC branch uses guest pointer `0x801c74d0`; PC branch uses `gScratch3_80180210 + 291520` (`+0x472c0`). | The PC branch uses a host pointer into the data-segment scratch region. | Route through validated host-backed storage; do not cast the guest address on Horizon. | The buffer is within 2 MiB main RAM, but the declared `gScratch3` logical size is not itself proof of the correct Switch allocation or lifetime. |
| `src/units/load.c`, `src/core/main.c` | Unit data pointer is set to `gScratch3_80180210 + 0x2db80`, or `+0x3a300` for map 39. | Shared data-segment symbol with a documented logical size of `0x80000`. | Treat offsets as logical region offsets and check allocation size before exposing them through the memory helper. | `+0x3a300` is the highest documented named use in the data-segment note; the note says a smaller guess crashes real gameplay code, so avoid reducing capacity without full use analysis. |
| `src/core/cd.c` — sound-file table | Multiple CD sound entries target `gScratch3_80180210`. | Table entries point at a shared staging buffer. | Model as a reusable staging region only after confirming whether loads overlap or are consumed asynchronously. | File sizes and concurrent/queued audio behavior need inspection before assigning independent buffers or making it reentrant. |
| `src/world/dojo.c`, `src/core/screen_effects.c`, `src/states/game_setup.c` | TIM/image/map data is loaded or parsed from `gScratch3`; map data uses `mapNum * 1797`. | Existing shared staging buffer. | Keep a documented staging-buffer contract, or replace with explicit caller-owned buffers once lifetime is known. | Shared-buffer reuse may be intentional; changing it to per-call storage can alter pointer lifetime or increase memory use. |
| `src/maps/unpack.c` | Map decompression dictionary uses the full 1 KiB scratchpad at `0x1f800000`; indexes are masked by `0x3ff`. | Under `PC_PORT`, function uses static `sPcScratchpad[0x400]`. | Use explicit 1 KiB storage and keep the exact ring/dictionary behavior. A dedicated backend-owned scratchpad is preferable if more than one routine needs it. | Static storage is non-reentrant. Confirm the unpacker cannot be nested or called concurrently before changing ownership. |
| `src/core/graphics.c` | Graphics path also selects a 1 KiB scratchpad buffer. | Under `PC_PORT`, it has its own static `sPcScratchpad[0x400]`. | Keep separate scratch storage unless call-flow analysis proves safe sharing. | Do not combine the graphics and decompression scratchpads just because both are 1 KiB; simultaneous/lifetime assumptions are unverified. |
| `platform/pc/src/pc_bootstrap.c` | Desktop-only bootstrap reserves fixed guest RAM and scratchpad address ranges with OS virtual-memory APIs. | Linux/Windows exact-address mapping. | Exclude this bootstrap from the Switch target; Switch code should allocate storage normally and translate logical guest addresses. | Fixed mappings, OS-specific VM APIs, and null-mirror behavior do not transfer directly to Horizon. |
| `platform/pc/src/libcd.c` | Guest-address-shaped constants such as `0x80010000` and region-specific values are used to compute offsets into executable-image data. | Desktop CD/executable parsing. | Keep image-file offsets distinct from live guest pointers; don't feed every address-shaped literal through the RAM translator. | A lexical scan cannot determine semantics on its own; call-site intent must remain documented. |

## Important boundary arithmetic

- Main RAM modeled by the prototype is `[0x80000000, 0x80200000)` (2 MiB).
- `gScratch3_80180210` starts at `0x80180210`; its documented nominal size `0x80000` would end at `0x80200210`, which is `0x210` beyond the 2 MiB RAM window.
- The documented use up to `+0x3a300` and the movie ring offset `+0x472c0` both fit inside the RAM window. This does **not** prove that every access through the nominal `0x80000` region is a valid guest-RAM access.
- `gScratch1_801317c0` has documented nominal size `0x10000` and usage up to `+0xa000`; any mapping must be checked against the actual allocation and guest-address window too.

## Implementation order

1. Replace direct sound-work guest-pointer casts with a named storage abstraction, retaining the existing `PC_PORT` behavior while introducing a Switch path.
2. Define a precise staging-buffer contract for `gScratch3`: allocation size, maximum observed offset, file-load destination, and whether returned pointers escape the loading function.
3. Keep graphics and map-decompression scratchpads separate until reentrancy/call nesting is demonstrated.
4. Integrate the existing `psx_memory_translate` prototype only after call sites are converted to offsets or bounded spans; the helper alone cannot repair raw pointers already embedded in game code.
5. Add host tests for each new adapter and retain the current strict compiler flags.

## Evidence and limits

The inventory is based on upstream `src/core/cd.c`, `src/units/load.c`, `src/core/main.c`, `src/world/dojo.c`, `src/states/game_setup.c`, `src/core/screen_effects.c`, `src/maps/unpack.c`, `src/core/graphics.c`, `platform/pc/src/pc_bootstrap.c`, `platform/pc/src/libcd.c`, and upstream `docs/pc-port/data-segment.md` / `docs/pc-port/bootstrap.md`. Findings describe static source structure, not complete dynamic pointer-flow proof. The Switch diagnostic NROs do not contain the game engine, and this matrix does not establish game compatibility.
