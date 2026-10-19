# MAP02 v187 — exact native RAM snapshot receipts bound to PCSX VBlank events

Base: fully green MAP02 v186 Draft PR #216 (79/79 workflows, native pinned PCSX ReARMed/Unai GCC and Clang).

v185 proved two synthetic guest-computed words and independent guard survive three pre-execution boundaries. v186 added fail-closed native refusals after faults placed after phase one and phase two. Those diagnostics relied mainly on Boolean outcomes. v187 adds exact numeric pre-execution snapshots for all three PS1 RAM words with genuine emulator VBlank ordinals, logged immediately before RAM comparison at phases 1, 2 and 3.

The native counter vh78_vblank_observed_count must equal pre-execution phase ordinal 1, 2 or 3, otherwise process exit 87. A clean run must print exactly three VH187_NATIVE_RAM_SNAPSHOT lines with first=51a7c3d9 derived=51a73c26 guard=a1b2c3d4, followed by VH187_NATIVE_RAM_SNAPSHOTS_PASS boundaries=3 ordered_vblanks=3 exact_values=1 guard=1 original_retail=0.

All nine pre-existing test-only host corruption modes must retain native exit 86 and their existing single failed RAM field, plus a numeric receipt showing the one-bit mutation: 51a7c3d8, 51a73c27 or a1b2c3d5. They must not print a positive v187 marker.

Independent GCC/Clang source and phase model audits plus pinned native PCSX ReARMed/Unai GCC/Clang run logs are mandatory. No game assets, original executable or original retail MAP02 frame are part of this synthetic proof; physical Nintendo Switch graphics remain unverified. Work stays in a Draft PR, main untouched.
