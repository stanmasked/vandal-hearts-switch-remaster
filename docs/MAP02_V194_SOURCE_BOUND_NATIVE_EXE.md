# MAP02 v194 — independently regenerate the original synthetic PS-X EXE from checked-in MIPS source

v194 stacks on MAP02 v193 Draft PR #228. v193 pins the private V183_RAM_CORRECT.EXE SHA-256 before and after ten genuine PCSX ReARMed/Unai native subprocesses, binds their ten return codes and output-log digests, and requires 22 genuine native GPU-phase marks and 159 deliberate corrupt-log refusals.

Remaining gap: if the original synthetic guest executable is consistently replaced with another PS-X EXE, and both its before/after fingerprints plus all 20 private receipt hashes are updated accordingly, v193's input identity guard could still pass.

v194 regenerates all three signed, synthetic guest PS-X EXE byte arrays in memory using the original checked-in MIPS-I builder tools/apply_map02_v183_native_ram_values.py make_variants(), without opening or copying any retail Vandal Hearts ROM. It confirms the canonical 10,240-byte PS-X EXE, original VH78SYN! signed header, distinct generated CORRECT, MISSING_SW and MISSING_LW binaries, and exact SHA-256 equality between the independently rebuilt CORRECT image and the actual native input EXE. The proof surrounds the inherited v193/v192/v191/v190/v189 audit with read-only original EXE+private-manifest SHA/inode/timestamp checks. No guest bytes or private fingerprints leave the runner.

Independent GCC/Clang fixture tests show why this matters: when all 20 receipts correctly describe the wrong, deliberately instruction-mutated MISSING_SW or MISSING_LW executable, the earlier v193 verifier accepts the internally consistent provenance. The new v194 verifier must independently reject both because neither matches the deterministic checked-in signed MIPS machine-code source.

Expected native aggregate:

VH194_NATIVE_SOURCE_EXE_REBUILD_PASS modes=10 rebuilt_variants=3 canonical_exe_sha_match=1 native_exe_receipts=20 native_exit_receipts=10 original_retail=0

This is evidence for synthetic guest PS1 code and native PCSX logs, not a retail Vandal Hearts MAP02 scene, not a Nintendo Switch emulator game build or physical console. The PR remains Draft until real native GCC/Clang and complete CI pass.
