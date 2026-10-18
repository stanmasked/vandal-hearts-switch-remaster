# MAP02 v154 — third source-authored MIPS instruction changed between dispatches

This test extends [v153 Draft PR #150](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/150). It uses only the self-authored 8192-byte v129 synthetic PlayStation guest program, not an original game executable.

The pinned PCSX interpreter `execI_` and `execIbp` already have a pre-opcode fetched-word source witness. Under the strictly opt-in `--vh154-mutate-third-word` CLI, together with `--vh129-vblank-04 --vh150-bounded-instructions`, the original 8192-byte synthetic guest RAM is first verified by SHA-256 (v151). The native witness then accepts and dispatches the first **two** expected instructions. After accepting the second source-authored opcode, it deliberately changes a byte of the **third** guest instruction at PS1 RAM offset `0x10008`. The third native fetch must be refused before dispatch, leaving exactly two accepted instructions.

The test must exit 58 with the specific marker `VH154_NATIVE_THIRD_WORD_REFUSED matched=2 attempted=3 original_retail=0`. Invalid profile combinations and simultaneous v152/v153 mutation switches are rejected. A failed check also exits 58 but with a **different** marker; CI requires the exact success-of-refusal marker so accidental error cannot count as a pass.

The independent GCC/Clang compiled C witness checks two accepted opcodes, mutated third-word refusal and a latched denial for further dispatch. The full native PCSX ReARMed/Unai workflow exercises the same guest-memory corruption with the actual pinned interpreter, validates the source EXE did not change and retains previous synthetic GPU/DMA/VBlank/MMIO checks. Only aggregate sanitized status may be published.

**Limits:** This intentionally validates the three-instruction synthetic test boundary. It does not execute the retail PlayStation game, authenticate its original resources, prove BIOS/CD accuracy, demonstrate an original MAP02 battle or establish Nintendo Switch HD image parity. The interpreter instrumentation is not a general OS sandbox. The PR stays Draft until the native and compiled regression matrices complete.
