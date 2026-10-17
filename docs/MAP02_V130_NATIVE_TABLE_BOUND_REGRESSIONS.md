# MAP02 v130 — strict compiler checks for the original native gap matrix

Stacked on [v129 Draft PR #120](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/120).
v129 was validated successfully on 23/23 GitHub Actions workflows, including
5/5 native GCC and 5/5 native Clang genuine-VBlank GPU DMA profiles after
fixing the fifth-row C table declaration.

## Independent C compiler proof, not a static search alone

The v130 checker extracts the **four actual static const unsigned table
declarations** from the generated v129 PCSX ReARMed C oracle:

- \`vh129_boundary_targets[5][2]\`
- \`vh129_adjacent_histograms[5][5]\`
- \`expected_total_edges[5]\`
- \`return_gap[5]\`

The exact declarations, not retyped initializer literals, are embedded into
a small isolated C11 executable with independently authored expected
boundary splits and adjacent Unai gap histograms.

GCC and Clang separately compile with \`-Wall -Wextra -Wpedantic -Werror\`
and \`-fsanitize=undefined,bounds\`, run and verify all five mode rows.
C11 \`_Static_assert\` checks the number of rows and columns for each table.
Any duplicate, missing or incorrectly dimensioned original declaration
fails before native compilation.

## Deliberate negative controls

Three mutations must fail **at compile time**:

1. Shrink the boundary row count from five to four.
2. Shrink the independent histogram row count from five to four.
3. Shrink the return-gap row count from five to four.

Four mutations must **compile but refuse at runtime**:

1. Alter the fifth split from \`4+0\` to \`3+0\`.
2. Corrupt the first adjacent VBlank histogram.
3. Change the fifth mode's expected number of genuine callbacks from 4 to 3.
4. Change the fifth mode's expected four-back return class from 4 to 3.

The tests reject any mutation unexpectedly accepted, and require a positive
baseline executable for every compiler. C source and artifacts are temporary
private files. Only an aggregate \`VH130_NATIVE_BOUNDS_VERIFIED\` marker,
without any VRAM values, GPU commands or sample hashes, is logged.

The v129 genuine-emulator five-profile matrix is left unchanged and rerun in
the pinned PCSX native workflow along with the original private-journal
SHA-256 invariants. This new stage is a **test-harness regression guard**,
not a new retail MAP02 verification.

- original_retail_MAP02_verified: false
- physical_PS1_verified: false
- HD_replacement_approved: false
