# MAP02 v78 — observing real emulated RCNT VBlank edges and native VRAM

## What is new beyond v77

v77 confirmed 2,380 exact native BGR555 pixels across four **bounded
MIPS execution blocks** inside one pinned PCSX ReARMed process. But the
block boundaries were deliberately authored by the fixture. They were
**not VBlank events, GPU scanout transitions or genuine video frames**.

v78 hooks the actual, unmocked **PlayStation emulation scheduler** at
`libpcsxcore/psxcounters.c::psxRcntUpdate()`, immediately **after**
the corresponding real GPU callback calls:

- `GPU_vBlank(1,0)`, when `hSyncCount==240`.
- `GPU_vBlank(0,field)`, at the scheduler's scanline-frame end.

The hook is an additive `#ifdef VH_MAP02_V66_PCSX_PROBE` observer
and does **not** invoke or fake `psxRcntUpdate()`, `GPU_vBlank()`,
setIrq, interrupt scheduling, timing registers or the rasterizer.
A feature-OFF object build confirms the observer symbol is absent.
The unmodified upstream scheduler supplies every event, driven by
the **real pinned PCSX MIPS interpreter advancing emulated cycles**.

Repository source:
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).

## Controlled executable and renderer

The input is the same reproducible **6 KiB, wholly synthetic v77
PS-X EXE**, generated using original hand-encoded MIPS opcodes.
No Vandal Hearts game assets, retail texture pages, original PS1
BIOS image, commercial SDK or private hardware capture are used.

First, the full emulator executes all four v77 GPU state/VRAM phases.
The RAM completion marker and expected final MIPS branch PC must
match exactly. This leaves the GPU software renderer with six known
painted 4×4 cells and GP0(E1/E2/E6) in the fully reset state.

The frontend then performs the following *without reinitialization,
reloading the EXE, or writing GPU pixels again*:

1. Verify and freeze the existing VRAM before VBlank, comparing all
   x39..123/y159..165 pixels with the independent v77 pixel oracle.
2. Execute the genuine MIPS interpreter's final self-branch, in
   **bounded** CPU blocks, until the instrumented original
   `psxRcntUpdate()` reports a **VBlank-start** callback.
3. Verify ordered callback receipt, monotonic CPU cycle and hsync
   value, then immediately freeze and check all GPU pixels and
   GP0(E1/E2/E6) state again.
4. Repeat for **VBlank-end, next VBlank-start, next VBlank-end**,
   sampling the native GPU VRAM after each observed callback.

This yields **four true emulated VBlank callback receipts** and
**five native GPU VRAM snapshots** × **595 pixel samples**, for
**2,975 independent 16-bit BGR555 pixel comparisons**.

The events must arrive in alternating order `start,end,start,end`,
with hSync 240 for starts and 0 for completed end callbacks
(`hSyncCount` has been reset by the original scheduler at end).
Cycle timestamps must be strictly increasing; snapshots must occur
within 4,096 MIPS scheduler cycles of event receipt, and no event may
be skipped or silently lost. An eight-entry bounded ring rejects
overflow. This is **emulator-time**, not real wall-clock timestamps.

A source-only hook that synthesized fabricated callbacks without
executing MIPS cycles would not pass the runtime event and native
VRAM verification. No event is inferred from a screenshot or from
the four authored CPU phase boundaries.

## Fail-closed real emulator tests

The full GCC and Clang CI inherits v45–v77 original public PC-port
GPU/PRS/GTE/OT/VHT1, DMA2, MIPS, private-provenance and raster tests
and adds **34 Python adversarial tests** for hook positions, source
gating, bounded event ring, exact CPU phase completion, event
ordering, monotonic cycle time, and independent native pixel oracle.

Native negative cases:

1. **Short MIPS cycle budget**: source-authored valid EXE and live
   emulator deliberately receive insufficient CPU cycles to reach
   a real VBlank; the test must fail with
   `VH78_VBLANK_MISSING_REFUSED`. No host emits a fake event.
2. **Mutated source-authored GP0 color**: identical valid EXE,
   different last red rectangle command; GPU VRAM must reject 16
   wrong pixels at baseline.
3. **Forged fixture identification**: an executable without the
   exact synthetic marker is rejected before it runs.

Only source-authored synthetic proof artifacts are permitted on
GitHub. Do not publish user-owned original GPU FIFO captures,
commercial textures, game RAM snapshots or retail media.

## What this is *not*

This genuinely observes the **PCSX emulation scheduler's actual**
GPU VBlank calls. It is **not** a capture of physical PS1 VBlank
signals or PlayStation video output measured independently on
real hardware. The five measured VRAM snapshots are taken
*immediately after the host-visible emulated scheduler callback
returns to the CPU-stub runner*, not at a separately instrumented
hardware scanout instant.

No original Vandal Hearts MAP02 was loaded. No authentic MAP02 scene,
Retail PlayStation GPU parity, actual Nintendo Switch gameplay or
HD texture replacement can be concluded from these synthetic
emulator events.

`authentic_physical_ps1_vblank_verified=false`

`retail_MAP02_frame_timing_verified=false`

`original_retail_MAP02_verified=false`

`HD_replacement_approved=false`

All proofs remain in a **stacked DRAFT PR** above v77. Nothing is
merged into `main`.
