# MAP02 v155 — four native source-authored MIPS instructions

Stacked on [v154 Draft PR #152](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/152). This experimental stage extends the **synthetic-only** native PCSX ReARMed interpreted CPU test from three instructions to **four**, while retaining the original three-step behavior with no new CLI option.

## Exact test boundary

The four MIPS opcodes are computed from the pinned repository-authored `make_map02_v129_four_vblank_exe.build()` output, and only straight-line nonbranching opcodes are admitted. The 8192 bytes actually loaded into emulated PS1 RAM must first pass the v151 SHA-256 check.

A new `--vh155-four-instructions` option, accepted **only** together with `--vh129-vblank-04 --vh150-bounded-instructions`, arms a four-step quota and unlocks one additional expected opcode in the v152 native instruction witness. Under normal conditions, the actual native interpreter should match and dispatch exactly four instruction words, then refuse step five before its cycles, fetch, or opcode effects.

The separate `--vh155-mutate-fourth-word` option must be combined with the four-step option. It causes the already instrumented native witness to flip one byte of emulated PS1 RAM immediately after accepting the first three source-authored words; when the fourth MIPS word is fetched, the exact source+RAM check must reject it before dispatch with `VH155_NATIVE_FOURTH_WORD_REFUSED matched=3 attempted=4 original_retail=0` (status 59). Invalid or mixed diagnostic flags, including all legacy mutation modes, are rejected.

## Regressions and evidence

An independent compiled C harness in GCC and Clang verifies (a) the original three-word limit is preserved, (b) four original words are accepted followed by rejection of the fifth by the native quota, and (c) a changed fourth word is rejected before dispatch, with the fault latched. The pinned PCSX/Unai GCC and Clang workflow runs the same tests on the actual upstream emulator and retains the earlier synthetic VBlank, DMA, MMIO and source-integrity tests.

Do not treat this as retail PS1 execution or playable MAP02. It does **not** demonstrate a complete MIPS ISA, original BIOS/CD runtime behavior, Nintendo Switch HD graphics parity or process-level isolation. Original game resources remain private and never enter GitHub or its public CI. Keep the PR in Draft pending full native verification.
