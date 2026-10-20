# MAP02 — local PC SampleTexture parity for separately captured FT4 VRAM

This tool is the next source-research step after approved Draft PRs #317
(full-page 4-bpp public PC source arithmetic) and #324 (three synthetic
per-FT4 atlas/CLUT bindings).

## Why

An FT4 face may see VRAM content that differs from the preceding face:
GPU LoadImage, MoveImage, ClearImage or framebuffer overwrites can affect
a texture or CLUT between two submissions. A single frame-wide VRAM
snapshot is not always sufficient.

The already implemented `tools/verify_map02_vram_timeline.py` validates
the **source/GTE event and one SHA-256-pinned VRAM snapshot for every
submitted face**. The new `tools/verify_map02_private_timeline_pc_vram4.py`
calls that validator first, then independently runs the actual compiled
`TPageOrigin` and `SampleTexture` function bodies from the exact
public PC-port raster Git blob.

For each independently verified submission, the checker:

1. Reads the local **private 0700** timeline directory with pinned,
   regular, no-follow files, including `timeline.json`,
   `gpu-events.jsonl`, `map02.decoded.bin` and
   `gpu-vram-000.bin`, `gpu-vram-001.bin`, etc.
2. Rejects changed file identity, missing files, symlinks, invalid source
   face IDs, unpaired snapshots, wrong source/GTE projection and failed
   original palette probes through the existing validator.
3. Compiles the exact public PC `SampleTexture` and the portable
   `vh_map02_vram4_materialize` implementation **once in a private
   temporary build folder**. The verifier never writes original game
   bytes or snapshot pixels to C source files.
4. Sends each 1-MiB snapshot and ten face-specific texture-register /
   crop values through **subprocess stdin**, not process command-line
   arguments or public logs. Every one of the page's 65,536 BGR555
   samples, and the specified actual UVWH crop, must equal the
   independently compiled PC-port source.
5. Reads **all original input files again** after the expensive source
   and compiler checks; rejects replacements or modifications. Only an
   aggregate source-math report is printed. The CLI suppresses private
   file paths and data on validation errors.

No data is uploaded. It is a **local-only command**; do not put a real
game image, texture snapshot, executable, screenshots or generated
private receipts in the public Git repository.

## Local use (only after a private original PC capture exists)

```bash
python3 -m tools.verify_map02_private_timeline_pc_vram4 \
  /path/to/private/map02/timeline \
  /path/to/pinned/public/upstream/platform/pc/src/pc_raster.c \
  --compiler clang
```

Python 3.9+ is supported for Intel Mac. The public reference file
must have Git blob SHA-1
`ba8a05d161ad778c0b75e452ff0a11ed163c65cd`, pinned at
`HalmyLyseas/VandalHearts-PcPort` commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`.
The private directory must already exist; this command neither creates
nor modifies capture data.

## Tests that can run without the user's disc

The dedicated GitHub Actions workflow uses **only invented** GTE/source
records and two synthetic independently changing VRAM snapshots. For
both GCC and Clang it verifies a successful 131,072-texel comparison,
and fails closed on a corrupted portable 4-bpp nibble formula,
a changed snapshot after primary GTE validation, a duplicate source
face, a symlinked VRAM file, and a changed public source blob.

A green CI means the **private-format comparison program and its
security checks** function on synthetic inputs. It does not mean any
user-owned original frame was captured or tested.

## Important limits

- Public PC-port source math, even when evaluated on private inputs,
  is **not** independent PS1 GPU hardware attestation.
- Signed source events, frame labels and SHA-256 are consistency proofs,
  not proof that data truly originated from retail Vandal Hearts.
- The tool does not replay observed GPU writes between snapshots. It
  cannot exclude writes followed by restoration between captures.
- The separate source-to-native GPU frame join remains necessary;
  original source frame counters must not be assumed equal to native
  GPU DrawOTag counters.
- The portable CPU FT4 compositor is not a bit-exact rasterizer,
  and this test does not assess drawing order, STP blending,
  dithering, frame presentation or Nintendo Switch hardware.
- The verifier does not automatically publish a certificate of retail
  equivalence or modify any previous Draft PR.
