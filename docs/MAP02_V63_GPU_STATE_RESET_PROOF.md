# Map02 v63 — GP0 E1–E6 register states and GP1 reset boundaries

## What is being proved

v63 adds a strictly bounded, **synthetic** hardware-format GPU state
interpreter atop the v60 DMA2-linked-list walker and v62 GP0 packet framer.

v60–v62 verified packet boundaries, GP0(E6) destination mask behavior
and state carry between consecutive DMA lists, but did not independently
track drawing-mode, texture-window, drawing-area or drawing-offset state.
The new tool decodes GP0(E1–E6) in actual parsed command order and
takes a register snapshot BEFORE each polygon/line/rectangle/VRAM
transfer. It does not rasterize or verify pixel-equivalent PS1 output.

The model assumes an **original retail-style v0 GPU profile**, refusing
revision-specific extended GP0(E1) bits and nonzero E2/E3/E4/E5/E6
reserved bits rather than silently guessing v1/v2 2-MB GPU behavior.

Hardware basis: [PSX-SPX rendering attributes](https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/) and
[GP1 reset commands](https://psx-spx.consoledev.net/dev/ps1/gpu/gpu-control-commands/).
These specifications distinguish GP1(00) full GPU reset, which resets
E1–E6 attributes, from GP1(01) command-buffer reset, which does not
clear the registers.

## Register semantics

- **E1:** texture-page X/Y bases; ABR; texture pixel format;
  dithering; drawing-to-display permission. Hardware-revision-dependent
  extension bits refuse under the v0 profile.
- **E2:** mask/offset texture-window fields.
  `UV'=(UV AND NOT(mask*8)) OR ((offset AND mask)*8)`.
- **E3 / E4:** top-left and bottom-right inclusive drawing area.
  These use packed X bits 0–9 / Y bits 10–18 in the v0 profile —
  NOT the GP0 vertex XY layout (low/high 16 bits).
- **E5:** signed 11-bit X/Y drawing offsets (ranges -1024..1023).
- **E6:** force/set and destination-check mask flags, continued from
  earlier v57–v62 work.
- **GP0(02) FillVRAM:** explicitly recorded as *not* obeying the E6
  destination mask, unlike transfers/drawing primitives. New tests
  verify only this classification, not rendered VRAM.
- **All drawing state:** persistent across DMA2 linked-list boundaries,
  unless an independently observed intervening GPU control operation
  legitimately resets it.

## Why GP1 must be a separate input

A DMA2 linked-list RAM snapshot contains **GP0 payload words**.
It does not automatically contain evidence of GP1 control-port writes.

The optional JSON sidecar accepts only:
- `0x00000000` before a frame: GP1(00) complete GPU reset;
- `0x01000000` before a frame: GP1(01) command-FIFO reset *only*.

Events must be frame-indexed, in ascending order, and have no extra
fields. Unsupported GP1 commands refuse closed. Without a sidecar,
the tool carries E1–E6 state between all consecutive submitted lists.
Even with a sidecar, the report explicitly says the GP1 events are
**user assertions, NOT captured hardware proof**. Unknown intervening
commands could change GPU state.

Example strictly synthetic GP1 sidecar:

```json
{
  "schema": "map02-v63-gp1-boundary-events-v1",
  "events": [
    {"before_frame": 2, "word": 0},
    {"before_frame": 3, "word": 16777216}
  ]
}
```

### Local-only audit (no uploads)

From a directory containing the project package:

```bash
python3 -m tools.audit_map02_v63_gp0_gp1_state \
  --ram /private/owned-gpu-ram.bin \
  --manifest /private/dma2-manifest.json \
  --gp1 /private/gp1-observations.json \
  --output /private/v63-summary.json
```

Use `python3 -m remaster.tools.audit_map02_v63_gp0_gp1_state`
when the repository is nested in a `remaster` directory.

The optional `--gp1` may be omitted, but a missing event capture must
not be interpreted as proof that no reset occurred.

The resulting summary contains only aggregate counts, verification
status and explicitly closed provenance/HD flags. It does **not** emit
private source file paths, GPU words, raw polygon coordinates, texture
samples, register values or VRAM pixels.

## Synthetic CI proof

`tools/make_map02_v63_state_fixture.py` constructs four entirely
synthetic PS1-format DMA scenes:

1. E1–E6 settings, an FT4, a rectangle and FillVRAM.
2. FT4 inherits the previous E1–E6, E2 changes only window state,
   a textured rectangle and VRAM upload whose data resembles E6.
3. A separately asserted GP1(00) full reset precedes the first FT4;
   subsequent E1/E3/E4/E5/E6 then change the drawing attributes.
4. An asserted GP1(01) FIFO reset precedes the first FT4, **without
   erasing the previous drawing state**; a later E6 changes mask state.

The sample comprises 19 synthetic linked-list nodes and 13 synthetic
GP0(E1–E6) register packets. 32 dedicated Python regression methods
cover all register fields, signed E5 bounds, E2 UV masking, cross-frame
carry, both GP1 reset classes, unsupported GP1 operations, private
output, malformed commands and **checksum-recomputed** corruption of
each E1–E6 reserved-bit field.

The GCC/Clang CI inherits original compiled PC-port GPU and PRS
exercises, actual VHT1 record/replay evidence and earlier v45–v62
regressions. No user-owned proprietary binaries enter CI.

## Still unproven

This is a structural state-audit tool — NOT hardware-exact GP0/GP1
timing simulation, an original retail gameplay recording, new raster
pixel parity or Switch runtime evidence. A sidecar declaring `GP1(00)`
does not demonstrate that the user captured that write.

Hard gates remain:

- `actual_gp1_commands_observed_on_hardware=false`
- `retail_gp0_provenance_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

v63 remains a stacked **draft** PR atop v62. Project `main`
and HD replacement settings are unchanged.
