# MAP02 v195 — independent signed guest MIPS opcode proof

Base: v194 Draft PR #230. v194 regenerates the native synthetic PS-X EXE using the *same* checked-in Python builder that initially generated the real input. If this one builder had an identical, wrong MIPS operation in both cases, the rebuilt EXE hash would match the native EXE and v194 could accept the shared mistake.

v195 independently hardcodes and checks the nine little-endian PS1 MIPS-I instructions expected in one original signed guest code window. These implement: LUI s6,0x001e (scratch RAM at 0x001e0000), LUI s7,0x51a7, ORI s7,s7,0xc3d9, SW s7,0(s6), ORI s7,zero,0xff (destroy register), LW s7,0(s6), NOP (PS1 load-delay slot), XORI s7,s7,0xffff, and SW s7,4(s6). There must be exactly one such contiguous nine-word chain in the signed 8192-byte guest image, at a four-byte aligned address, in a 10240-byte PS-X EXE.

The v195 checker verifies that the native input contains that literal sequence; compares CORRECT source bytes to the actual native EXE; requires the two deliberately broken source variants to differ only by zeroing precisely SW or LW at position 3 or 5; and then runs the full inherited v194/v193/v192/v191/v190/v189 evidence chain. No EXE bytes, private hashes or original retail ROM data are published.

An independent regression simulates a *coordinated builder compromise*: source-generated CORRECT EXE and all 20 SHA-256 receipts are rewritten to describe the same wrong PS-X EXE missing guest SW. v194's internally consistent source-regeneration audit accepts; v195 must reject because the independent hardcoded machine-word sequence does not match. Additional tests tamper each of the nine instructions, forge the signed PS-X header and create duplicate guest sequences.

Required native marker:

VH195_INDEPENDENT_MIPS_OPCODES_PASS modes=10 words=9 signed_sequence_unique=1 missing_sw_refused=1 missing_lw_refused=1 canonical_source=1 original_retail=0

All evidence remains native PCSX ReARMed/Unai running synthetic PS1 guest code, not the retail Vandal Hearts MAP02 scene and not a physical Nintendo Switch. PR remains Draft pending native GCC and Clang and inherited CI.
