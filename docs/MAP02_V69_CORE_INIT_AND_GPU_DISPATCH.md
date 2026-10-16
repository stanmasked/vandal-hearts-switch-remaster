# MAP02 v69 — PCSX HLE no-media core initialization and GPU plugin callback dispatch

## Scope

v68 actually launched the fully linked `pcsx --help` executable without
a disc or BIOS. That returns **before** PCSX initializes its emulated
core and GPU plugin. v69 introduces an opt-in no-media smoke flag and
observes the boundary where PCSX invokes its GPU plugin callbacks.

The pinned open-source emulator is
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).
The source patch is applied only to a disposable cloned checkout, not
to the main Switch remaster branch.

### No-commercial-media core smoke

The **diagnostic-only** `--vh69-core-smoke` flag is guarded by
`VH_MAP02_V66_PCSX_PROBE`. The regular application remains unaffected
when the diagnostics are not compiled.

Unlike `--help`, this flag lets the native frontend pass through:
- input/platform initialization and core `emu_core_init()`, invoking
  `EmuInit()`;
- built-in HLE BIOS selection; no commercial BIOS image is loaded;
- plugin loading and opening, including the GPU plugin;
- `SysReset()` for emulator core state, before loading game media;
- a deterministic no-media marker and clean resource shutdown.

Example:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  VH_MAP02_V69_CALLBACK_LOG=/private/new-callback-log.jsonl \
  ./pcsx -novid -nothread -nodrc --vh69-core-smoke
```

This is **emulator initialization**, not execution of PS1 gameplay
instructions. It supplies neither a Vandal Hearts disc image nor a
retail MAP02 capture. An HLE/no-media reset is not pixel rendering.

### GPU plugin callback dispatch

PCSX's actual `libpcsxcore/plugins.c` resolves GPU function pointers,
then calls a guarded adapter just after `GPUgetScreenInfo` resolution.
The adapter preserves each original callback and intercepts:

| Callback | Origin | Evidence level |
|---|---|---|
| `GPUwriteData` | CPU direct GP0 | Callback entry and return |
| `GPUwriteDataMem` | Block-mode GPU DMA | Callback entry and return |
| `GPUwriteStatus` | GP1 control write | Callback entry and return |
| `GPUdmaChain` | Linked-list GPU DMA2 | Callback entry, return and unchanged return value |

No data words, DMA addresses, texture bytes, coordinate values or
framebuffer pixels are written into this secondary log. It contains
only an ordered sequence number, callback name and `enter`/`return`
phase. An initial `bind/complete` record identifies the successful
adapter attachment. The output file is created with exclusive
0600 permissions when `VH_MAP02_V69_CALLBACK_LOG` is set; otherwise
the loaded function pointers remain untouched.

This captures **synchronous function dispatch**, not independent proof
that a plugin decoded or executed the GPU instruction correctly.
A plugin could return without producing correct pixels. The v69 gate
therefore must NEVER set GPU FIFO-consumption or raster-parity to true.

### Synthetic-only tests

The CI compiles the actual pinned PCSX ReARMed native executable using
GCC and Clang, then separately:

1. Executes the new `--vh69-core-smoke` with empty private HOME and
   dummy video/audio drivers and no BIOS/disc.
2. Parses the actual plugin binding log and confirms no GPU authenticity
   or gameplay claims.
3. Compiles the same C callback wrapper against four **synthetic mock
   GPU callbacks**, exercises data/status/DMA paths, verifies the original
   callback return and strict `enter`/`return` pairing.
4. Runs the new adversarial JSONL parser tests and inherited v45–v68
   original-C GPU/PRS/GTE/OT/VHT1, GPU DMA2, GP1 state, and private
   provenance regressions.

This tests an **installed hook in a freshly built diagnostic emulator**,
not a user's independent existing emulator process. The mock GPU
callback functions do not rasterize pixels and no copyrighted game
assets enter GitHub Actions.

### Evidence boundaries

- `real_game_boot_verified=false` — no game executed;
- `gpu_plugin_fifo_consumption_verified=false`;
- `gpu_rendering_or_pixel_parity_verified=false`;
- `retail_gp0_provenance_verified=false`;
- `original_retail_MAP02_verified=false`;
- `HD_replacement_approved=false`.

The next possible milestone is a controlled synthetic PS1 executable
that makes known GP0 operations **inside the initialized emulator**,
with a separately captured GPU-plugin output reference. This would
still be distinct from retail MAP02 gameplay.

v69 stays a **stacked draft PR** based on v68. Main remains unchanged
and private original assets are not published.
