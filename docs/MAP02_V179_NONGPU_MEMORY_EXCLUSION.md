# MAP02 v179 — native negative controls for non-GPU memory

This stage builds on fully green v178 (PR #203, 71/71 Actions). Earlier v173–v178 tests proved guest MIPS GPU-register reads and writes must be refused during the four genuine PCSX internal VBlank waits. v179 checks the complementary property: unrelated guest MIPS memory operations must **not** be misclassified as GP0/GP1 accesses.

Eight separately generated self-authored VH78SYN! EXEs each differ in exactly one original 512-NOP wait-pad instruction. Four read paths target 0x1f80180f, 0x1f80180c, or 0x1f801818, adjacent to but outside GP0 0x1f801810–813 and GP1 0x1f801814–817: LB zero,-1(t0), LHU zero,8(t0), LWL zero,-1(t0), LWR zero,8(t0). Four writes target independent ordinary guest RAM bytes 0–2, not MMIO: SB zero,0(zero), SH zero,2(zero), SWL zero,2(zero), SWR zero,1(zero). The zero destination or source avoids perturbing the synthetic rendering source registers. Mutant files remain private, chmod 0600, never overwritten.

Native GCC and Clang must run each variant through the existing --vh176-mips-vblank-narrow-mmio oracle and require all four real emulator-internal VBlank edges, the v172 GPU source attestations, v175 32-bit read silence, v176 8/16-bit memory silence, and 2380 native Unai pixel samples. No false GPU refusal is permitted. Separate independent regressions validate mutation isolation, exact MIPS encodings, and no-overwrite behavior.

This is only synthetic in-emulator MIPS behavior. No original retail Vandal Hearts MAP02 gameplay, physical PlayStation or Nintendo Switch graphics output, or complete port is claimed.
