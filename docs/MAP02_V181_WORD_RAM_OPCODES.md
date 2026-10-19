# MAP02 v181 — true aligned MIPS LW/SW RAM provenance

Builds on fully green [MAP02 v180 PR #208](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/208), 73/73 GitHub Actions. v180 proved eight byte/halfword and unaligned synthetic MIPS accesses were actually executed according to live interpreter PC, opcode and data address. v181 extends the same protection to ordinary aligned 32-bit MIPS LW and SW instructions through actual PCSX `psxMemRead32` and `psxMemWrite32` callbacks.

Four source-authored private PS-X EXE variants each change only one wait NOP: LW $zero,0($zero), LW $zero,4($zero), SW $zero,0($zero), SW $zero,4($zero). Each native GCC/Clang run must observe an exact instruction word and address inside all four genuine emulator-internal VBlank wait windows, while retaining 2380 native Unai pixel samples and existing GPU-register sentinels. The unchanged VH78SYN! EXE must exit 84 with `VH181_NATIVE_WORD_UNOBSERVED_REFUSED`, never falsely claiming instruction execution.

Independent C99 GCC/Clang tests exercise real read32/write32 accessors, all four operation and address combinations, and rejection of a forged opcode. The observer is passive: it changes no MIPS registers, guest memory, GPU data, VBlank timers, or Unai pixels. No retail Vandal Hearts MAP02 game code or physical Nintendo Switch output is claimed.
