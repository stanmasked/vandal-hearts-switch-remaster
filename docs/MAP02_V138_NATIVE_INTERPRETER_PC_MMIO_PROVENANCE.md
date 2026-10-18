# MAP02 v138 — real PCSX interpreted MIPS SW program-counter witness

This stage is stacked on [v137 Draft PR #128](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/128), confirmed **31/31 GitHub Actions green**. All runtime evidence in this stage is produced by a source-authored **synthetic** PS-X executable, not by a retail Vandal Hearts game.

## Source instrumentation at real CPU memory-store execution

The pinned PCSX ReARMed version is `notaz/pcsx_rearmed` commit `8b6c163575e6ce9a0537553e0d4ed4225315955e`.

Its actual `libpcsxcore/psxinterpreter.c` executes each fetched instruction by incrementing `regs->pc` by 4 **before** decoding and executing the current `regs->code`. The `SW` instruction invokes `psxMemWrite32(regs, destination, value)`. A temporary, opt-in native hook in `libpcsxcore/psxmem.c` therefore observes `regs->pc-4` when a real MIPS store reaches the GPU or DMA memory-mapped register classes.

The new native hook:

- Is active only after signed source-authored v129 PS-X EXE identity and interpreter readiness checks have passed, and only under the new `--vh138-interpreter-pc` opt-in flag.
- Captures the real current interpreter instruction opcode (`regs->code >> 26 == 0x2b`), `regs->pc-4` and the physical destination MMIO register class before dispatching the ordinary memory write.
- Compares **every** observed MMIO `SW` in order with an independent expected PC / register-class table compiled from the unchanged v129 generated MIPS program using the v132 static decoder. An extra, missing, aliased, wrong-PC, wrong-class or out-of-order store fails the process.
- Does not change `psxRegs.pc`, emulated DMA memory, GPU packets, MIPS cycles, VBlank counters or Unai state.
- Prints **only one aggregate success or refusal** status; it never prints instruction PCs, opcode values, source code or raw GPU words.
- Preserves all five original `--vh129-vblank-04/13/22/31/40` scenarios unchanged when the new flag is not set.

The optional `--vh138-corrupt-pc-witness` deliberately corrupts **only the private observer's integrity flag**, never MIPS or GPU state. The same actual native executable must then refuse with a distinct `VH138_NATIVE_MIPS_PC_REFUSED` marker. This proves the matcher is not merely a decorative PASS string.

## Independent compiled host tests and actual emulator execution

Standalone GCC and Clang workflows compile a small source-derived C11 witness using bounds/undefined-behavior sanitizers. The C regression requires one positive ordered sequence and refuses an altered instruction PC, wrong register class, non-SW opcode and forced witness corruption.

The complete pinned GCC/Clang PCSX native workflow uses the unchanged synthetic MIPS EXE and genuine Unai software renderer:

1. Execute the existing five real-VBlank profiles, verifying their original DMA2/Unai evidence and private EXE SHA-256.
2. Start a separate **sixth interpreter process** with `--vh129-vblank-04 --vh138-interpreter-pc`, require both `VH138_NATIVE_INTERPRETER_PC_PASS` and the original `VH129_REAL_VBLANK_PROFILES_PASS` status.
3. Start a seventh process with `--vh138-corrupt-pc-witness`; require exit code 48 and the specific sanitized witness refusal rather than a false success.

These extra processes use no user-owned retail game resources, no hidden game executable and no fake CPU, VBlank or GPU events.

### Exact scope

This authenticates source-authored **synthetic** MMIO store-PC observations originating in an actual PCSX MIPS interpreter execution. It provides a working capture primitive for subsequent private retail research, but it does **not** authenticate captured original-game instructions, confirm a retail MAP02 encounter, or establish PS1/HD Switch graphics parity.

- `original_retail_mips_executed`: false
- `retail_map02_graphics_captured`: false
- `physical_playstation_equivalence`: false
- `nintendo_switch_hd_parity`: false
