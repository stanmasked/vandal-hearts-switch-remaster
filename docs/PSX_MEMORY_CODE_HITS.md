# PS1 address literals: code-shaped hit triage

This is a source-level triage of the code-shaped rows in the CI literal inventory for pinned upstream commit \`14552fffa0e0b47e02b57592e274fc6e7a649923\`. It does not modify or copy upstream source. “Code-shaped” means the address text is outside ordinary comments and quoted string/character literals; inactive preprocessor branches are still included.

## Main-RAM-shaped hits

| Location | What the literal is doing | Switch-port implication |
|---|---|---|
| \`platform/pc/src/libcd.c:158\` | \`VH_EXE_LOAD_VRAM = 0x80010000\`, a guest executable load-address constant used to derive an offset inside a disc image. | Not a host pointer dereference. Keep the disc-image offset arithmetic conceptually separate from guest RAM allocation. |
| \`platform/pc/src/libcd.c:172,176\` | \`0x800f5551\` and \`0x800f76a9\` are region-specific addresses used by \`CardIdAt\` to calculate the memory-card ID's location in the executable image. | These are input offsets for disc metadata, not addresses to dereference in Switch process memory. The lexical scanner correctly flags them but cannot infer their meaning. |
| \`src/core/cd.c:66-82\` | \`SOUND_WORK_PTR\` and its table entries use the PS1 address family \`0x8014xxxx\`. Under \`PC_PORT\`, the macro translates these to offsets inside \`sPcSoundWorkRam\`; otherwise it casts the guest address to a pointer. | This is an existing compatibility seam. A Switch backend should provide equivalent host-backed storage through a Switch-specific guard or a shared memory helper; it should not inherit the raw-pointer fallback. Repeated table entries account for most code-shaped hits. |
| \`src/core/cd.c:1279\` | Non-\`PC_PORT\` branch assigns \`ringBufAddr = (void *)0x801c74d0\`; the \`PC_PORT\` branch instead uses \`&gScratch3_80180210[291520]\`. | High-priority follow-up: trace the declared size and lifetime of \`gScratch3_80180210\`, then reuse a validated host-backed buffer or add a narrowly scoped Switch mapping. Do not simply cast this address on Horizon. |

## Scratchpad hits

| Location | Existing behavior | Switch-port implication |
|---|---|---|
| \`src/maps/unpack.c:49\` | The non-\`PC_PORT\` branch assigns \`pCache = (u8 *)0x1f800000\` for a 1 KiB dictionary. The \`PC_PORT\` branch uses a static \`sPcScratchpad[0x400]\`. | Use an explicit Switch-owned 1 KiB scratchpad buffer or a common helper. Verify reentrancy and lifetime before changing storage semantics. |
| \`platform/pc/src/pc_bootstrap.c:48\` (not in scanner scope's PC source? see note) | Documents the fixed PS1 scratchpad base used by the desktop bootstrap. | Desktop bootstrap must not be part of the Switch target; this comment/definition is an architectural reference, not a reason to reserve the same address on Horizon. |

## Priority order

1. Trace \`gScratch3_80180210\` and the movie ring-buffer path; this is the most obvious remaining fixed pointer in an engine source path.
2. Add a Switch-specific storage path for \`SOUND_WORK_PTR\` and the map-unpack scratchpad without forcing desktop SDL/window/audio dependencies into the target.
3. Keep the \`libcd.c\` image-offset constants categorized as file-format offsets unless a separate call-site analysis proves they are used as live pointers.
4. Extend analysis to computed guest addresses and pointer flow. This list is only the literal-shaped subset.

## Limits

The scanner scans \`src/\`, \`platform/pc/src/\`, and \`platform/pc/include/\`; the bootstrap file is included in the separate blocker audit but not the memory-literal scanner's source roots, so the \`pc_bootstrap.c\` note above is contextual and not one of the reported 20 code-shaped rows. Inactive \`#if\` branches remain included. No runtime execution, Switch build of the game engine, or real-hardware test was performed.
