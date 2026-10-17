# MAP02 v82 — pinned PCSX emulator private native event journal integration

v82 extends the stacked v78–v81 path, **without enabling HD replacement**.
It adds a separate opt-in `--vh82-private-export-smoke` frontend mode to
pinned PCSX ReARMed (revision
`8b6c163575e6ce9a0537553e0d4ed4225315955e`).

## Order of evidence

1. Load only the locally generated, strictly marked `VH78SYN!` MIPS EXE.
2. Reset the v80 observer *after* successful synthetic fixture authentication.
3. Run the original v78 four-phase CPU interpreter and **actual emulator**
   `psxRcntUpdate()` VBlank-start callback.
4. Require v78's four observed VBlank starts, consecutive emulator frames,
   and exact native GPU VRAM oracle (595 pixels per edge, 2,380 total).
5. Require exactly four v80 observed VBlank edge records, at least two GP1
   MMIO submissions, and zero dropped journal entries.
6. Serialize with the bounded v81 formatter into caller-owned memory.
7. Publish a local POSIX private diagnostic path from
   `VH_MAP02_V82_PRIVATE_PATH`, only if it names an absolute pathname and
   is in a private user-created directory.
8. Write only to an **exclusive** `.tmp` file (mode 0600), fsync and close,
   reopen and compare every byte, then hard-link to the final path **without
   overwriting an existing destination**. Remove the `.tmp` after success
   or failure.
9. Independently validate the saved bytes with
   `python3 -m remaster.tools.verify_map02_v82_native_trace PRIVATE.jsonl`,
   including exact count, strict per-event schema, contiguous sequence,
   and four consecutive emulator VBlank frames.

The v82 GitHub Action, on Ubuntu with GCC and Clang, fetches the exact pinned
upstream and compiles the complete opted-in emulator before executing the
synthetic scene. It also checks the duplicate-output refusal while verifying
the original private file remains unchanged.

**Private material is never uploaded as an Actions artifact.** Only short
aggregate status strings are eligible for publication. Do not enable capture
outside the synthetic test without private capture consent and appropriate
data handling.

## What the JSONL events actually mean

- `vblank`: observed **emulator** VBlank callback, cycle and emulator frame.
- `gp1_mmio`: observed GPU control submission, not proof GPU consumption;
  `frame=0` is an unknown frame placeholder, not frame zero.
- `gpu_dma2_start`: observed DMA2 start address, **not decoded GP0 words**;
  `frame=0` has the same unknown meaning.

The v82 JSONL is not interchangeable with the v79 GP0 + native VRAM-write
oracle. VRAM snapshots are validated independently within the v78 test;
v82 does not establish event-by-event GPU write provenance.

This is an **implementation and CI plan** until actual green workflow
results confirm successful patched upstream compilation and execution.
Do not label v82 as verified on real PCSX from source code alone.

## Unresolved claims

`physical_ps1_vblank_verified=false`
`retail_video_frame_correspondence_proven=false`
`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

No changes are made to the production Switch renderer or main branch.
