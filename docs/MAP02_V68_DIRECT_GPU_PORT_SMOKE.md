# MAP02 v68 — direct GP0 MMIO plus DMA2 and no-media PCSX CLI smoke

## Goal

The prior v67 source-level diagnostic bridge reads **GPU DMA2 linked-list**
submissions from a pinned open-source PlayStation emulator. A real game
can also issue **direct CPU writes to the GPU GP0 register** at address
`0x1F801810`, which DMA2 observation alone necessarily misses.

v68 patches the pinned
[notaz/pcsx_rearmed@`8b6c163575e6ce9a0537553e0d4ed4225315955e`](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e)
`psxHwWrite32` **just before its original
`GPU_writeData(value)` call** to emit a new `GP0_MMIO` event. The
existing GP1 control-write and DMA2 linked-list hooks remain intact,
with all observations disabled unless diagnostic compilation and
private output settings are both explicitly enabled.

The GP0 write is observed on the **CPU / emulator input side**.
It is not a claim that a GPU plugin consumed that command, performed
a particular drawing action or produced a particular VRAM buffer.

## Synthetic mixed GPU stream validation

`tools/audit_map02_v68_mixed_gpu.py` consumes:
- the v65/v68 ordered local JSONL GPU observations,
- the v67 frame-bound manifest holding one DMA head and SHA per frame,
- the corresponding private immutable 2 MiB per-DMA RAM captures.

It supports three bounded event types:
`GP0_MMIO` with a single direct 32-bit GPU command/data word;
`GP0_DMA2` with the full linked-list GP0 payload observed at submission;
and `GP1_WRITE` with explicitly supported full GPU reset GP1(00)
or FIFO reset GP1(01).

A direct GP0 word can be **part of a multiword polygon, line, VRAM
transfer or E6-related command**, not necessarily the start of a new
GP0 packet. The parser accumulates direct GP0 words in FIFO order
until the next DMA2 submission, then parses the combined stream using
the v62 packet lengths and v63 E1–E6 drawing-register semantics.
Before a GP1 reset, any earlier direct words must form a complete
command stream; truncated sequences fail closed.

Unrecognized port records, unsupported GP1 writes, mismatched DMA
heads, invalid packet lengths, duplicate/dangling events, illegal
bitfields, reordered ticks and disallowed provenance fields are
refused. The report contains only aggregate counters and closed
hardware/retail authenticity flags, never original GPU data.

This is a **conservative bounded diagnostic parser**, not a faithful
emulator of arbitrary GPU FIFO fragmentation. Mixed streams that cross
unsupported interrupt or callback boundaries require separately
specified handling, never silent guessing.

## Source patch and local usage

Apply the observer to a disposable, pinned upstream checkout:

```bash
python3 -m remaster.tools.apply_map02_v68_pcsx_rearmed /tmp/pcsx-rearmed-v68
```

Build the instrumented frontend (with your own supported SDL 1.2
and emulator dependencies):

```bash
make -C /tmp/pcsx-rearmed-v68 VH_MAP02_V66_PCSX_PROBE=1
```

Observations are opt-in only:

```bash
mkdir -m 700 /private/v68-gpu-frames
export VH_MAP02_V66_PCSX_LOG=/private/NEW-gpu-observations.jsonl
export VH_MAP02_V67_SNAPSHOT_DIR=/private/v68-gpu-frames
```

Raw GP0 command words, dynamic RAM snapshots and the private
hash manifest may include proprietary game assets. **Do not upload
them to GitHub or attach them to a public CI run.**

The sanitized parser can be run offline:

```bash
python3 -m remaster.tools.audit_map02_v68_mixed_gpu \
  --snapshot-dir /private/v68-gpu-frames \
  --manifest /private/v67-bound-frame-manifest.json \
  --probe /private/NEW-gpu-observations.jsonl \
  --output /private/v68-aggregate-only.json
```

## Native executable start smoke — no game

The GCC/Clang CI now builds the **complete pinned PCSX ReARMed
diagnostic executable** with `libpicofe` and SDL 1.2 dependencies.
It also **executes the built `pcsx --help` process**, checks for
its expected command-line usage output, and requires it to return
normally without creating a GPU capture file.

This is a genuine **native CLI process execution**, but it returns
during option parsing; it is **not** a PlayStation CPU/GPU bootstrap,
a BIOS load, original gameplay or even a rendered frame. No BIOS,
game disc image or proprietary gameplay data are used.

The synthetic C driver calls the **same real PCSX bridge
implementation** with four direct GP0(E6) words interleaved among
four DMA2 submissions and two simulated GP1 operations. The mixed
validator must recognize **84 GP0 input words** (four direct and
80 DMA2), maintain E1–E6 state ordering, verify all immutable
RAM captures and refuse deliberate direct-GP0 corruption.
Inherited v45–v67 graphical and provenance regressions also run.

## Evidence gates

- `real_game_boot_verified=false`
- `gpu_plugin_fifo_consumption_verified=false`
- `independent_capture_provenance_verified=false`
- `retail_gp0_provenance_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

No authenticated original MAP02 capture, Switch gameplay or
HD replacement is claimed. PR stays a stacked draft and
does not change `main`.
