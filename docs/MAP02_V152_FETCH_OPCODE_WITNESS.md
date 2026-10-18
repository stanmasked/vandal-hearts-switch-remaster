# MAP02 v152 — verify fetched synthetic MIPS words immediately before dispatch

This experimental stage stacks on [v151 Draft PR #147](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/147), with the original game data kept private and **no retail PS1 execution enabled**.

The native PCSX interpreter is now instrumented at **both** `execI_` and `execIbp` to verify the actual fetched MIPS opcode and corresponding guest RAM bytes just before the opcode dispatcher is called. Only the first three source-authored v129 synthetic MIPS instruction words are accepted, and only when the opt-in v150 instruction budget is active. Word expectations are generated directly from the v129 fixture during source patching, not from private game resources.

## Positive and deliberately changed-RAM tests

The existing v151 SHA-256 of the full 8192-byte loaded synthetic payload must succeed first. The v152 witness then arms before native MIPS execution. On an untouched v129 fixture, exactly three fetched words are matched in sequence; the v150 quota must stop the following instruction.

The new explicit flag `--vh152-mutate-post-verify` is valid **only** with `--vh129-vblank-04 --vh150-bounded-instructions`. Immediately after the successful v151 payload SHA-256 check and before native MIPS fetch, it flips a byte of guest RAM at physical offset `0x10000`. The first fetched instruction must be refused **before guest opcode dispatch**, with no matched instructions, exit code 56, and `VH152_NATIVE_FETCH_TAMPER_REFUSED matched=0 original_retail=0`. An attempt to use the mutation flag without the correct synthetic mode also refuses.

The independent C witness compiled under GCC and Clang tests the legitimate first three words, alteration of guest RAM with unchanged fetched opcode, alteration of the fetched opcode with intact RAM, and latching after a rejection. The full pinned native PCSX matrix verifies the real host emulator's refusal while retaining previous v129 VBlank/Unai/DMA/MMIO and v150-v151 native tests.

## Limits

This is **not** a general emulator integrity framework, native retail boot authorization, full instruction-code attestation, process sandbox, BIOS/CD fidelity demonstration, MAP02 gameplay proof or Switch HD renderer certification. It adds source-authored **synthetic** pre-dispatch evidence for three instructions only. In normal execution, with the v150 test mode off, no v152 witness is armed.

Keep the draft review open until both the independent compiled checks and real pinned PCSX native GCC/Clang executions pass. Neither user-owned game files nor raw gameplay assets are added to the public repository.
