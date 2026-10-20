# MAP02 v196 — independently execute PS1 MIPS-I guest RAM dataflow

Base: v195 Draft PR #233. The v195 literal nine-instruction oracle ensures the 10240-byte synthetic guest PS-X EXE contains precisely the expected SW/LW/XORI guest opcodes, while the v194 source oracle proves input-file SHA-256 matches the checked-in machine-code builder. v195 remains under its own 88-job CI at the start of v196.

The new v196 checker independently interprets only the exact MIPS-I subset present in the signed nine-instruction PS1 guest program: LUI, ORI, SW, LW, NOP and XORI. Unlike the machine-code generator, the interpreter uses a general register file with r0 hard-wired to zero, a 32-bit wrapping address space, signed 16-bit memory offsets and an explicit one-instruction delayed register write for LW. All memory access is constrained to scratch RAM addresses 0x001e0000 and 0x001e0004; a third neighboring guard is protected.

Using seeded scratch memory different from the guest's desired output, the correct input must perform exactly two SW and one LW, commit its loaded register after the NOP delay slot and write the source value 0x51a7c3d9 and computed value 0x51a73c26 to the two addresses. In the deliberately broken MISSING_SW variant, LW returns the seed value instead; in MISSING_LW the ORI-clobbered register is never restored before XORI. Both must produce a different second RAM word, without altering the guard. The model also proves that moving XORI into the LW delay slot does not produce the correct value, unlike an incorrect immediate-load executor.

The native source check reads only the original synthetic guest EXE, runs this independent interpreter and its negative variants, and then runs inherited v195/v194/v193/v192/v191/v190/v189 native evidence proofs. No input or private data is exported.

Expected aggregate marker:

VH196_INDEPENDENT_GUEST_MIPS_RAM_PASS modes=10 words=9 guest_sw=2 guest_lw=1 load_delay=1 negative_paths=2 unchanged_neighbor=1 original_retail=0

This is limited proof for a synthetic PS1 guest program in PCSX ReARMed/Unai, not original Vandal Hearts retail MAP02, not actual gameplay and not a Nintendo Switch console. The PR must stay Draft until native GCC/Clang and inherited CI complete.
