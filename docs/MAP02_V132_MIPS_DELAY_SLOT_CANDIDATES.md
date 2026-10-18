# MAP02 v132 — conservative MIPS-I branch delay-slot GPU/DMA inventory

Stacked on [v131 Draft PR #122](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/122). All 25 workflows of v131 completed successfully, but that private static scanner intentionally used an incomplete model of original PS1 MIPS control flow.

## Why a real hardware instruction detail matters

On the PlayStation R3000A MIPS-I CPU, a branch or jump has a **delay slot**. The instruction immediately following the branch executes **before** the change of program counter (the PlayStation R3000A runs MIPS I; later MIPS II branch-likely opcodes are reserved, not valid branch instructions on this hardware). The original v131 conservative linear pass reset its register constants immediately upon seeing the branch opcode. It therefore could miss a statically provable candidate store into the DMA2 CHCR register located in the delay slot.

The new `tools/analyze_map02_v132_mips_delay_slots.py` preserves known register values for precisely **one** following instruction, then clears inferred state. It separately counts:

- control-flow delay slots examined;
- candidate GPU/DMA `SW` instructions inside delay slots;
- occurrences of reserved MIPS II branch-likely opcodes, which must **never** credit a subsequent GPU/DMA write on the PS1;
- ambiguous nested control instructions in delay slots (no inferred MMIO values).

It also invalidates a JAL/JALR link destination before the delay-slot instruction reads it. A code section ending with an incomplete delay slot refuses analysis rather than pretending a complete MIPS program was examined. Unknown operations, loads and jumps continue to invalidate speculative constants.

### Positive and negative proof fixtures

1. Confirm a statically provable `SW` after an original MIPS `j` while v131 missed it.
2. Confirm normal MIPS I branch slots are counted while MIPS II branch-likely opcodes are treated as unsupported (including REGIMM and coprocessor variants).
3. Prove known constants cannot propagate after a branch's slot.
4. Prove load clobbers and JALR link-register writes invalidate stale MMIO addresses.
5. Treat branches embedded inside another delay slot as ambiguous, with no guessed MMIO instruction site.
6. Reject missing delay-slot instructions or malformed MIPS text.
7. Re-examine the exact source-authored v129 EXE and require unchanged candidate counts (3 DMA2 MADR, 3 BCR, 6 CHCR, 3 literal linked-list CHCR writes, and GP0 sites).

Both standalone GCC/Clang workflow jobs and full pinned emulator workflows execute the test suite. The latter binds the v131 and v132 *static scans of the exact same 0600 synthetic EXE* to five independent actual PCSX MIPS/VBlank/GPU DMA processes using private SHA-256 before and after each.

## No retail or emulator parity claim

The scanner remains a conservative **linear static candidate** inventory, not a control-flow graph, full CPU emulator, source provenance proof, retail MAP02 runtime trace, texture or VRAM comparison or Nintendo Switch implementation. User-owned inputs remain local and unmodified. The tool never prints game bytes, file paths or hashes.

- original_retail_MAP02_verified: false
- physical_PS1_verified: false
- HD_replacement_approved: false

Reference: the [R3000 family manual](https://student.cs.uwaterloo.ca/~cs350/common/r3000-manual.pdf) identifies R3000 as MIPS I and branch-likely as an addition of MIPS II. The [PS1 R3000A instruction overview](https://archives.somnolescent.net/web/cammy_v1/games/everything_psx/r3000a.html) describes the standard one-instruction branch delay.
