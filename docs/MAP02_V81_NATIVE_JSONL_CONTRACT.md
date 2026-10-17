# MAP02 v81 — native observed-event JSONL formatting gate

Stacked on v80, this stage installs a C formatter for *already observed*
bounded events. Each JSONL record carries `seq`, `kind`, `value`,
`cycle`, and `frame`. Kinds are strictly distinguished:
`vblank`, `gp1_mmio`, and `gpu_dma2_start`. The last kind is a DMA2
start address, **not** a decoded, consumed or executed GP0 command.
Non-VBlank events carry `frame=0` as unknown, not an identified frame.

The formatter operates entirely in caller-owned memory, verifies no
drops occurred, validates contiguous event sequence numbers, requires
at least two observed VBlank edges, and fails closed on buffer
truncation or unexpected types. It never writes to the user's SD card
or changes emulated CPU/GPU state.

This is **not a completed runtime evidence pipeline**: source integration
and synthetic C-backed unit tests are included, but the native pinned
PCSX build, execution, and emitted trace have not yet been independently
confirmed. No automatic upload or public sharing of private GPU data.

Important: the v79 analyzer expects decoded `gp0` / `gp1` / VRAM
records and its own snapshot boundary requirements. Do **not** pass the
v81 raw input-event format to v79 as though it were equivalent. A
distinct conversion/provenance gate must first validate event identity
and preserve the DMA2-vs-GP0 distinction.

Follow-up: implement native integration checks, read-back verified
private export, and actual GP0 and VRAM-write observers without
substituting simulated event data for original retail MAP02.

`physical_ps1_vblank_verified=false`;
`original_retail_MAP02_verified=false`;
`HD_replacement_approved=false`.
