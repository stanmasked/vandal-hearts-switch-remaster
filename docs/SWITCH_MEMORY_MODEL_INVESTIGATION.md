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

These are examples, not a complete inventory of all absolute addresses. The CI literal scanner has run against the pinned upstream snapshot (156 C/C++ source files). The raw inventory reports 3,321 main-RAM-shaped occurrences, 3 scratchpad occurrences, 0 I/O-register-range occurrences, and 2 zero/NULL-mirror occurrences. A lexical pass separates ordinary code from comments and quoted strings: main RAM is 18 code-shaped occurrences plus 3,303 comment/string occurrences; scratchpad is 2 code-shaped plus 1 comment/string; the 2 zero/NULL-mirror occurrences are comment/string-only. These are *occurrences*, not unique addresses or confirmed runtime accesses. Inactive preprocessor branches are still included, so even a code-shaped occurrence is only a review lead, not proof of a runtime dereference. The downloadable CI artifact contains the full per-file/per-line inventory.

## Design decision to resolve before integrating the engine

Do not try to reserve those desktop addresses on Horizon. The port needs an explicit representation for emulated PS1 memory, and all remaining hard-coded pointers must be traced before selecting a strategy.

### Candidate approaches

1. **Targeted source-level conversion.** Replace each remaining literal address with an offset into a suitably aligned allocated RAM/scratchpad region. This is relatively simple for isolated scratch buffers, but unsafe if game code expects arbitrary PS1 pointers to behave as native C pointers.
2. **Central PSX address translation.** Represent PS1 addresses as 32-bit guest addresses and translate them through helpers into host pointers. This is more systematic, but requires auditing pointer arithmetic, casts, stored pointers, callbacks, and data tables across the decompiled code.
3. **Reserved virtual region, if supported.** Consider only if the target OS and toolchain explicitly guarantee the needed mapping semantics. Do not assume desktop `mmap` or `VirtualAlloc` behavior exists on Switch; this option is not the default plan.

A mixed solution may be needed because existing PC_PORT adaptations already handle some regions differently. Preserve the matching/decompiled game logic where possible and document each intentional divergence.

## Next technical work

1. **Completed:** `scripts/audit_psx_memory_literals.py` scans upstream `src/`, `platform/pc/src/`, and `platform/pc/include/`; CI runs it, tests the code/comment classifier, and uploads `psx-memory-literal-inventory.txt`.
2. **Next:** inspect the 20 code-shaped hits (18 main-RAM, 2 scratchpad) in context and distinguish active code from inactive `#if` branches. Then classify pointer casts/dereferences, arithmetic from a guest base, and values passed to memory-sensitive subsystems.
3. Expand beyond literals to address construction and pointer-flow patterns; a simple regex cannot prove the inventory is complete.
4. Identify whether a narrow memory helper can cover each category without changing observable game behavior.
5. Add unit tests for guest-address translation and boundary cases before attempting a Switch engine link.
6. Only after this inventory is reviewed, introduce a Switch-only memory module and exclude the desktop bootstrap from the target build.

## Validation gate

A Switch build should not be called bootable until the engine can initialize memory without desktop VM APIs and passes tests for main RAM bounds, scratchpad bounds, pointer conversion, and all known hard-coded address sites. A successful NRO build alone is not sufficient.
