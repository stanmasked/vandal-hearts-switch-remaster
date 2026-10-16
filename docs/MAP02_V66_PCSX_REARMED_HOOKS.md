# Map02 v66 — pinned PCSX ReARMed GP1 and DMA2 hooks

## Milestone: source-integrated, still not a retail capture

This is a **real-source integration patch** targeting open-source
[notaz/pcsx_rearmed](https://github.com/notaz/pcsx_rearmed),
pinned to **`8b6c163575e6ce9a0537553e0d4ed4225315955e`**
(2026-10-03). The patch is applied only to a disposable clone;
no third-party emulator source or copyrighted game content is
vendored into the Switch remaster project.

The patch inserts read-only instrumentation into exactly two
existing emulator functions:

1. `libpcsxcore/psxhw.c` `psxHwWrite32` at the CPU-side
   `0x1F801814` **GP1 GPU control-register write**, immediately
   before the original `psxHwWriteGpuSR(value)`.
2. `libpcsxcore/psxdma.c` `psxDma2`, linked-list mode
   `0x01000401`, immediately before the original
   `GPU_dmaChain(...)` callback. It walks the current emulator RAM
   linked list, recording **host-side pre-submit GP0 words**.

It does **not** hook inside the renderer or intercept GPU-plugin FIFO
consumption, and it is not a verified full-playback emulator build.
For example, GPU plugin processing may be incomplete or asynchronous,
and a source-RAM observation cannot prove exact pixel delivery.

Source references:
- [PCSX ReARMed `psxhw.c` at pinned SHA](https://github.com/notaz/pcsx_rearmed/blob/8b6c163575e6ce9a0537553e0d4ed4225315955e/libpcsxcore/psxhw.c)
- [PCSX ReARMed `psxdma.c` at pinned SHA](https://github.com/notaz/pcsx_rearmed/blob/8b6c163575e6ce9a0537553e0d4ed4225315955e/libpcsxcore/psxdma.c)
- [PS1 GP1 and DMA2 hardware command definitions](https://psx-spx.consoledev.net/ps1/gpu/)

## Apply without altering upstream or main

From the parent directory of the `remaster` project:

```bash
git clone https://github.com/notaz/pcsx_rearmed.git /tmp/pcsx-rearmed-v66
git -C /tmp/pcsx-rearmed-v66 checkout 8b6c163575e6ce9a0537553e0d4ed4225315955e
python3 -m remaster.tools.apply_map02_v66_pcsx_rearmed /tmp/pcsx-rearmed-v66
```

The exact-anchor patch refuses source deviations, previously
instrumented code, and any existing adapter files. The original GPU
status write, DMA2 linked-list submission and scheduling logic are
left intact. A guarded Makefile addition means an ordinary emulator
build **does not activate** the capture functionality.

Diagnostic build opt-in:

```bash
make -C /tmp/pcsx-rearmed-v66 VH_MAP02_V66_PCSX_PROBE=1
```

A full emulator executable/build has **not** been validated as part of
v66: the CI compiles the actual modified `psxHwWrite32` and
`psxDma2` translation units individually, both with the flag
enabled and disabled, and tests the compiled bridge separately.
The final emulator frontend still needs environment, dependencies,
an actual boot and supported GPU plugin verification.

Enable local logging on a machine running that instrumented build:

```bash
export VH_MAP02_V66_PCSX_LOG=/private/new_gpu_trace.jsonl
```

The bridge creates a new capture file with `0600` permissions and
refuses to overwrite an existing file. It never uploads anything.
The environment variable must be set **before the first observed GPU
port call**; absence of the variable disables capture. The bridge is
single-threaded, strictly limited to 2 MiB emulated RAM, 4096 DMA
nodes and 65,536 GP0 words per linked list. It rejects incomplete
lists, repeated pointers and terminators outside the current strict
v60/v65 contract. On unsupported input it adds an invalid marker to
the capture so the downstream analyzer must refuse.

**Important real-capture limitation:** real PCSX GPU programs can
issue multiple GP1 operations, including modes other than GP1(00)
and GP1(01). The v65 consumer deliberately refuses these because the
bounded parser cannot yet safely interpret their effects. A log
rejected in this way is useful diagnostic information, not a failed
claim of emulation correctness.

Actual capture sessions may also modify PS1 RAM between frames.
The current v65 manifest / saved RAM snapshot format can prove
GP0 equality only when the saved RAM correctly corresponds to each
recorded chain. A changing in-game scene is not guaranteed to satisfy
this single-snapshot contract. A following milestone will need
per-submission or versioned RAM snapshots and a broader GP1 grammar.

## Validation proof: strictly synthetic, not gameplay

The v66 GCC+Clang CI uses:

- pinned public PCSX ReARMed source checkout and guarded code patch;
- compilation of **original** `psxhw.c` and `psxdma.c` with
  instrumenter ON/OFF, checking symbol references with `nm`;
- compiled C11 bridge and a separate synthetic-only invocation driver;
- v63 synthetic PS1-format DMA2 RAM, four DMA frames / 19 nodes;
- two simulated GP1 writes before frames 2 and 3;
- v65 readback parity of **80 GP0 words**, then v64 journal audit;
- a deliberately altered GPU word, which must fail;
- all earlier original-PC-port GPU/OT/VHT1 and v45–v65 regressions.

This runs real *PCSX source call-site compilation*, but its simulated
bridge driver is **not** the same as running the real emulator with
game media. The source patch does not install itself into a user's
running emulator.

In addition to prior tests, v66 checks pin mismatch, exact anchors,
non-invasiveness, off-by-default Makefile handling, and that a
second patch application or existing target file is refused.

Hard evidence gates remain:

`producer_instrumentation_actually_installed=false`

`gp1_write_proven_to_originate_from_hardware=false`

`retail_gp0_provenance_verified=false`

`original_retail_MAP02_verified=false`

`HD_replacement_approved=false`

No original gameplay verified; native Switch NRO and HD replacement
remain outside this milestone. PR is draft, stacked on v65;
`main` is not changed.
