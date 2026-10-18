# MAP02 v153 — second guest instruction changed between native dispatches

This diagnostic stage stacks on v152 Draft PR #149. Source-authored synthetic MIPS is the **only** guest input permitted; original PS1 binaries, BIOS/CD and MAP02 gameplay remain unexecuted.

The v152 fetched-opcode validator is now extended with an opt-in `--vh153-mutate-second-word` mode. After the v151 SHA-256 check of the original 8192-byte synthetic guest RAM and after the **first** MIPS word has matched the source witness, the native observer deliberately flips a byte in the **second** guest instruction at RAM offset `0x10004`. The first instruction still dispatches normally. On the next interpreter fetch, v152 must refuse the changed second word **before dispatch**.

The only permitted option combination is `--vh129-vblank-04 --vh150-bounded-instructions --vh153-mutate-second-word`. Other profiles or combination with the older `--vh152-mutate-post-verify` mode are rejected (exit 57). A passing negative witness emits `VH153_NATIVE_SECOND_WORD_REFUSED matched=1 attempted=2 original_retail=0` and also exits with 57, so callers must verify the exact message and count, not merely the exit status.

Compiled GCC/Clang C tests assert exactly one accepted word and a latched refusal of second and subsequent dispatches. The actual pinned native PCSX ReARMed/Unai workflow executes the same synthetic-only scenario, checks that the on-disk EXE is unchanged, verifies exit/message evidence, then runs all prior VBlank/Unai/DMA and MMIO modes without modifications. No source-game data or low-level private gameplay traces are uploaded.

**Evidence limit:** this is a deliberately induced mutation between two source-authored synthetic instructions. It does not authenticate or execute the original game, prove a security sandbox, or establish original MAP02 rendering and Switch HD parity. Keep PR Draft and `main` untouched until both compiled and real native emulator CI matrices pass.
