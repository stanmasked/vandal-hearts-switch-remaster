# MAP02 v180 — true non-GPU MIPS opcode execution provenance

This stage builds upon the fully verified MAP02 v179 (72/72 GitHub Actions). v179 confirmed that eight signed self-authored synthetic guest MIPS variants retain four emulator-internal VBlank events and 2380 native Unai pixel samples without a false GPU-register refusal. However, rendering success alone cannot prove that each inserted instruction actually executed.

v180 adds a passive read/write witness in the real PCSX `psxMemRead8`, `psxMemRead16`, `psxMemRead32`, `psxMemWrite8` and `psxMemWrite16` functions. It checks the live interpreter register PC, the actual instruction word `regs->code`, the exact expected data-memory address and read/write width while the original VBlank observer is armed. Every v179 synthetic variant must be observed in every one of the four VBlank wait intervals. Compound SWL and SWR operations require both their 8-bit and 16-bit write callbacks in equal numbers.

The positive marker `VH180_NONGPU_GUEST_OPCODE_EXECUTED_PASS` requires all four per-variant observed windows, clean GPU-register sentinels, and the inherited 2380 native Unai samples. A negative control runs the unmodified source-authored v78 program with the new witness flag; it must return code 83 with `VH180_GUEST_OPCODE_UNOBSERVED_REFUSED`, even if it would render the same pixels.

Independent GCC/Clang C fixture tests check all eight access patterns and ensure a mismatched opcode is never counted. No CPU registers, GPU state, VBlank schedule or original retail assets are modified by the observer. The proof concerns synthetic guest MIPS within PCSX ReARMed, not original retail MAP02 execution or physical Nintendo Switch output.
