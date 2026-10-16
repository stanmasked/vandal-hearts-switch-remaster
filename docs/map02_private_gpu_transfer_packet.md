# MAP02: private GPU transfer packet v1

**Scope:** offline MAP02 PC-port diagnostic pipeline, not retail PS1 pixel
equivalence or live Nintendo Switch gameplay. No copyrighted game assets
are provided or committed by this tooling.

The Python auditor verifies a user's locally supplied frozen MAP02 source,
per-submission GPU state, VRAM timeline, SHA-256 manifests and explicit
`LoadImage` / `MoveImage` / `ClearImage` journal. The exporter converts
that audited journal to a small, strict C-readable packet. Its LOAD payloads
may contain game-derived bytes: **do not upload, commit, or publish packets**.

## Export privately

The directory needs `timeline.json`, `write-ledger.json`,
`map02.decoded.bin`, `gpu-events.jsonl`, matching
`gpu-vram-000.bin`, `gpu-vram-001.bin`, ... and
`gpu-writes.jsonl`, plus any indexed `load-0000.bin` payloads.
Use the existing local validators to create and validate these inputs.

Run from the repository root, replacing both paths with paths on the
**local machine**:

```sh
PYTHONPATH=. python3 -m tools.export_map02_verified_vram_ledger \
  /private/map02-capture \
  --output /private/map02-checked-transfers.bin
```

The exporter checks the complete existing GPU write-ledger audit first;
it refuses unaccounted VRAM changes, invalid source/texture/GTE observations,
mismatched hashes and overwritten output files. Output permissions on POSIX
systems default to owner-only (0600). The console report contains counts
and the packet hash only. This packet is not a signed attestation.

## C consumption

`source/map02_vram4_transfer_import.h` defines the
`vh_map02_vram_ledger_import_packet` decoder and
`vh_map02_vram4_timeline_build_from_packet` convenience bridge.

The caller supplies:

- The byte packet, its exact size and a caller-owned event array.
- The separately captured, immutable decoded MAP02 bytes and one VRAM
  snapshot **for each submitted, NCLIP-visible face**.
- A `VhMap02Vram4TimelineInput` with matching frame, order and indices.
- A `VhMap02Vram4FrameWorkspace` and a separate scratch buffer holding
  at least `VH_MAP02_VRAM_BYTES` bytes.

Import accepts at most 512 events. It validates a canonical little-endian
header and every bounded event before writing the caller's event array.
The subsequent replay requires that each full VRAM snapshot match the
exact result of the logged transfer operations; unexplained differences
abort **before the OT scene is built**. No game data is uploaded.

## Binary contract

- 32-byte header: `VHMAPGL1`, LE32 frame, submissions, event count and
  packet byte length, followed by eight zero bytes.
- Each event: 13 signed LE32 integers containing step, boundary, opcode
  (`1=load`, `2=move`, `3=clear`), RECT x/y/w/h, destination x/y,
  RGB and payload length.
- `load` events append exactly `w*h*2` little-endian source bytes.
  Other events have no payload; all unused fields must be zero.
- Events have contiguous zero-based steps and nondecreasing submission
  boundaries starting at 1. Event payloads are limited to 16,384 words.

The decoder rejects trailing bytes and truncated records and preserves
output on malformed packets. The packet is **not** a complete capture:
its input geometry, GTE camera, GPU register state, palette and VRAM
snapshots remain separate caller-owned, unmodified files.

## Limitations

Even a perfect replay of recorded transfers does not prove the trace
originated in retail gameplay. GPU rasterized writes are not modeled, and
writes that happened and reverted between snapshot instants cannot be
excluded. A passed replay proves consistency with the **supplied** sequence,
not PS1 GPU timing or bit-identical rendered pixels.

See `tools/verify_map02_gpu_write_ledger.py` for the Python auditor,
`source/map02_vram4_transfer_ledger.h` for the source-matched C replay,
and `tests/test_map02_captured_vram4_bridge.c` for synthetic regression
coverage.
