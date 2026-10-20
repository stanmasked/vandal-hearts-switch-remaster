# MAP02 — one private evidence set across PC texture source and native FT4 GPU

This opt-in, **local-only** check composes two existing verified modules:

- `tools/verify_map02_private_timeline_pc_vram4.py` — validates source/compiled PC GTE, one VRAM snapshot for every source FT4, and independent pixel arithmetic across each 256×256 4bpp page compared with the real compiled public PC-port `SampleTexture` implementation.
- `tools/verify_map02_source_native_ft4_join.py` — independently validates original-format native PC GPU DrawOTag before/after snapshots, explicit distinct-frame clock mapping, exact GPU XY/UV/tpage/CLUT/E2 texture-window packet signatures, unambiguous packet identity, referenced 16-bit texture/CLUT word equality and ordering without guessing packet submission order.

`tools/verify_map02_private_pc_native_ft4.py` calls both **with the same immutable source directory**, insists that they agree on the count of source faces and exact matched FT4 records, and rereads *all* private source and native captured inputs after both expensive validations. This last read detects changed file contents, inode replacement, symlinks and metadata changes between the two validators. It does not claim kernel-atomic multi-file snapshots or exclude metadata-preserving changes that occur between two reads.

Both private directories must be local, distinct, owner-only (`0700`). The public PC-port `pc_raster.c` source must be the pinned Git blob from `HalmyLyseas/VandalHearts-PcPort`, commit `14552fffa0e0b47e02b57592e274fc6e7a649923`. Every private file is read through the already tested no-follow, regular-file, same-inode double-read code. The checker receives no new raw resource source, uploads nothing and returns **only aggregate counts and strictly false retail/hardware authentication flags**. No paths, colors, geometry, VRAM samples, private hashes or screenshots are present in the success report or generic CLI error.

## Owner-local command (only when original private captures exist)

```bash
python3 -m tools.verify_map02_private_pc_native_ft4 \
  /private/map02/source-timeline \
  /private/map02/native-gpu-capture \
  /public/pinned/platform/pc/src/pc_raster.c \
  --compiler clang
```

Intel macOS with Python 3.9+ and Clang is supported by the code paths; actual owner hardware and original retail-image operation have not been demonstrated. The source timeline must include `timeline.json`, `gpu-events.jsonl`, one `gpu-vram-NNN.bin` per source FT4, `map02.decoded.bin` and the explicit, hash-bound `gpu-face-timeline-join.json` mapping. The separate native folder must include the GPU event log and its referenced native before/after snapshots. Do not upload any of these captures, BIN/CUE, executables, images or private JSON receipts to GitHub.

## No-disc CI acceptance

The new GitHub Actions workflow downloads **only the pinned public PC-port source** and invents two source FT4 observations (source clock 411) and a reversed-order native GPU packet sequence (native clock 12) with completely synthetic VRAM. It checks both GCC and Clang and rejects mutated GPU FT4 texture-window parameters, late native snapshot changes, mutated source snapshots, incorrect clock mapping, linked snapshot files and non-private native directories. The existing timeline/native test fixture's other negative controls are also rerun.

A green result means only that **the verifier correctly enforces its consistency contract**. It cannot authenticate any retail PS1/PC-port runtime capture, original MAP02 assets, uninterrupted GPU write history, source-to-native frame mapping provenance, genuine PlayStation pixels, bit-exact rendering or Switch console boot. All changes remain Draft; no merges.
