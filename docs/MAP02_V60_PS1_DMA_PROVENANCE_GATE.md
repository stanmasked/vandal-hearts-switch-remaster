# Map02 v60 — hardware-format PS1 GPU DMA2/GP0 provenance boundary

## Why this exists

The VHT1 trace of the original public PC-port is a custom serialized
diagnostic representation of its *tokenized PC primitive structs*, NOT a
hardware PlayStation GPU-command recording. v57–v59 E6 work used a
**synthetic PC-port-only** `DR_MASK` packet; the fact that its payload
starts with the actual GP0(E6) opcode does not prove that the original
PlayStation game emitted it.

A native PS1 GPU OT/DrawOTag submits a **DMA2 linked-list**. The first
32-bit little-endian RAM word of each node contains:
- bits 24–31: how many following 32-bit words to send to GP0;
- bits 0–23: the next node's RAM address; `0xFFFFFF` means end.
A node containing zero GP0 words is a valid empty ordering-table bucket.

The command stream must be decoded with the GP0 opcode's actual word
count. GP0(E6) is a single word with set-mask bit 0, check-destination
bit 1; remaining argument bits 2–23 reserved. GP0(2C–2F) is a nine-word
flat textured quadrilateral packet. **A word equal to `0xE6000003` can
be part of a textured polygon's payload, not a GP0(E6) command.**

### Grounded hardware references

- [psx-spx, DMA linked-list format](https://psx-spx.consoledev.net/dev/ps1/system/dmachannels/)
- [psx-spx, GPU depth ordering and DMA2 submission](https://psx-spx.consoledev.net/ps1/gpu/depth-ordering/)
- [psx-spx, render polygon GP0 command fields](https://psx-spx.consoledev.net/dev/ps1/gpu/render-polygon-commands/)
- [psx-spx, GP0(E1–E6) rendering attributes and mask state](https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/)

## New tools

`tools/verify_map02_v60_ps1_dma.py` is a separate, bounded parser of
a raw **PS1-format RAM slice**, with an explicit JSON manifest:
`format="ps1-dma2-linked-list-ram-v1"`, `base_address`,
`entry_points`, SHA256 of input bytes and source class.

- Inputs must be aligned, byte-bounded and match SHA256; chain pointers
  must stay in the supplied slice.
- An empty OT node is legal; cycles, dangling links, oversized nodes,
  partial GP0 commands and unsupported opcodes refuse closed.
- It consumes data by GP0 packet length, NOT a raw search for E6 words.
  It understands bounded E1–E6 state, flat untextured and textured
  polygons, and basic rectangle types. This is NOT a complete GPU.
- The tool never marks user-supplied bytes as authenticated retail
  provenance solely because the user labels them as such.
- With optional `--vht1`, it independently parses v59 VHT1 packets
  as a DIFFERENT format and verifies matching FT4 geometry/UV/TPAGE/STP
  and GP0(E6) command order. A semantic match of synthetic examples
  is **not** proof that retail assets contain the commands.

`tools/make_map02_v60_synthetic_dma.py` generates synthetic PS1-format
RAM and manifest. Four frames contain 19 linked-list nodes including
empty OT buckets and 11 actual GP0(E6)+11 nine-word GP0 FT4 packet pairs.
The FT4 payload deliberately contains 11 deceptive `0xE6000003`
values. Those 11 values are **not GP0 commands**. This hardware-format
synthetic example is cross-compared with v59's **genuine original PC-port
VHT1 trace**, acquired in the same GCC/Clang CI.

`tests/test_map02_v60_ps1_dma.py` rejects malformed metadata, alien
provenance claims, checksum mismatch, pointer cycle/overflow, GP0 length
misinterpretation, mask-word tampering, polygon payload changes, wrong
clip/UV/STP when compared with VHT1, and VHT1 masquerading as raw PS1 RAM.

## Trusted vs untrusted evidence

- **Verified:** mechanical decoding of synthetic hardware-format DMA2,
  11 GP0(E6) commands and semantic equivalence with 11 synthetic
  state packets in the executed original PC-port VHT1 diagnostic replay.
- **Not verified:** that any byte came from an original retail PS1
  executable, disc or actual MAP02 gameplay; it is not a bus capture
  and does not represent complete PS1 DMA/GP0 execution.
- **Not verified:** GPU timing, image fidelity against hardware, HD art,
  Switch rendering, original MAP02 ownership/provenance.

Production gates are deliberately fixed:

`retail_gp0_provenance_verified=false`

`retail_MAP02_verified=false`

`HD_replacement_approved=false`

No retail resources are published, and the project default branch is
not modified. Work remains in stacked draft PR on v59.

## User-owned original data, future non-public audit

When legally obtained original game data becomes available, first
extract a **real DMA2 GPU RAM capture** and its exact entry point(s)
from a reproducible run. Keep the original binary private. Record a
source SHA256, precise hardware/emulator memory address basis and capture
method. Run this strict parser locally. Unsupported GPU opcodes should
lead to extending and independently testing the decoder, **never**
falling back to byte-scanning for E6. Actual retail provenance will
still need separate independent evidence, not merely a successful parse.
