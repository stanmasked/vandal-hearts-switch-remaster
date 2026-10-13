# Switch-side PS1 memory translator prototype

Status: isolated prototype with host-side unit tests. It is **not yet linked into the game engine**.

\`switch-memory/psx_memory.c\` provides an explicit translation seam from a 32-bit guest address to a caller-owned host buffer for two ranges already identified in the pinned upstream code:

- Main RAM: \`0x80000000\` through \`0x801fffff\` (2 MiB).
- Scratchpad: \`0x1f800000\` through \`0x1f8003ff\` (1 KiB).

The helper validates that the requested range is wholly contained in one supported region. It rejects zero-length requests, undersized or missing backing buffers, cross-boundary requests, the zero/NULL mirror, and I/O-register addresses. Range checks use subtraction after validating the offset, avoiding an unchecked end-address addition.

## Deliberate limitations

- No KUSEG/KSEG aliases or address canonicalization.
- No PS1 I/O-register emulation.
- No address-zero mirror behavior; the upstream PC port has special compatibility assumptions here that need separate investigation.
- No allocation, initialization policy, synchronization, save-state behavior, or integration with existing game globals.
- No guarantee that the upstream engine can use this helper without broader pointer-flow changes.

CI compiles this module with the host C compiler and runs boundary tests. Before engine integration, the design must be reconciled with all upstream address sites and the actual Switch build's memory ownership/lifetime requirements.
