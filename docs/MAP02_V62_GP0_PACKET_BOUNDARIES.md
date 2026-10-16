# Map02 v62 — PS1 GP0 packet boundaries, not false E6 discovery

## Goal

Extend the existing hardware-format PlayStation GPU DMA2 preflight parser with
the packet families necessary to inspect a wider range of original-looking
GPU command streams, without silently assuming all arbitrary 32-bit words
containing `0xE6` represent a real GP0(E6) command.

This milestone is **structural parsing only**: no PS1 GPU emulation,
VRAM-pixel oracle for new primitives, gameplay execution, retail extraction
or HD-texture replacement is claimed.

### Decoder additions

`tools/decode_map02_v62_gp0.py` extends the v60/v61 public
`parse_gp0(words, initial_mask, return_state)` interface. The original
v60 DMA2 linked-list walker and the v61 persistent GP0(E6) state are retained.

Commands supported now include:
- GP0(20h–3Fh): flat/Gouraud, triangle/quadrilateral, untextured/textured.
  Packet length is derived from the three actual GPU flags (IIP, VTX, TME).
  The legacy FT4 (2Ch–2Fh) event fields remain unchanged.
- GP0(40h–47h, 50h–57h): fixed monochrome and Gouraud line packets.
- GP0(48h–4Fh, 58h–5Fh): variable-length mono/Gouraud polylines, terminated
  only on a legal vertex/color boundary where
  `(word & 0xF000F000) == 0x50005000`. Missing terminators,
  malformed color/vertex pairs and excessively long polylines fail closed.
- GP0(60h–7Fh): all eight size/texture-layout combinations for variable,
  1×1, 8×8 and 16×16 rectangles.
- GP0(02h) VRAM fill; GP0(80h–9Fh) VRAM-to-VRAM copy;
  GP0(A0h–BFh) CPU-to-VRAM transfer with exact 16-bit packed payload
  word count; GP0(C0h–DFh) VRAM-to-CPU transfer header.
- GP0(1Fh) IRQ1, E1h–E6h state and 00h/01h one-word no-op/reset-cache.

All GPU words are bounded; incomplete packets, overlong uploads and
unsupported opcodes are explicitly rejected. `E6` recognition only
occurs after the previous entire command has been consumed.

### Hardware format references

- [PSX-SPX polygon opcode flags and word structures](https://psx-spx.consoledev.net/ps1/gpu/render-polygon-commands/)
- [PSX-SPX line/polyline termination](https://psx-spx.consoledev.net/ps1/gpu/render-line-commands/)
- [PSX-SPX rectangle size/texture word layouts](https://psx-spx.consoledev.net/ps1/gpu/render-rectangle-commands/)
- [PSX-SPX GPU memory transfer commands](https://psx-spx.consoledev.net/ps1/gpu/memory-transfer-commands/)
- [PSX-SPX GP0(E6) drawing mask bits](https://psx-spx.consoledev.net/ps1/gpu/rendering-attributes/)

### Synthetic adversarial proof

`tools/make_map02_v62_gp0_fixtures.py` creates a separate 4-frame
synthetic, hardware-format PS1 RAM capture, with **27 linked-list nodes**.
It deliberately includes deceptive E6-looking values in:
- Gouraud color fields of polygons and polylines;
- ordinary polyline vertices and legal terminator-neighbor words;
- rectangle CLUT/UV fields;
- packed 16-bit CPU-to-VRAM upload pixel data.

One 12-word Gouraud textured quadrilateral command spans **two distinct
DMA2 nodes**. The parser must concatenate the DMA payload in linked-list
order without corrupting GP0 command framing. The expected true GP0(E6)
command count is **3**, even though many more data words resemble E6.

`tests/test_map02_v62_gp0.py` includes 28 dedicated test methods,
including exhaustive 32 polygon opcode variations and all 32 rectangle
opcodes, legal polyline termination patterns, invalid/partial packets,
overlong transfers, v60 FT4 schema compatibility, and persisted E6 mask
state across multiple DMA lists.

The GCC+Clang workflow additionally mutates an **actual standalone E6**
reserved bit and the packed VRAM transfer size, recomputes the source
checksum, and demands *structural* rejection. It inherits all v45–v61
original-C GPU, VHT1 record/replay, PS1 DMA2 and privacy regressions.
No original copyrighted GPU capture is published or required.

### Important limitations

This is a bounded decoder, **not** a complete PS1 GPU instruction or
DMA/GP1 execution model. Real streams with unsupported opcodes must
be refused until their exact hardware lengths are independently established.
It does not verify GPU rasterization of new lines/rectangles, hardware timing,
texture cache effects, VRAM mutation, intervening GP1 resets, user-owned
MAP02 extraction or any Switch display output.

The fixed audit gates remain:

- `retail_gp0_provenance_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

`main` is not modified by the stacked draft v62 PR.
