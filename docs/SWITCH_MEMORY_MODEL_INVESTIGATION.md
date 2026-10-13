# Memory-model investigation for the Switch backend

Status: source-level investigation; no game code has been ported in this step.

## What the pinned upstream code actually assumes

The PC bootstrap is intentionally a desktop startup shim. In `platform/pc/src/pc_bootstrap.c`, it reserves:

- `0x80000000` for 2 MiB of writable PS1 main RAM.
- `0x1f800000` for 1 KiB of PS1 scratchpad RAM.

The Linux path uses `mmap(... MAP_FIXED_NOREPLACE ...)`; the Windows path uses `VirtualAlloc` and requires the exact returned address. The file also includes platform-specific executable-path inspection and, on some desktop targets, fault-handling code. These assumptions cannot be carried into a Switch target unchanged.

Two concrete examples in the pinned source make the issue visible:

- `src/core/cd.c` initializes `gSoundSets` with `SOUND_WORK_PTR(0x80140878)`. The nearby comment says these used to be anonymous fixed PS1-RAM addresses; the PC port has already added host-backed handling for this specific structure.
- `src/maps/unpack.c` sets `pCache = (u8 *)0x1f800000` and uses it as a 1 KiB dictionary indexed by `cacheOfs & 0x3ff`. This is a direct scratchpad pointer, not an ordinary allocated host buffer.

These are examples, not a complete inventory of all absolute addresses. The CI scanner currently reports 5 matches for fixed-address patterns, but a pattern count is not a complete semantic analysis of every pointer derived from PS1 addresses.

## Design decision to resolve before integrating the engine

Do not try to reserve those desktop addresses on Horizon. The port needs an explicit representation for emulated PS1 memory, and all remaining hard-coded pointers must be traced before selecting a strategy.

### Candidate approaches

1. **Targeted source-level conversion.** Replace each remaining literal address with an offset into a suitably aligned allocated RAM/scratchpad region. This is relatively simple for isolated scratch buffers, but unsafe if game code expects arbitrary PS1 pointers to behave as native C pointers.
2. **Central PSX address translation.** Represent PS1 addresses as 32-bit guest addresses and translate them through helpers into host pointers. This is more systematic, but requires auditing pointer arithmetic, casts, stored pointers, callbacks, and data tables across the decompiled code.
3. **Reserved virtual region, if supported.** Consider only if the target OS and toolchain explicitly guarantee the needed mapping semantics. Do not assume desktop `mmap` or `VirtualAlloc` behavior exists on Switch; this option is not the default plan.

A mixed solution may be needed because existing PC_PORT adaptations already handle some regions differently. Preserve the matching/decompiled game logic where possible and document each intentional divergence.

## Next technical work

1. **Added:** `scripts/audit_psx_memory_literals.py` now scans upstream `src/`, `platform/pc/src/`, and `platform/pc/include/` for literal patterns in PS1 main-RAM, scratchpad, I/O-register, and NULL-mirror address ranges. CI runs it against the pinned source and includes `psx-memory-literal-inventory.txt` in the downloadable artifact.
2. Review each hit and classify it as a direct dereference, offset arithmetic, address passed to a subsystem, stored guest pointer, or documentation/comment-only occurrence. The script deliberately includes comments and inactive preprocessor branches to avoid silently dropping leads.
3. Expand beyond literals to address construction and pointer-flow patterns; a simple regex cannot prove the inventory is complete.
4. Identify whether a narrow memory helper can cover each category without changing observable game behavior.
5. Add unit tests for guest-address translation and boundary cases before attempting a Switch engine link.
6. Only after this inventory is reviewed, introduce a Switch-only memory module and exclude the desktop bootstrap from the target build.

## Validation gate

A Switch build should not be called bootable until the engine can initialize memory without desktop VM APIs and passes tests for main RAM bounds, scratchpad bounds, pointer conversion, and all known hard-coded address sites. A successful NRO build alone is not sufficient.
